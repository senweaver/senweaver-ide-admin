import asyncio
import json
import uuid
import os
import re
import random
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Set
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, AliasChoices, ConfigDict
import uvicorn
from src.utils.web_search import perform_web_search, WEB_SEARCH_DEFAULT_ENGINES

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
except Exception:
    pass

# 数据库相关导入
try:
    from src.core.database import init_db, close_db, AsyncSessionLocal
    from src.api.articles import router as articles_router
    from src.api.stats import router as stats_router
    from src.api.admin import router as admin_router, verify_admin_token
    from src.api.users import router as users_router
    from src.api.orders import router as orders_router
    from src.api.key_pools import router as key_pools_router
    from src.services.stats_service import stats_service
    from src.services.key_pool_service import key_pool_service
    from src.services.user_service import user_service
    from src.models.models import UsageLog, UserStatus, IDEVersion
    from sqlalchemy import select
    DB_ENABLED = True
    from src.core.connection_manager import clients, manager, ConnectionManager, ClientInfo
    from src.schemas.schemas import ClientResponse
except ImportError as e:
    print(f"数据库模块导入失败: {e}")
    print("将以无数据库模式运行")
    DB_ENABLED = False


# 数据模型
# ClientInfo moved to connection_manager.py
# ClientResponse moved to schemas.py


class VersionUpdateRequest(BaseModel):
    version: str
    description: Optional[str] = None


class ModelConfigRequest(BaseModel):
    client_id: str


class ModelUsageRecordRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    api_key: str = Field(
        min_length=1,
        max_length=2048,
        validation_alias=AliasChoices("api_key", "key", "secret")
    )

    model_config = ConfigDict(protected_namespaces=())


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    engines: Optional[List[str]] = None
    limit: int = Field(default=16, ge=1, le=50)
    user_id: str = Field(min_length=1, max_length=100)
    timestamp: int = Field(description="10位时间戳（秒级）")
    auth: str = Field(min_length=1, description="md5签名字符串")


class SearchResult(BaseModel):
    title: str
    url: str
    description: str
    engine: str


class WebSearchResponse(BaseModel):
    query: str
    engines: List[str]
    total: int
    results: List[SearchResult]





# 全局变量
DEFAULT_VERSION = "1.0.0"

# 存储所有客户端信息 - moved to connection_manager.py
# clients and active_connections are imported from connection_manager.py

# 文件下载配置
DOWNLOAD_BASE_DIR = Path(__file__).resolve().parent / "download"

# 版本管理
latest_version_info = {
    "version": DEFAULT_VERSION,
    "updated_at": datetime.now().isoformat(),
    "description": f"当前版本 {DEFAULT_VERSION}"
}


async def get_latest_ide_version(db_session=None) -> str:
    """从数据库获取最新IDE版本"""
    if not DB_ENABLED:
        return DEFAULT_VERSION
    
    try:
        if db_session:
             result = await db_session.execute(select(IDEVersion).where(IDEVersion.is_latest == True))
             v = result.scalar_one_or_none()
             return v.version if v else DEFAULT_VERSION
        else:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(IDEVersion).where(IDEVersion.is_latest == True))
                v = result.scalar_one_or_none()
                return v.version if v else DEFAULT_VERSION
    except Exception as e:
        print(f"获取最新版本失败: {e}")
        return DEFAULT_VERSION

def compare_versions(version1: str, version2: str) -> int:
    """比较两个版本号，返回 1 表示 version1 > version2，-1 表示 version1 < version2，0 表示相等"""
    def normalize_version(v):
        return [int(x) for x in re.sub(r'[^\d.]', '', v).split('.') if x.isdigit()]
    
    v1_parts = normalize_version(version1)
    v2_parts = normalize_version(version2)
    
    # 补齐长度
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    
    for i in range(max_len):
        if v1_parts[i] > v2_parts[i]:
            return 1
        elif v1_parts[i] < v2_parts[i]:
            return -1
    
    return 0


def get_latest_available_version() -> Optional[str]:
    """从download目录中获取最新的可用版本"""
    if not DOWNLOAD_BASE_DIR.exists():
        return None
    
    versions = []
    for version_dir in DOWNLOAD_BASE_DIR.iterdir():
        if version_dir.is_dir():
            # 检查是否有exe文件
            exe_files = list(version_dir.glob("*.exe"))
            if exe_files:
                versions.append(version_dir.name)
    
    if not versions:
        return None
    
    # 按版本号排序，返回最新的
    versions.sort(key=lambda v: [int(x) for x in re.sub(r'[^\d.]', '', v).split('.') if x.isdigit()], reverse=True)
    return versions[0]


# ConnectionManager moved to connection_manager.py


async def heartbeat_task():   
    # 初始化版本
    manager.current_version = await get_latest_ide_version()
    print(f"心跳任务已启动，当前版本: {manager.current_version}")

    while True:
        try:
            # 等待事件触发 或 60秒超时
            # wait_for 会在超时后抛出 TimeoutError
            await asyncio.wait_for(manager.version_update_event.wait(), timeout=60)
            
            # 如果执行到这里，说明事件被触发了（版本更新）
            manager.version_update_event.clear()
            print(f"检测到版本更新，立即广播: {manager.current_version}")
            
        except asyncio.TimeoutError:
            # 超时（正常心跳周期）
            pass
        except Exception as e:
            print(f"心跳任务异常: {e}")
            await asyncio.sleep(5) # 防止死循环
            
        # 无论是超时还是事件触发，都广播当前版本
        await manager.broadcast_heartbeat(manager.current_version)
        print(f"心跳包已发送给 {len(manager.active_connections)} 个活跃客户端 ({manager.current_version})")




@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 挂载共享状态到 app.state
    app.state.clients = clients
    app.state.manager = manager
    
    # 启动时执行
    asyncio.create_task(heartbeat_task())
    print("WebSocket服务器已启动，心跳包任务已开始")
    
    # 初始化密钥池
    # if DB_ENABLED:
    #     async with AsyncSessionLocal() as db:
    #         await key_pool_service.initialize_key_pools(db)
    #     print("密钥池已初始化")
    
    # 初始化数据库
    # if DB_ENABLED:
    #     try:
    #         await init_db()
    #         print("数据库已初始化")
    #     except Exception as e:
    #         print(f"数据库初始化失败: {e}")
    
    yield
    
    # 关闭时执行
    if DB_ENABLED:
        try:
            await close_db()
            print("数据库连接已关闭")
        except Exception as e:
            print(f"关闭数据库连接失败: {e}")
    print("WebSocket服务器正在关闭...")

# 创建FastAPI应用实例，使用lifespan事件处理器
app = FastAPI(title="WebSocket Backend", version="2.7.2", lifespan=lifespan)

# ============================================
# 添加 CORS 中间件（重要！解决跨域问题）
# ============================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议改为 ["vscode-file://vscode-app"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

# ============================================
# 全局认证中间件
# ============================================
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from src.api.admin import active_sessions
import re

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 放行 OPTIONS 请求
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    method = request.method

    # 白名单路径 (无需登录)
    # 1. 静态资源和文档
    if path.startswith("/admin") or path.startswith("/assets") or path in ["/docs", "/redoc", "/openapi.json", "/favicon.svg"]:
        return await call_next(request)
    
    # 2. 指定的公开接口
    public_paths = [
        "/download/latest",
        "/changelogs",
        "/version/current", # 保持版本检查公开
        "/version/check",   # 保持版本检查公开
        "/api/version/current",
        "/api/version/check",
        "/api/admin/login", # 允许管理员登录
        "/stats",           # 服务器状态统计 (无需鉴权)
        "/api/upload/image",
        "/api/web_search",  # 联网搜索接口（需要认证但不需要登录）
    ]
    
    if path in public_paths:
        return await call_next(request)
        
    # 3. 正则匹配的公开接口
    # /version/{version}/changelog
    if re.match(r"^/version/[^/]+/changelog$", path):
        return await call_next(request)

    if re.match(r"^/api/version/[^/]+/changelog$", path):
        return await call_next(request)
        
    # /download/{version} 和 /download/{version}/info (为了支持下载特定版本)
    if re.match(r"^/download/[^/]+(/info)?$", path):
        return await call_next(request)

   
    if path.startswith("/api/blog/") and method == "GET":       
        return await call_next(request)

    # 验证 Token
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # 也可以从 Query 参数获取 (为了方便某些GET请求)
    if not token:
        token = request.query_params.get("token")

    if not token or token not in active_sessions:
        return JSONResponse(
            status_code=401,
            content={"detail": "未授权访问，请先登录"}
        )
    
    # 检查 Token 有效期
    session = active_sessions[token]
    if datetime.now() > session["expires_at"]:
        del active_sessions[token]
        return JSONResponse(
            status_code=401,
            content={"detail": "登录已过期，请重新登录"}
        )

    return await call_next(request)


# 注册API路由
if DB_ENABLED:
    app.include_router(articles_router)
    app.include_router(stats_router)
    app.include_router(admin_router)
    app.include_router(users_router)
    app.include_router(orders_router)
    app.include_router(key_pools_router)
    print("已注册文章管理、统计、管理员、用户、订单和密钥池API路由")

# 管理后台路由 - Vite构建后的静态文件
ADMIN_DIR = Path(__file__).parent / "static" / "admin"

# 挂载静态资源目录
if (ADMIN_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=ADMIN_DIR / "assets"), name="assets")

@app.get("/favicon.svg")
async def favicon():
    return FileResponse(ADMIN_DIR / "favicon.svg")
# MIME类型映射
MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

def verify_image_upload_sn(user_id: str, sn: str, timestamp: Optional[str] = None) -> bool:
    if not user_id or not sn:
        return False

    def match_ts(ts: str) -> bool:
        if not ts or not ts.isdigit() or len(ts) != 10:
            return False
        raw = f"{ts}{AUTH_SALT}{user_id}"
        expected = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return expected.lower() == sn.lower()

    if timestamp and match_ts(timestamp):
        return True

    now_ts = int(datetime.now().timestamp())
    for delta in range(0, 301):
        if match_ts(str(now_ts - delta)):
            return True

    return False

def normalize_oss_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return ""
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    return f"https://{endpoint}"

def get_oss_client(endpoint_override: Optional[str] = None):
    try:
        import oss2
    except Exception:
        return None

    access_key_id = os.getenv("ALIYUN_OSS_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("ALIYUN_OSS_ACCESS_KEY_SECRET", "").strip()
    endpoint = (endpoint_override or os.getenv("ALIYUN_OSS_ENDPOINT", "")).strip()
    bucket_name = os.getenv("ALIYUN_OSS_BUCKET", "senweaver").strip()

    if not access_key_id or not access_key_secret or not endpoint or not bucket_name:
        return None

    endpoint = normalize_oss_endpoint(endpoint)
    if not endpoint:
        return None

    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)

def get_oss_signing_client():
    try:
        import oss2
    except Exception:
        return None

    access_key_id = os.getenv("ALIYUN_OSS_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("ALIYUN_OSS_ACCESS_KEY_SECRET", "").strip()
    bucket_name = os.getenv("ALIYUN_OSS_BUCKET", "senweaver").strip()

    if not access_key_id or not access_key_secret or not bucket_name:
        return None

    base_url = os.getenv("ALIYUN_OSS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    is_cname = False
    endpoint = ""

    if base_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
            if parsed.scheme and parsed.netloc:
                endpoint = f"{parsed.scheme}://{parsed.netloc}"
                is_cname = True
        except Exception:
            endpoint = ""

    if not endpoint:
        raw_endpoint = os.getenv("ALIYUN_OSS_ENDPOINT", "").strip()
        public_endpoint = os.getenv("ALIYUN_OSS_PUBLIC_ENDPOINT", "").strip() or raw_endpoint.replace("-internal.", ".")
        endpoint = normalize_oss_endpoint(public_endpoint)
        is_cname = False

    if not endpoint:
        return None

    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name, is_cname=is_cname)

def build_oss_signed_get_url(object_key: str) -> Optional[str]:
    bucket = get_oss_signing_client()
    if not bucket:
        return None

    try:
        expires = int(os.getenv("ALIYUN_OSS_SIGN_EXPIRES", "3600").strip() or "3600")
    except Exception:
        expires = 3600

    if expires <= 0:
        expires = 3600

    try:
        return bucket.sign_url("GET", object_key, expires, slash_safe=True)
    except Exception:
        return None

def build_oss_public_url(object_key: str) -> Optional[str]:
    base_url = os.getenv("ALIYUN_OSS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}/{object_key.lstrip('/')}"

    endpoint = os.getenv("ALIYUN_OSS_ENDPOINT", "").strip()
    public_endpoint = os.getenv("ALIYUN_OSS_PUBLIC_ENDPOINT", "").strip() or endpoint.replace("-internal.", ".")
    bucket_name = os.getenv("ALIYUN_OSS_BUCKET", "senweaver").strip()
    if not public_endpoint or not bucket_name:
        return None

    host = normalize_oss_endpoint(public_endpoint).replace("https://", "").replace("http://", "").strip().strip("/")
    if not host:
        return None

    return f"https://{bucket_name}.{host}/{object_key.lstrip('/')}"

@app.get("/admin/{file_path:path}")
async def admin_static(file_path: str):
    """管理后台静态文件"""
    # 如果是空路径或目录请求，返回index.html
    if not file_path or file_path.endswith("/"):
        file_path = "index.html"
    
    file = ADMIN_DIR / file_path
    
    # 如果文件不存在且不是静态资源，返回index.html（SPA路由）
    if not file.exists() or not file.is_file():
        if not any(file_path.endswith(ext) for ext in MIME_TYPES.keys()):
            file = ADMIN_DIR / "index.html"
    
    if file.exists() and file.is_file():
        suffix = file.suffix.lower()
        content_type = MIME_TYPES.get(suffix, "application/octet-stream")
        return FileResponse(file, media_type=content_type)
    
    return HTMLResponse(content="Not Found", status_code=404)

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """管理后台入口"""
    admin_html = ADMIN_DIR / "index.html"
    if admin_html.exists():
        return HTMLResponse(content=admin_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>管理后台未找到，请先构建: cd admin-frontend && npm run build</h1>", status_code=404)


AUTH_SALT = os.getenv("AUTH_SALT", "default_your_auth_salt")


def verify_web_search_auth(user_id: str, timestamp: int, auth_received: str) -> bool:
    
    if not user_id or not auth_received or not timestamp:
        return False

    # 兼容字符串/数字时间戳
    try:
        ts_int = int(str(timestamp))
    except (TypeError, ValueError):
        return False

    # 必须是 10 位秒级时间戳
    if ts_int <= 0 or len(str(ts_int)) != 10:
        return False

    # 校验时间窗口（±5 分钟）
    now_ts = int(datetime.now().timestamp())
    if abs(now_ts - ts_int) > 300:
        return False

    raw = f"{ts_int}{user_id}{AUTH_SALT}web_search"
    expected_auth = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return expected_auth.lower() == (auth_received or "").lower()

def verify_client_auth(user_id: str, timestamp: str, auth_received: str, auth_type: str) -> bool:
    """
    验证客户端连接/心跳合法性
    规则: 原始字符串=10位时间戳+用户id+固定字符串+类型
    """
    if not user_id or not timestamp or not auth_received:
        return False
    
    # 构造原始字符串
    raw = f"{timestamp}{user_id}{AUTH_SALT}{auth_type}"
    # 计算MD5
    expected_auth = hashlib.md5(raw.encode("utf-8")).hexdigest()
    
    return expected_auth.lower() == auth_received.lower()


async def disconnect_other_sessions(user_id: str, current_client_id: str):
    """
    当用户登录时，断开该用户的所有其他连接 (互斥登录)
    """
    if not user_id:
        return
        
    user_id_str = str(user_id)
    
    # 找出需要断开的连接ID
    clients_to_disconnect = []
    for cid, info in clients.items():
        # 检查是否是同一个用户，且不是当前连接
        if info.user_id and str(info.user_id) == user_id_str and cid != current_client_id:
            if info.is_online:
                clients_to_disconnect.append(cid)
    
    # 执行断开操作
    for cid in clients_to_disconnect:
        print(f"检测到用户 {user_id} (Client: {current_client_id}) 登录，正在断开旧连接 {cid}")
        try:
            # 发送通知消息
            await manager.send_to_client(cid, {
                "type": "error",
                "message": "您的账号已在其他设备登录，连接已断开"
            })
            
            # 关闭连接
            if cid in manager.active_connections:
                await manager.active_connections[cid].close()
            
            # 清理状态
            manager.disconnect(cid)
        except Exception as e:
            print(f"断开旧连接 {cid} 失败: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接端点"""
    # 从URL参数中获取user_id
    user_id = websocket.query_params.get("user_id")
    token = websocket.query_params.get("token")
    timestamp = websocket.query_params.get("timestamp")
    auth = websocket.query_params.get("auth")

    # 验证客户端合法性 (非管理员连接必须验证)
    # 管理员连接通常带有token且走特殊流程，但这里如果用户要求统一验证，也需要加上
    # 不过管理员通常没有user_id，而是通过token换取。
    # 根据用户描述 "客户端在websocket连接...添加auth字段"，主要针对普通客户端。
    # 暂时对所有连接进行验证，如果user_id存在。
    
    # 强制验证逻辑:
    # 如果是普通客户端连接(无管理员token)，必须通过验证
    # 如果是管理员连接(有token)，可以跳过此验证，或者也必须验证
    # 假设: 只有带有 user_id 的连接才需要验证 auth (即普通客户端)
    
    # 注意: 如果客户端是旧版没有传auth，会被拒绝连接 (Breaking Change)
    if user_id: 
        if not verify_client_auth(user_id, timestamp, auth, "connection"):
            print(f"客户端连接验证失败: user_id={user_id}, timestamp={timestamp}, auth={auth}")
            # 拒绝连接 (使用 1008 Policy Violation)
            # 注意: accept() 还没调用，可以直接 close? 
            # FastAPI websocket 需要先 accept 才能 close? 
            # 不，可以直接抛出异常或者不 accept 直接 close
            await websocket.close(code=1008, reason="Authentication failed")
            return

    is_admin = False
    
    if token:
        admin_session = verify_admin_token(token)
        if admin_session:
            is_admin = True
            print(f"管理员 {admin_session.get('username', 'unknown')} 已连接")
    
    # 获取客户端IP
    client_ip = None
    user_agent = None
    try:
        client_ip = websocket.client.host if websocket.client else None
        user_agent = websocket.headers.get("user-agent", "")
    except:
        pass
    
    client_id = await manager.connect(websocket, user_id, client_ip, user_agent, is_admin=is_admin)

    # 处理多端登录互斥 (如果在连接时就提供了user_id)
    if user_id:
        await disconnect_other_sessions(user_id, client_id)

    
    # 记录连接统计
    if DB_ENABLED:
        try:
            async with AsyncSessionLocal() as db:
                await stats_service.log_connection(db, client_id, user_id, client_ip, user_agent)
                # 确保用户存在于users表中
                if user_id:
                    user = await user_service.ensure_user_exists(db, user_id)
                    
                    # 检查是否是新创建的用户 (5秒内创建)
                    # 注意：created_at可能是naive time，datetime.now()也是
                    if user and user.created_at and (datetime.now() - user.created_at).total_seconds() < 5:
                        try:
                             from src.api.users import notify_user_update
                             await notify_user_update(db, user.id)
                        except Exception as e:
                             print(f"通知新用户创建失败: {e}")

                    # 如果用户被禁用，不分配key，并在后续消息中告知
                    # if user and user.status == UserStatus.BANNED:
                    #    ...
        except Exception as e:
            print(f"记录连接统计失败: {e}")
    
    try:
        # 为客户端分配密钥
        # 获取活跃的提供商列表
        active_providers = {}
        model_access = None
        user_banned = False
        
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                if user_id:
                    user = await user_service.ensure_user_exists(db, user_id)
                    if user and user.status == UserStatus.BANNED:
                        user_banned = True
                        print(f"用户 {user_id} 已被禁用，标记为禁用状态")
                    else:
                        model_access = await user_service.get_model_access_status(db, user_id)

                active_providers_list = await key_pool_service.get_active_providers(db)
                active_providers = {p.name: p for p in active_providers_list}
        
        allocated_keys = {}
        # 只有未禁用且（无model_access限制或enabled=True）且非管理员时才分配key
        if DB_ENABLED and active_providers and not user_banned and not is_admin and (not model_access or model_access.get("enabled")):
            async with AsyncSessionLocal() as db:
                for provider_name in active_providers.keys():
                    api_key = await key_pool_service.allocate_key_for_client(db, provider_name, client_id, user_id)
                    if api_key:
                        allocated_keys[provider_name] = api_key
        
        # 构建连接成功消息
        welcome_message = {
            "type": "connection",
            "message": "连接成功",
            "client_id": client_id,
            "user_id": user_id,
            "version": await get_latest_ide_version(),
            "timestamp": datetime.now().isoformat()
        }

        if user_banned:
            welcome_message["model_access"] = {
                "enabled": False,
                "used": 0,
                "used_total": 0,
                "limit": 0,
                "reset_days": 30,
                "last_reset_time": None,
                "reason": "您的账号已被禁用"
            }
            # 返回 DISABLED 的配置
            if active_providers:
                 welcome_message["model_providers"] = {
                    provider_name: {
                        "api_key": "DISABLED",
                        "base_url": provider_info.base_url or "",
                    }
                    for provider_name, provider_info in active_providers.items()
                }
            print(f"客户端 {client_id} (用户 {user_id}) 连接成功，但账号已被禁用")

        elif model_access is not None:
            welcome_message["model_access"] = {
                "enabled": model_access.get("enabled"),
                "used": model_access.get("used"),
                "used_total": model_access.get("used_total", 0),
                "limit": model_access.get("limit"),
                "reset_days": model_access.get("reset_days", 30),
                "last_reset_time": model_access.get("last_reset_time"),
                "reason": model_access.get("disabled_reason"),
            }
        
        # 如果成功分配密钥，添加模型配置信息
        if allocated_keys:
            model_providers = {}

            for provider_name, api_key in allocated_keys.items():
                if provider_name in active_providers:
                    provider_info = active_providers[provider_name]
                    model_providers[provider_name] = {
                        "api_key": api_key,
                        "base_url": provider_info.base_url or ""
                    }

            welcome_message["model_providers"] = model_providers
            print(f"客户端 {client_id} 已分配密钥配置: {list(model_providers.keys())}")
        else:
            if model_access is not None and not model_access.get("enabled"):
                welcome_message["message"] = "连接成功，模型调用已被禁用"
                if active_providers:
                    welcome_message["model_providers"] = {
                        provider_name: {
                            "api_key": "DISABLED",
                            "base_url": provider_info.base_url or "",
                        }
                        for provider_name, provider_info in active_providers.items()
                    }
                print(f"客户端 {client_id} 连接成功，但模型调用已被禁用")
            else:
                if is_admin:
                    welcome_message["message"] = "连接成功 (管理员)"
                else:
                    welcome_message["message"] = "连接成功，但密钥池已满，未分配模型配置"
                    print(f"客户端 {client_id} 连接成功，但未分配密钥（密钥池已满）")
        
        await websocket.send_text(json.dumps(welcome_message))
        
        # 保持连接活跃，监听客户端消息
        while True:
            try:
                # 接收客户端消息
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # 处理客户端消息
                if message.get("type") == "ping":
                    pong_message = {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send_text(json.dumps(pong_message))
                
                # 处理客户端初始化消息
                elif message.get("type") == "init":
                    # 更新客户端的用户ID
                    init_user_id = message.get("user_id")
                    if init_user_id and client_id in clients:
                        clients[client_id].user_id = init_user_id
                        # 处理多端登录互斥
                        await disconnect_other_sessions(init_user_id, client_id)
                    
                    await handle_client_init(client_id, message, websocket)
                
                # 处理心跳包，验证客户端密钥
                elif message.get("type") == "heartbeat":
                    # 从心跳包中获取user_id并更新客户端信息
                    heartbeat_user_id = message.get("user_id")
                    if heartbeat_user_id and client_id in clients:
                        clients[client_id].user_id = heartbeat_user_id
                        clients[client_id].last_heartbeat = datetime.now()
                    
                    await handle_client_heartbeat(client_id, message, websocket)

                # 处理模型使用上报
                elif message.get("type") == "model_usage_report":
                    user_id = message.get("user_id")
                    model_name = message.get("model_name")
                    inc = message.get("inc", 1)
                    if user_id and DB_ENABLED:
                        try:
                            async with AsyncSessionLocal() as db:
                                usage_result = await user_service.increment_model_usage(
                                    db, 
                                    user_id, 
                                    inc=inc, 
                                    model_name=model_name,
                                    client_id=client_id
                                )
                                if usage_result:
                                    # 发送确认消息
                                    await websocket.send_text(json.dumps({
                                        "type": "model_usage_ack",
                                        "success": True,
                                        "usage": usage_result
                                    }))

                                    # 通知管理员用户数据更新 (实时更新用量)
                                    try:
                                        from src.api.users import notify_user_update
                                        user = await user_service.get_user_by_user_id(db, user_id)
                                        if user:
                                            await notify_user_update(db, user.id)
                                    except Exception as e:
                                        print(f"通知用户用量更新失败: {e}")
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "model_usage_ack",
                                        "success": False,
                                        "error": "User not found"
                                    }))
                        except Exception as e:
                            print(f"处理模型使用上报失败: {e}")
                            await websocket.send_text(json.dumps({
                                "type": "model_usage_ack",
                                "success": False,
                                "error": str(e)
                            }))
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"处理客户端 {client_id} 消息时出错: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        # 记录断开连接统计
        if DB_ENABLED:
            try:
                async with AsyncSessionLocal() as db:
                    final_user_id = clients[client_id].user_id if client_id in clients else user_id
                    await stats_service.log_disconnection(db, client_id, final_user_id)
            except Exception as e:
                print(f"记录断开连接统计失败: {e}")
        
        # 客户端断开连接时释放密钥
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                await key_pool_service.release_key_for_client(db, client_id)
        
        # 获取用户ID用于通知（需要在disconnect之前获取）
        notify_user_id_str = clients[client_id].user_id if client_id in clients else user_id
        
        manager.disconnect(client_id)

        # 通知管理员用户下线
        if DB_ENABLED and notify_user_id_str:
             try:
                 async with AsyncSessionLocal() as db:
                     from src.api.users import notify_user_update
                     user = await user_service.get_user_by_user_id(db, notify_user_id_str)
                     if user:
                         await notify_user_update(db, user.id)
             except Exception as e:
                 print(f"通知用户下线失败: {e}")


async def handle_client_init(client_id: str, message: dict, websocket: WebSocket):
    """处理客户端初始化消息"""
    try:
        user_id = message.get("user_id")
        model_providers = message.get("model_providers", {})
        
        print(f"客户端 {client_id} 发送初始化消息，用户ID: {user_id}")
        print(f"客户端提供的模型配置: {model_providers}")

        if DB_ENABLED and user_id:
            async with AsyncSessionLocal() as db:
                status = await user_service.get_model_access_status(db, user_id)
                if status and not status.get("enabled"):
                    await key_pool_service.release_key_for_client(db, client_id)
                    active_providers_list = await key_pool_service.get_active_providers(db)
                    active_providers = {p.name: p for p in active_providers_list}
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "model_config_update",
                                "timestamp": datetime.now().isoformat(),
                                "model_providers": {
                                    provider_name: {
                                        "api_key": "DISABLED",
                                        "base_url": provider_info.base_url or "",
                                    }
                                    for provider_name, provider_info in active_providers.items()
                                },
                            }
                        )
                    )
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "model_access_update",
                                "enabled": False,
                                "used": status.get("used"),
                                "used_total": status.get("used_total", 0),
                                "limit": status.get("limit"),
                                "reset_days": status.get("reset_days", 30),
                                "last_reset_time": status.get("last_reset_time"),
                                "reason": status.get("disabled_reason"),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )
                    return
        
        # 验证客户端提供的密钥状态
        key_validation_result = {}
        active_providers = {}
        
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                # 确保用户存在
                if user_id:
                    user = await user_service.ensure_user_exists(db, user_id)
                    # 检查用户状态
                    if user and user.status == UserStatus.BANNED:
                        print(f"用户 {user_id} 已被禁用，返回禁用状态配置")
                        # 释放之前可能存在的key
                        await key_pool_service.release_key_for_client(db, client_id)
                        
                        active_providers_list = await key_pool_service.get_active_providers(db)
                        active_providers = {p.name: p for p in active_providers_list}
                        
                        # 发送禁用配置更新
                        await websocket.send_text(json.dumps({
                            "type": "model_config_update",
                            "timestamp": datetime.now().isoformat(),
                            "model_providers": {
                                provider_name: {
                                    "api_key": "DISABLED",
                                    "base_url": provider_info.base_url or "",
                                }
                                for provider_name, provider_info in active_providers.items()
                            },
                        }))
                        # 发送权限更新
                        await websocket.send_text(json.dumps({
                            "type": "model_access_update",
                            "enabled": False,
                            "used": 0,
                            "limit": 0,
                            "reason": "您的账号已被禁用",
                            "timestamp": datetime.now().isoformat(),
                        }))
                        return

                # 获取活跃提供商用于后续逻辑
                active_providers_list = await key_pool_service.get_active_providers(db)
                active_providers = {p.name: p for p in active_providers_list}
                
                for provider_name, provider_config in model_providers.items():
                    if "api_key" in provider_config:
                        client_key = provider_config["api_key"]
                        is_valid = await key_pool_service.validate_client_key(db, provider_name, client_id, client_key)
                        key_validation_result[provider_name] = "valid" if is_valid else "invalid"
                        
                        if not is_valid:
                            # 尝试接受客户端提供的密钥（如果它在我们的池中是有效的）
                            # 这解决了客户端坚持使用旧密钥（但在池中有效）导致的死循环问题
                            accepted = await key_pool_service.try_accept_client_key(db, provider_name, client_id, client_key, user_id)
                            if accepted:
                                is_valid = True
                                key_validation_result[provider_name] = "valid"
                                print(f"DEBUG [Init]: 接受并同步客户端提供的密钥 - Provider: {provider_name}")
                            else:
                                expected_key = await key_pool_service.get_allocated_key(db, provider_name, client_id)
                                print(f"DEBUG [Init]: 密钥验证失败 - Provider: {provider_name}")
                                print(f"DEBUG [Init]: 客户端发送: '{client_key}'")
                                print(f"DEBUG [Init]: 服务器期望: '{expected_key}'")
                                if expected_key is None:
                                    print(f"DEBUG [Init]: 服务器端未找到该客户端的活跃分配记录")
                    else:
                        key_validation_result[provider_name] = "missing"
        print(f"密钥验证结果: {key_validation_result}")
        
        need_update = False
        update_reason = []
        
        # 检查是否需要更新配置
        for provider, status in key_validation_result.items():
            if status in ["invalid", "conflict", "missing"]:
                need_update = True
                if status == "invalid":
                    update_reason.append(f"{provider}密钥不在配置池中")
                elif status == "conflict":
                    update_reason.append(f"{provider}密钥被其他客户端使用")
                elif status == "missing":
                    update_reason.append(f"{provider}密钥缺失")
        
        if need_update:
            print(f"需要为客户端 {client_id} 重新分配配置，原因: {', '.join(update_reason)}")

            any_wrong = any(s in ["invalid", "conflict"] for s in key_validation_result.values())
            any_missing = any(s == "missing" for s in key_validation_result.values())

            # 确保客户端有分配的密钥（若还没有则分配一套）
            allocated_keys = {}
            if DB_ENABLED and active_providers:
                async with AsyncSessionLocal() as db:
                    for provider_name in active_providers.keys():
                        api_key = await key_pool_service.allocate_key_for_client(db, provider_name, client_id, user_id)
                        if api_key:
                            allocated_keys[provider_name] = api_key
            
            if not allocated_keys:
                error_response = {
                    "type": "error",
                    "message": "服务器密钥池已满，无法分配新的模型配置",
                    "error_code": "KEY_POOL_FULL"
                }
                await websocket.send_text(json.dumps(error_response))
                return

            if any_wrong or any_missing:
                new_model_config = {}

                for provider_name, api_key in allocated_keys.items():
                    if provider_name in active_providers:
                        provider_info = active_providers[provider_name]
                        new_model_config[provider_name] = {
                            "api_key": api_key,
                            "base_url": provider_info.base_url or ""
                        }

                config_update_response = {
                    "type": "model_config_update",
                    "timestamp": datetime.now().isoformat(),
                    "model_providers": new_model_config,
                    "reason": "配置重新分配",
                    "details": update_reason
                }
                await websocket.send_text(json.dumps(config_update_response))
                print(f"已向客户端 {client_id} 发送新的模型配置")
            
        else:
            print(f"客户端 {client_id} 的密钥配置有效，无需更新")
            
            # 发送确认消息（可选）
            confirmation_response = {
                "type": "init_success",
                "message": "初始化成功，当前配置有效",
                "user_id": user_id
            }
            await websocket.send_text(json.dumps(confirmation_response))
        
    except Exception as e:
        print(f"处理客户端 {client_id} 初始化消息时出错: {str(e)}")
        error_response = {
            "type": "error",
            "message": f"初始化处理失败: {str(e)}",
            "error_code": "INIT_ERROR"
        }
        await websocket.send_text(json.dumps(error_response))


async def handle_client_heartbeat(client_id: str, message: dict, websocket: WebSocket):
    """处理客户端心跳包，确保客户端使用服务器分配的密钥"""
    try:
        # 验证心跳包合法性
        # 规则: 原始字符串=10位时间戳+用户id+固定字符串+类型(heartbeat)
        hb_auth = message.get("auth")
        hb_timestamp = message.get("timestamp")
        
        # 获取关联的用户ID (消息中携带的 或者 之前记录的)
        heartbeat_user_id = message.get("user_id")
        if not heartbeat_user_id and client_id in clients:
            heartbeat_user_id = clients[client_id].user_id

        # 如果有用户ID，则必须验证auth
        if heartbeat_user_id:
            # 兼容旧逻辑: 如果没有auth字段，是否强制断开? 
            # 用户要求: "验证合法性的逻辑...如果不合法就直接强制断开连接"
            # 这意味着必须有auth字段
            
            # 注意: message.get("timestamp") 可能是 int 或 str，需要转 str
            ts_str = str(hb_timestamp) if hb_timestamp is not None else ""
            
            if not verify_client_auth(heartbeat_user_id, ts_str, hb_auth, "heartbeat"):
                print(f"客户端 {client_id} (用户 {heartbeat_user_id}) 心跳验证失败，强制断开")
                await websocket.close(code=1008, reason="Heartbeat authentication failed")
                return

        # 检查心跳包中是否包含模型配置
        client_model_config = message.get("model_providers", {})

        if DB_ENABLED and heartbeat_user_id:
            async with AsyncSessionLocal() as db:
                # 使用 get_user_by_user_id 而不是 ensure_user_exists，避免在心跳时自动创建用户
                user = await user_service.get_user_by_user_id(db, heartbeat_user_id)
                
                if not user:
                    print(f"Warning: 收到用户 {heartbeat_user_id} (Client: {client_id}) 的心跳，但用户在数据库中不存在")
                    # 如果用户不存在，可能需要断开连接，或者只是记录日志
                    # 这里选择断开，因为合法用户应该在 init 阶段就创建了
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "用户认证失败，连接断开"
                    }))
                    await websocket.close()
                    return

                # 检查用户状态，如果被禁用则发送禁用配置，而不是断开连接
                if user.status == UserStatus.BANNED:
                    print(f"用户 {heartbeat_user_id} 已被禁用，心跳检测拒绝服务并推送禁用状态")
                    
                    # 释放key
                    await key_pool_service.release_key_for_client(db, client_id)
                    
                    active_providers_list = await key_pool_service.get_active_providers(db)
                    active_providers = {p.name: p for p in active_providers_list}
                    
                    # 只有当客户端还没有收到禁用配置时（例如刚被禁用），推送一次更新
                    # 这里简化处理，每次心跳如果发现是禁用状态，都推送一次禁用配置，确保客户端状态同步
                    # 实际生产中可以优化为只推送一次，但心跳频率不高（60s），全量推送也可接受
                    
                    await websocket.send_text(json.dumps({
                        "type": "model_config_update",
                        "timestamp": datetime.now().isoformat(),
                        "model_providers": {
                            provider_name: {
                                "api_key": "DISABLED",
                                "base_url": provider_info.base_url or "",
                            }
                            for provider_name, provider_info in active_providers.items()
                        },
                    }))
                    
                    await websocket.send_text(json.dumps({
                        "type": "model_access_update",
                        "enabled": False,
                        "used": 0,
                        "limit": 0,
                        "reason": "您的账号已被禁用",
                        "timestamp": datetime.now().isoformat(),
                    }))
                    return
                
                # 更新最后活跃时间
                user.last_seen_at = datetime.now()
                await db.commit()

                status = await user_service.get_model_access_status(db, heartbeat_user_id)
                if status and not status.get("enabled"):
                    await key_pool_service.release_key_for_client(db, client_id)
                    active_providers_list = await key_pool_service.get_active_providers(db)
                    active_providers = {p.name: p for p in active_providers_list}
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "model_config_update",
                                "timestamp": datetime.now().isoformat(),
                                "model_providers": {
                                    provider_name: {
                                        "api_key": "DISABLED",
                                        "base_url": provider_info.base_url or "",
                                    }
                                    for provider_name, provider_info in active_providers.items()
                                },
                            }
                        )
                    )
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "model_access_update",
                                "enabled": False,
                                "used": status.get("used"),
                                "limit": status.get("limit"),
                                "reason": status.get("disabled_reason"),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )
                    return

        if not client_model_config:
            return
        
        # 提取客户端的密钥
        client_keys = {}
        for provider, config in client_model_config.items():
            if "api_key" in config:
                client_keys[provider] = config["api_key"]
        
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                # 获取活跃的提供商
                active_providers_list = await key_pool_service.get_active_providers(db)
                active_providers = {p.name: p for p in active_providers_list}
                
                missing = []
                wrong = []

                # 检查各个提供商的密钥
                for provider_name, client_api_key in client_keys.items():
                    # 仅检查活跃的提供商
                    if provider_name in active_providers:
                        # 跳过已禁用的Key检查
                        if client_api_key == "DISABLED":
                            continue

                        is_valid = await key_pool_service.validate_client_key(db, provider_name, client_id, client_api_key)
                        if not is_valid:
                            # 尝试接受客户端提供的密钥
                            accepted = await key_pool_service.try_accept_client_key(db, provider_name, client_id, client_api_key, message.get("user_id"))
                            if accepted:
                                is_valid = True
                                print(f"DEBUG [Heartbeat]: 接受并同步客户端提供的密钥 - Provider: {provider_name}")
                            else:
                                wrong.append(provider_name)
                                expected_key = await key_pool_service.get_allocated_key(db, provider_name, client_id)
                                print(f"DEBUG [Heartbeat]: 密钥验证失败 - Provider: {provider_name}")
                                print(f"DEBUG [Heartbeat]: 客户端发送: '{client_api_key}'")
                                print(f"DEBUG [Heartbeat]: 服务器期望: '{expected_key}'")
                                if expected_key is None:
                                    print(f"DEBUG [Heartbeat]: 服务器端未找到该客户端的活跃分配记录")
                
                # 检查是否有缺失的提供商密钥
                for provider_name in active_providers.keys():
                    if provider_name not in client_keys:
                        # 检查服务器端是否已经分配了key
                        allocated_key = await key_pool_service.get_allocated_key(db, provider_name, client_id)
                        if allocated_key:
                            # 如果服务器已分配，但客户端没发过来，视为缺失，需要补发
                            missing.append(provider_name)
                        else:
                            # 如果服务器也没分配，那就不算缺失，可能是池满了或者是新添加的provider
                            # 这种情况下，我们可以尝试分配
                            pass
                            # missing.append(provider_name) # 暂时不强制分配新provider，除非客户端请求或者显式分配逻辑触发
                
                # 如果有错误或缺失，尝试重新分配
                if wrong or missing:
                    new_model_config = {}
                    
                    # 重新分配或获取正确的密钥
                    for provider_name in active_providers.keys():
                        api_key = await key_pool_service.allocate_key_for_client(db, provider_name, client_id, message.get("user_id"))
                        if api_key:
                            provider_info = active_providers[provider_name]
                            new_model_config[provider_name] = {
                                "api_key": api_key,
                                "base_url": provider_info.base_url or ""
                            }
                    
                    if new_model_config:
                        msg = {
                            "type": "model_config_update",
                            "timestamp": datetime.now().isoformat(),
                            "model_providers": new_model_config
                        }
                        await websocket.send_text(json.dumps(msg))
                        print(f"已向客户端 {client_id} 发送正确的密钥配置 (心跳更新)")
                else:
                    # 验证通过，无需更新
                    pass
        
    except Exception as e:
        print(f"处理客户端 {client_id} 心跳包时出错: {e}")




@app.get("/clients", response_model=List[ClientResponse])
async def get_all_clients():
    """获取所有客户端信息和在线状态"""
    client_list = []
    
    for client_info in clients.values():
        client_response = ClientResponse(
            client_id=client_info.client_id,
            user_id=client_info.user_id,
            connect_time=client_info.connect_time.isoformat(),
            last_heartbeat=client_info.last_heartbeat.isoformat(),
            is_online=client_info.is_online
        )
        client_list.append(client_response)
    
    return client_list


@app.get("/clients/online")
async def get_online_clients():
    """获取当前在线的客户端"""
    online_clients = [
        {
            "client_id": client_info.client_id,
            "user_id": client_info.user_id,
            "connect_time": client_info.connect_time.isoformat(),
            "last_heartbeat": client_info.last_heartbeat.isoformat()
        }
        for client_info in clients.values()
        if client_info.is_online
    ]
    
    return {
        "online_count": len(online_clients),
        "clients": online_clients
    }


@app.get("/stats")
async def get_stats():
    """获取服务器统计信息"""
    online_count = sum(1 for client in clients.values() if client.is_online)
    
    return {
        "version": await get_latest_ide_version(),
        "total_clients": len(clients),
        "online_clients": online_count,
        "offline_clients": len(clients) - online_count,
        "active_connections": len(manager.active_connections)
    }


# 文件下载接口
@app.get("/download/versions")
async def get_available_versions():
    """获取所有可用的版本列表"""
    if not DOWNLOAD_BASE_DIR.exists():
        return {
            "versions": [],
            "message": "下载目录不存在"
        }
    
    versions = []
    for version_dir in DOWNLOAD_BASE_DIR.iterdir():
        if version_dir.is_dir():
            # 检查是否有exe文件
            exe_files = list(version_dir.glob("*.exe"))
            if exe_files:
                versions.append({
                    "version": version_dir.name,
                    "files": [exe_file.name for exe_file in exe_files]
                })
    
    return {
        "versions": versions,
        "total": len(versions)
    }


@app.get("/download/latest")
async def download_latest_version():
    """下载最新版本的应用程序"""
    # 首先尝试使用当前设置的最新版本
    latest_version = await get_latest_ide_version()

    version_dir = DOWNLOAD_BASE_DIR / latest_version

    if version_dir.exists():
        exe_files = list(version_dir.glob("*.exe"))
        if exe_files:
            exe_file = exe_files[0]
            if not exe_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"文件 {exe_file.name} 不存在"
                )

            return FileResponse(
                path=str(exe_file),
                filename=exe_file.name,
                media_type='application/octet-stream'
            )

    if DB_ENABLED:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(IDEVersion).where(IDEVersion.version == latest_version))
                v = result.scalar_one_or_none()
                if v and v.external_url:
                    return RedirectResponse(url=v.external_url)
        except Exception as e:
            print(f"获取版本详情失败: {e}")
    
    # 如果当前设置的版本目录不存在，尝试自动获取最新版本
    if not version_dir.exists():
        auto_latest = get_latest_available_version()
        if auto_latest:
            latest_version = auto_latest
            version_dir = DOWNLOAD_BASE_DIR / latest_version
        else:
            raise HTTPException(
                status_code=404,
                detail="没有找到可用的最新版本"
            )
    
    # 查找exe文件
    exe_files = list(version_dir.glob("*.exe"))
    if not exe_files:
        raise HTTPException(
            status_code=404,
            detail=f"最新版本 {latest_version} 下没有找到可执行文件"
        )
    
    # 选择第一个exe文件
    exe_file = exe_files[0]
    
    if not exe_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"文件 {exe_file.name} 不存在"
        )
    
    # 返回文件下载响应
    return FileResponse(
        path=str(exe_file),
        filename=exe_file.name,
        media_type='application/octet-stream'
    )


@app.get("/download/{version}")
async def download_version(version: str):
    """根据版本号下载对应的exe文件"""
    version_dir = DOWNLOAD_BASE_DIR / version
    
    # 检查版本目录是否存在
    if not version_dir.exists() or not version_dir.is_dir():
        raise HTTPException(
            status_code=404, 
            detail=f"版本 {version} 不存在"
        )
    
    # 查找exe文件
    exe_files = list(version_dir.glob("*.exe"))
    
    if not exe_files:
        raise HTTPException(
            status_code=404, 
            detail=f"版本 {version} 下没有找到可执行文件"
        )
    
    # 如果有多个exe文件，选择第一个
    exe_file = exe_files[0]
    
    # 检查文件是否存在
    if not exe_file.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"文件 {exe_file.name} 不存在"
        )
    
    # 返回文件下载响应
    return FileResponse(
        path=str(exe_file),
        filename=exe_file.name,
        media_type='application/octet-stream'
    )


@app.get("/download/{version}/info")
async def get_version_info(version: str):
    """获取指定版本的详细信息"""
    version_dir = DOWNLOAD_BASE_DIR / version
    
    if not version_dir.exists() or not version_dir.is_dir():
        raise HTTPException(
            status_code=404, 
            detail=f"版本 {version} 不存在"
        )
    
    exe_files = list(version_dir.glob("*.exe"))
    
    if not exe_files:
        raise HTTPException(
            status_code=404, 
            detail=f"版本 {version} 下没有找到可执行文件"
        )
    
    file_info = []
    for exe_file in exe_files:
        if exe_file.exists():
            stat = exe_file.stat()
            file_info.append({
                "filename": exe_file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    
    return {
        "version": version,
        "files": file_info,
        "download_url": f"/download/{version}"
    }


# 版本管理接口
@app.get("/version/current")
@app.get("/api/version/current")
async def get_current_version():
    """获取当前最新版本信息"""
    version = await get_latest_ide_version()
    desc = f"当前版本 {version}"
    updated_at = datetime.now().isoformat()
    
    if DB_ENABLED:
        try:
             async with AsyncSessionLocal() as db:
                 result = await db.execute(select(IDEVersion).where(IDEVersion.version == version))
                 v = result.scalar_one_or_none()
                 if v:
                     desc = v.description or desc
                     updated_at = v.updated_at.isoformat() if v.updated_at else updated_at
        except Exception as e:
            print(f"获取版本详情失败: {e}")
            
    return {
        "version": version,
        "updated_at": updated_at,
        "description": desc
    }


@app.post("/version/update")
async def update_latest_version(request: VersionUpdateRequest):
    """更新最新可用版本"""
    global latest_version_info
    
    # 验证版本是否在download目录中存在
    version_dir = DOWNLOAD_BASE_DIR / request.version
    if not version_dir.exists() or not version_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"版本 {request.version} 在下载目录中不存在"
        )
    
    # 检查是否有exe文件
    exe_files = list(version_dir.glob("*.exe"))
    if not exe_files:
        raise HTTPException(
            status_code=404,
            detail=f"版本 {request.version} 下没有找到可执行文件"
        )
    
    # 更新最新版本信息
    updated_at = datetime.now().isoformat()
    description = request.description or f"更新到版本 {request.version}"

    if DB_ENABLED:
        try:
            async with AsyncSessionLocal() as db:
                # Check if version exists in DB
                result = await db.execute(select(IDEVersion).where(IDEVersion.version == request.version))
                v = result.scalar_one_or_none()
                
                # If version doesn't exist in DB but exists on disk (checked above), maybe we should create it?
                # Or just error out? For safety, let's assume it should exist or we create it.
                # But creating it requires more fields (filename etc).
                # If it doesn't exist in DB, we can't set it as latest in DB easily without creating it.
                # Let's try to update if exists.
                if v:
                    # Set all others to false (admin logic does this, but here we do manual)
                    # Actually, if we use the same logic as Admin:
                    from sqlalchemy import update
                    await db.execute(update(IDEVersion).values(is_latest=False))
                    v.is_latest = True
                    if request.description:
                        v.description = request.description
                    await db.commit()
                else:
                    # If not in DB, we can't fulfill "store in DB".
                    # But maybe we should warn?
                    # For now, just print log.
                    print(f"Warning: Version {request.version} not found in DB, cannot set as latest in DB.")
        except Exception as e:
            print(f"Failed to update version in DB: {e}")

    # Keep legacy behavior for response consistency
    latest_version_info = {
        "version": request.version,
        "updated_at": updated_at,
        "description": description
    }
    
    return {
        "message": f"最新版本已更新为 {request.version}",
        "previous_version": DEFAULT_VERSION, # Note: This is now just a fallback reference, actual previous might be different
        "new_version": request.version,
        "updated_at": latest_version_info["updated_at"]
    }


@app.get("/version/latest")
@app.get("/api/version/latest")
async def get_latest_version_info():
    """获取最新版本的详细信息"""
    latest_version = await get_latest_ide_version()
    description = ""
    updated_at = datetime.now().isoformat()
    external_url = None

    if DB_ENABLED:
        try:
             async with AsyncSessionLocal() as db:
                 result = await db.execute(select(IDEVersion).where(IDEVersion.version == latest_version))
                 v = result.scalar_one_or_none()
                 if v:
                     description = v.description or ""
                     updated_at = v.updated_at.isoformat() if v.updated_at else updated_at
                     external_url = v.external_url
        except Exception as e:
            print(f"获取版本详情失败: {e}")
    
    # 获取版本文件信息
    version_dir = DOWNLOAD_BASE_DIR / latest_version
    file_info = []
    
    if version_dir.exists():
        exe_files = list(version_dir.glob("*.exe"))
        for exe_file in exe_files:
            if exe_file.exists():
                stat = exe_file.stat()
                file_info.append({
                    "filename": exe_file.name,
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
    
    # 如果本地没有文件且没有外部链接，尝试自动检测（兼容旧逻辑）
    if not file_info and not external_url:
        if not version_dir.exists():
            # 如果设置的最新版本不存在，尝试从目录中自动获取
            auto_latest = get_latest_available_version()
            if auto_latest:
                latest_version = auto_latest
                version_dir = DOWNLOAD_BASE_DIR / latest_version
                description = f"自动检测到的最新版本 {latest_version}"
                
                # 重新扫描文件
                if version_dir.exists():
                    exe_files = list(version_dir.glob("*.exe"))
                    for exe_file in exe_files:
                        if exe_file.exists():
                            stat = exe_file.stat()
                            file_info.append({
                                "filename": exe_file.name,
                                "size_bytes": stat.st_size,
                                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
                            })
            else:
                raise HTTPException(
                    status_code=404,
                    detail="没有找到可用的版本文件"
                )
        else:
             if not file_info:
                 raise HTTPException(
                    status_code=404,
                    detail=f"最新版本 {latest_version} 下没有找到可执行文件"
                )
    
    return {
        "version": latest_version,
        "description": description,
        "updated_at": updated_at,
        "files": file_info,
        "download_url": external_url if external_url else f"/download/latest"
    }


@app.get("/version/check")
@app.get("/api/version/check")
async def check_version_update():
    """检查版本更新"""
    latest_version = await get_latest_ide_version()
    
    external_url = None
    if DB_ENABLED:
        try:
             async with AsyncSessionLocal() as db:
                 result = await db.execute(select(IDEVersion).where(IDEVersion.version == latest_version))
                 v = result.scalar_one_or_none()
                 if v:
                     external_url = v.external_url
        except Exception as e:
            print(f"获取版本详情失败: {e}")

    # 获取可用版本列表
    available_versions = []
    if DOWNLOAD_BASE_DIR.exists():
        for version_dir in DOWNLOAD_BASE_DIR.iterdir():
            if version_dir.is_dir():
                exe_files = list(version_dir.glob("*.exe"))
                if exe_files:
                    available_versions.append(version_dir.name)
    
    # 按版本号排序
    available_versions.sort(key=lambda v: [int(x) for x in re.sub(r'[^\d.]', '', v).split('.') if x.isdigit()], reverse=True)
    
    # 返回检查结果
    return {
        "current_version": DEFAULT_VERSION, # 仅作参考或兼容
        "latest_version": latest_version,
        "available_versions": available_versions,
        "has_update": latest_version != DEFAULT_VERSION if latest_version else False, 
        "download_url": external_url if external_url else (f"/download/latest" if latest_version else None)
    }


@app.get("/version/{version}/changelog")
@app.get("/api/version/{version}/changelog")
async def get_version_changelog(version: str):
    """获取指定版本的更新日志"""
    try:
        if not version or any(x in version for x in ("/", "\\", "..")):
            raise HTTPException(status_code=400, detail="版本号不合法")

        candidates = [version]
        normalized = re.sub(r"^[vV]\s*", "", version).strip()
        if normalized and normalized != version:
            candidates.append(normalized)

        changelog_path = None
        for v in candidates:
            p = DOWNLOAD_BASE_DIR / v / "UpdateLog.md"
            if p.exists():
                changelog_path = p
                version = v
                break
        
        # 检查文件是否存在
        if not changelog_path:
            raise HTTPException(status_code=404, detail=f"版本 {version} 的更新日志不存在")
        
        # 读取更新日志内容
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_content = f.read()
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试其他编码
            with open(changelog_path, 'r', encoding='gbk') as f:
                changelog_content = f.read()
        
        return {
            "success": True,
            "data": {                   
                "version": version,
                "changelog": changelog_content,
                "file_path": str(changelog_path)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }






@app.get("/changelog/latest")
async def get_latest_changelog():
    """获取最新版本的更新日志"""
    try:
        latest_version = get_latest_available_version()
        
        if latest_version is None:
            raise HTTPException(status_code=404, detail="没有可用的版本")
        
        # 构建更新日志文件路径
        changelog_path = DOWNLOAD_BASE_DIR / latest_version / "UpdateLog.md"
        
        # 检查文件是否存在
        if not changelog_path.exists():
            raise HTTPException(status_code=404, detail=f"最新版本 {latest_version} 的更新日志不存在")
        
        # 读取更新日志内容
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_content = f.read()
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试其他编码
            with open(changelog_path, 'r', encoding='gbk') as f:
                changelog_content = f.read()
        
        return {
            "success": True,
            "data": {
                "version": latest_version,
                "changelog": changelog_content,
                "file_path": str(changelog_path)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/changelogs")
async def get_all_changelogs():
    """获取所有版本的更新日志（仅返回存在UpdateLog.md的版本）"""
    try:
        changelogs = []
        
        if not DOWNLOAD_BASE_DIR.exists():
            return {"success": True, "data": [], "count": 0}
        
        # 遍历download目录下的所有版本文件夹
        for version_dir in DOWNLOAD_BASE_DIR.iterdir():
            if version_dir.is_dir():
                changelog_path = version_dir / "UpdateLog.md"
                if changelog_path.exists():
                    # 读取更新日志内容，兼容编码
                    try:
                        with open(changelog_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        with open(changelog_path, 'r', encoding='gbk') as f:
                            content = f.read()
                    
                    changelogs.append({
                        "version": version_dir.name,
                        "changelog": content,
                        "file_path": str(changelog_path)
                    })
        
        # 按版本号倒序排序
        changelogs.sort(
            key=lambda item: [int(x) for x in re.sub(r'[^\d.]', '', item['version']).split('.') if x.isdigit()],
            reverse=True
        )
        
        return {
            "success": True,
            "data": changelogs,
            "count": len(changelogs)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }




@app.get("/websocket/clients")
async def get_connected_clients():
    """获取当前连接的客户端列表"""
    try:
        client_list = []
        for client_id, websocket in manager.active_connections.items():
            client_info = {
                "client_id": client_id,
                "connected_at": clients[client_id].connect_time.isoformat() if client_id in clients else "未知",
                "last_heartbeat": clients[client_id].last_heartbeat.isoformat() if client_id in clients else "未知",
                "state": "connected"
            }
            client_list.append(client_info)
        
        return {
            "success": True,
            "total_clients": len(client_list),
            "clients": client_list,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取客户端列表失败: {str(e)}")


# 密钥池配置已迁移至 key_pool_config.py，并存储在数据库中
# 原有的 MemoryKeyPoolManager 类及其相关逻辑已移除
# 所有密钥管理功能现在通过 key_pool_service.py 和数据库实现

@app.get("/model/keys/status")
async def get_key_pool_status():
    """获取密钥池状态"""
    try:
        if not DB_ENABLED:
            return {
                "success": False,
                "error": "数据库未启用"
            }

        async with AsyncSessionLocal() as db:
            status = await key_pool_service.get_key_pool_status(db)
            return {
                "success": True,
                "data": status
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/model/keys/allocate")
async def allocate_model_config(request: ModelConfigRequest):
    """为指定客户端分配模型配置"""
    try:
        client_id = request.client_id
        
        # 检查客户端是否存在，如果不存在则创建一个临时客户端记录
        if client_id not in clients:
            # 创建临时客户端记录用于测试
            clients[client_id] = ClientInfo(
                client_id=client_id,
                connect_time=datetime.now(),
                last_heartbeat=datetime.now(),
                is_online=False,
                websocket=None
            )
        
        # 为客户端分配密钥
        allocated_keys = {}
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                active_providers = await key_pool_service.get_active_providers(db)
                for provider in active_providers:
                    api_key = await key_pool_service.allocate_key_for_client(db, provider.name, client_id)
                    if api_key:
                        allocated_keys[provider.name] = api_key
        
        if not allocated_keys:
            raise HTTPException(status_code=503, detail="密钥池已满，无法分配新的模型配置")
        
        return {
            "success": True,
            "data": {
                "client_id": client_id,
                "allocated_keys": allocated_keys,
                "message": f"成功为客户端 {client_id} 分配模型配置"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/usage/model")
async def record_client_model_usage(payload: ModelUsageRecordRequest, request: Request):
    if not DB_ENABLED:
        return {"success": True}

    client_ip = request.client.host if request.client else None
    client_id = request.headers.get("x-client-id") or "api"

    key_hash = hashlib.sha256(payload.api_key.encode("utf-8")).hexdigest()
    key_tail = payload.api_key[-4:] if len(payload.api_key) >= 4 else payload.api_key
    usage_detail = f"model={payload.model_name};key_hash={key_hash};key_tail={key_tail}"
    if len(usage_detail) > 200:
        usage_detail = usage_detail[:200]

    model_access = None
    async with AsyncSessionLocal() as db:
        user = await user_service.get_or_create_user(
            db,
            payload.user_id,
            touch_last_seen=True,
            increment_connections=False
        )
        log = UsageLog(
            user_id=user.id,
            client_id=client_id,
            usage_type="model_use",
            usage_detail=usage_detail,
            request_ip=client_ip
        )
        db.add(log)
        await db.commit()

        model_access = await user_service.increment_model_usage(db, payload.user_id, inc=1)

        if model_access and model_access.get("just_disabled"):
            await key_pool_service.release_key_for_user(db, payload.user_id)

    if model_access and model_access.get("just_disabled"):
        placeholder_providers = {}
        if DB_ENABLED:
            async with AsyncSessionLocal() as db:
                active_providers_list = await key_pool_service.get_active_providers(db)
                placeholder_providers = {
                    p.name: {
                        "api_key": "DISABLED",
                        "base_url": p.base_url or "",
                    }
                    for p in active_providers_list
                }
        await manager.send_to_user(
            payload.user_id,
            {
                "type": "model_config_update",
                "timestamp": datetime.now().isoformat(),
                "model_providers": placeholder_providers,
            },
        )
        await manager.send_to_user(
            payload.user_id,
            {
                "type": "model_access_update",
                "enabled": False,
                "used": model_access.get("used"),
                "limit": model_access.get("limit"),
                "reason": model_access.get("disabled_reason"),
                "timestamp": datetime.now().isoformat(),
            },
        )

    response = {"success": True}
    if model_access:
        response["model_access"] = {
            "enabled": model_access.get("enabled"),
            "used": model_access.get("used"),
            "limit": model_access.get("limit"),
            "reason": model_access.get("disabled_reason"),
        }
    return response


@app.get("/api/usage/model/access")
async def get_model_access_status(user_id: str):
    if not DB_ENABLED:
        return {"success": True, "data": {"enabled": True}}

    async with AsyncSessionLocal() as db:
        status = await user_service.get_model_access_status(db, user_id)
        if not status:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"success": True, "data": status}


@app.post("/api/upload/image")
async def upload_image(request: Request, file: UploadFile = File(...), user_id: Optional[str] = None, timestamp: Optional[str] = None, sn: Optional[str] = None):
    user_id = user_id or request.query_params.get("uid") or request.headers.get("x-user-id")
    timestamp = timestamp or request.query_params.get("ts") or request.headers.get("x-timestamp")
    sn = sn or request.query_params.get("signature")

    if not user_id or not sn:
        raise HTTPException(status_code=400, detail="缺少 user_id 或 sn")

    if not verify_image_upload_sn(user_id=str(user_id), sn=str(sn), timestamp=str(timestamp) if timestamp else None):
        raise HTTPException(status_code=401, detail="sn 无效或已过期")

    if not file:
        raise HTTPException(status_code=400, detail="缺少文件")

    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="仅支持图片上传")

    original_suffix = Path(file.filename or "").suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", original_suffix or ""):
        original_suffix = ""

    if not original_suffix:
        if content_type == "image/jpeg":
            original_suffix = ".jpg"
        elif content_type == "image/png":
            original_suffix = ".png"
        elif content_type == "image/gif":
            original_suffix = ".gif"
        elif content_type == "image/webp":
            original_suffix = ".webp"
        elif content_type == "image/bmp":
            original_suffix = ".bmp"
        else:
            original_suffix = ".png"

    max_bytes = 10 * 1024 * 1024
    total = 0
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="图片过大")
        buf.extend(chunk)

    endpoint_env = os.getenv("ALIYUN_OSS_ENDPOINT", "").strip()
    public_endpoint_env = os.getenv("ALIYUN_OSS_PUBLIC_ENDPOINT", "").strip()

    bucket = get_oss_client(endpoint_override=endpoint_env)
    if not bucket:
        raise HTTPException(status_code=500, detail="OSS 未配置或依赖缺失")

    prefix = os.getenv("ALIYUN_OSS_PREFIX", "ide").strip().strip("/")
    date_part = datetime.now().strftime("%Y%m%d")
    object_key = f"{prefix}/temp/{date_part}/{user_id}/{uuid.uuid4().hex}{original_suffix}"

    try:
        import oss2
        headers = {"Content-Type": file.content_type} if file.content_type else None
        result = await asyncio.to_thread(bucket.put_object, object_key, bytes(buf), headers=headers)
        if getattr(result, "status", 500) >= 400:
            raise HTTPException(status_code=500, detail="上传 OSS 失败")
    except Exception as e:
        is_internal = "-internal." in endpoint_env
        if is_internal:
            retry_endpoint = public_endpoint_env or endpoint_env.replace("-internal.", ".")
            retry_bucket = get_oss_client(endpoint_override=retry_endpoint)
            if retry_bucket:
                try:
                    result = await asyncio.to_thread(retry_bucket.put_object, object_key, bytes(buf), headers=headers)
                    if getattr(result, "status", 500) < 400:
                        url = build_oss_signed_get_url(object_key) or build_oss_public_url(object_key)
                        if not url:
                            raise HTTPException(status_code=500, detail="OSS URL 生成失败")
                        return {"url": url}
                except Exception:
                    pass
        if isinstance(e, HTTPException):
            raise e
        try:
            import oss2
            if isinstance(e, getattr(oss2.exceptions, "OssError", Exception)):
                parts = []
                code = getattr(e, "code", None)
                status = getattr(e, "status", None)
                request_id = getattr(e, "request_id", None)
                msg = getattr(e, "message", None)
                if status:
                    parts.append(str(status))
                if code:
                    parts.append(str(code))
                if request_id:
                    parts.append(f"request_id={request_id}")
                if msg:
                    parts.append(str(msg))
                detail = "上传 OSS 失败"
                if parts:
                    detail = f"{detail}: {' '.join(parts)}"
                raise HTTPException(status_code=500, detail=detail)
        except HTTPException:
            raise
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"上传 OSS 失败: {str(e)}")

    url = build_oss_signed_get_url(object_key) or build_oss_public_url(object_key)
    if not url:
        raise HTTPException(status_code=500, detail="OSS URL 生成失败")

    return {"url": url}


@app.post("/api/web_search", response_model=WebSearchResponse)
async def web_search_endpoint(payload: WebSearchRequest):   
    if not verify_web_search_auth(payload.user_id, payload.timestamp, payload.auth):
        raise HTTPException(status_code=401, detail="web_search 认证失败或已过期")

    # 规范化引擎列表
    engines = payload.engines or WEB_SEARCH_DEFAULT_ENGINES
    normalized: List[str] = []
    seen = set()
    for e in engines:
        name = (e or "").lower()
        if name in seen:
            continue
        if name in WEB_SEARCH_DEFAULT_ENGINES:
            normalized.append(name)
            seen.add(name)
    if not normalized:
        normalized = WEB_SEARCH_DEFAULT_ENGINES.copy()

    raw_results = await perform_web_search(
        query=payload.query,
        engines=normalized,
        limit=payload.limit,
    )

    results = [
        SearchResult(
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            description=str(item.get("description", "")),
            engine=str(item.get("engine", "")),
        )
        for item in raw_results
    ]

    return WebSearchResponse(
        query=payload.query,
        engines=normalized,
        total=len(results),
        results=results,
    )


# ============================================
# 前端静态文件服务 (必须放在最后)
# ============================================

# 前端构建目录
STATIC_DIR = Path(__file__).parent / "static"

@app.get("/assets/{file_path:path}")
async def assets_static(file_path: str):
    """前端静态资源 (assets目录)"""
    file = STATIC_DIR / "assets" / file_path
    if file.exists() and file.is_file():
        suffix = file.suffix.lower()
        content_type = MIME_TYPES.get(suffix, "application/octet-stream")
        return FileResponse(file, media_type=content_type)
    return HTMLResponse(content="Not Found", status_code=404)

@app.get("/{file_path:path}")
async def main_static(file_path: str):
    """前端页面 (SPA路由支持)"""
    # 排除已知的API前缀
    if file_path.startswith("api/") or file_path.startswith("admin") or file_path.startswith("ws") or file_path.startswith("changelog"):
        # 如果是API路径但没匹配到前面的路由，说明是404
        if file_path.startswith("api/") or file_path.startswith("changelog"):
            raise HTTPException(status_code=404, detail="Not Found")
        pass
    
    # 尝试直接访问文件
    file = STATIC_DIR / file_path
    
    # 如果文件不存在，或者请求的是目录，或者请求的是根路径，则返回index.html
    if not file.exists() or not file.is_file():
        # 如果是已知后缀的静态资源请求但不存在，返回404
        if any(file_path.endswith(ext) for ext in MIME_TYPES.keys()):
             return HTMLResponse(content="Not Found", status_code=404)
        
        # 否则返回index.html (SPA)
        file = STATIC_DIR / "index.html"
    
    if file.exists() and file.is_file():
        suffix = file.suffix.lower()
        content_type = MIME_TYPES.get(suffix, "text/html")
        return FileResponse(file, media_type=content_type)
    
    return HTMLResponse(content="<h1>前端未构建，请运行: cd frontend && npm run build</h1>", status_code=404)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=18016)
