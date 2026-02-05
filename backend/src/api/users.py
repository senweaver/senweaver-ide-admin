"""
用户管理API路由
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc, and_, or_
from pydantic import BaseModel, ConfigDict

from src.core.database import get_db
from src.models.models import User, Order, Transaction, UsageLog, UserStatus, OrderStatus, TransactionType, PaymentMethod, UserModelAccess
from src.api.admin import verify_token
from src.services.user_service import user_service
from src.services.key_pool_service import key_pool_service
from src.core.connection_manager import clients as ws_clients, manager as ws_manager

router = APIRouter(prefix="/api/admin/users", tags=["User Management"])


# ============ 请求/响应模型 ============
class UserListResponse(BaseModel):
    id: int
    user_id: str
    nickname: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    balance: float
    total_recharge: float
    total_consume: float
    total_connections: int
    total_online_duration: int
    status: str
    is_vip: bool
    first_seen_at: str
    last_seen_at: str
    
    # Model Access Info
    model_enabled: bool = True
    model_used: int = 0
    model_used_total: int = 0
    model_limit: int = 1000
    model_reset_days: int = 30
    model_last_reset_time: Optional[str] = None

    model_config = ConfigDict(protected_namespaces=())


class UserDetailResponse(UserListResponse):
    total_messages: int
    total_api_calls: int
    vip_expire_at: Optional[str]
    created_at: str


class RechargeRequest(BaseModel):
    amount: float
    remark: Optional[str] = None


class AdjustBalanceRequest(BaseModel):
    amount: float  # 正数增加，负数减少
    remark: str


class UpdateUserRequest(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    is_vip: Optional[bool] = None
    vip_days: Optional[int] = None  # VIP天数


class ModelAccessUpdateRequest(BaseModel):
    user_id: str
    enabled: bool
    usage_limit: Optional[int] = None
    reset_used: bool = False
    reason: Optional[str] = None


# ============ API端点 ============

async def notify_user_update(db: AsyncSession, user_id: int):
    """
    通知管理员用户数据更新
    """
    # 查询用户和模型权限
    query = select(User, UserModelAccess).outerjoin(UserModelAccess, User.id == UserModelAccess.user_id).where(User.id == user_id)
    result = await db.execute(query)
    row = result.first()
    
    if not row:
        return
        
    u, ma = row
    
    # 获取在线信息
    from connection_manager import clients as ws_clients, manager as ws_manager
    active_client_ids = set(ws_manager.active_connections.keys())
    
    online_info = None
    is_online = False
    
    if u.user_id:
        # 查找该用户的在线连接
        for cid, info in ws_clients.items():
            if cid in active_client_ids and str(info.user_id) == str(u.user_id):
                online_info = {
                    "client_id": cid,
                    "ip": info.ip,
                    "connected_at": info.connect_time.isoformat(),
                    "user_agent": info.user_agent
                }
                is_online = True
                break
    
    # 构建数据对象 (与 UserListResponse 保持一致)
    user_data = {
        "id": u.id,
        "user_id": u.user_id,
        "nickname": u.nickname,
        "email": u.email,
        "phone": u.phone,
        "balance": float(u.balance or 0),
        "total_recharge": float(u.total_recharge or 0),
        "total_consume": float(u.total_consume or 0),
        "total_connections": u.total_connections,
        "total_online_duration": u.total_online_duration,
        "status": u.status.value if u.status else "active",
        "is_vip": u.is_vip,
        "first_seen_at": u.first_seen_at.isoformat() if u.first_seen_at else None,
        "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
        
        # Model Access Info
        "model_enabled": ma.enabled if ma else True,
        "model_used": ma.used_count if ma else 0,
        "model_used_total": ma.used_total if ma else 0,
        "model_limit": ma.usage_limit if ma else 1000,
        "model_reset_days": ma.reset_period_days if ma else 30,
        "model_last_reset_time": ma.last_reset_time.isoformat() if ma and ma.last_reset_time else None,
        
        # Online Status
        "is_online": is_online,
        "online_info": online_info
    }
    
    # 广播消息
    await ws_manager.broadcast_admin({
        "type": "user_update",
        "user": user_data
    })


@router.get("")
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    is_vip: Optional[bool] = None,
    sort_by: str = "last_seen_at",
    sort_order: str = "desc",
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户列表"""
    # 基础查询，关联 UserModelAccess
    query = select(User, UserModelAccess).outerjoin(UserModelAccess, User.id == UserModelAccess.user_id)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                User.user_id.like(search_pattern),
                User.nickname.like(search_pattern),
                User.email.like(search_pattern),
                User.phone.like(search_pattern)
            )
        )
    
    if status:
        query = query.where(User.status == UserStatus(status))
    
    if is_vip is not None:
        query = query.where(User.is_vip == is_vip)
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # 排序
    sort_column = getattr(User, sort_by, User.last_seen_at)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)
    
    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    rows = result.all()
    
    # 获取在线状态
    from connection_manager import clients as ws_clients, manager as ws_manager
    active_client_ids = set(ws_manager.active_connections.keys())
    
    online_user_map = {}
    for cid, info in ws_clients.items():
        if cid in active_client_ids and info.user_id:
            online_user_map[str(info.user_id)] = {
                "client_id": cid,
                "ip": info.ip,
                "connected_at": info.connect_time.isoformat(),
                "user_agent": info.user_agent
            }

    return {
        "items": [
            {
                "id": u.id,
                "user_id": u.user_id,
                "nickname": u.nickname,
                "email": u.email,
                "phone": u.phone,
                "balance": float(u.balance or 0),
                "total_recharge": float(u.total_recharge or 0),
                "total_consume": float(u.total_consume or 0),
                "total_connections": u.total_connections,
                "total_online_duration": u.total_online_duration,
                "status": u.status.value if u.status else "active",
                "is_vip": u.is_vip,
                "first_seen_at": u.first_seen_at.isoformat() if u.first_seen_at else None,
                "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
                
                # Model Access Info
                "model_enabled": ma.enabled if ma else True,
                "model_used": ma.used_count if ma else 0,
                "model_used_total": ma.used_total if ma else 0,
                "model_limit": ma.usage_limit if ma else 1000,
                "model_reset_days": ma.reset_period_days if ma else 30,
                "model_last_reset_time": ma.last_reset_time.isoformat() if ma and ma.last_reset_time else None,
                
                # Online Status
                "is_online": str(u.user_id) in online_user_map,
                "online_info": online_user_map.get(str(u.user_id))
            }
            for u, ma in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/online")
async def get_online_users(
    request: Request,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取当前在线用户"""
    from connection_manager import clients as imported_clients
    from datetime import datetime
    
    # 优先从 app.state 获取 clients，保证是全局唯一的对象
    clients = getattr(request.app.state, "clients", imported_clients)
    manager = getattr(request.app.state, "manager", None)
    
    # 如果无法从state获取manager，尝试导入
    if not manager:
        from connection_manager import manager
    
    # 获取当前活跃连接ID集合，以此为准
    active_client_ids = set(manager.active_connections.keys())
    
    # 收集所有连接过的用户（包括在线和离线）
    connected_user_ids = set()
    online_info = {}
    
    for client_id, client_info in clients.items():
        # 只处理当前活跃的连接
        if client_id not in active_client_ids:
            continue
            
        # 使用真实user_id，如果没有则使用带有前缀的client_id作为临时ID，确保能显示
        uid = client_info.user_id or f"anon_{client_id}"
        connected_user_ids.add(uid)
        
        current_info = {
            "client_id": client_id,
            "connect_time": client_info.connect_time.isoformat(),
            "last_heartbeat": client_info.last_heartbeat.isoformat(),
            "ip": client_info.ip,
            "user_agent": client_info.user_agent,
            "is_online": True # 既然在active_connections中，肯定在线
        }
        
        # 如果该用户尚未记录，或者当前心跳更新，则更新信息
        should_update = False
        if uid not in online_info:
            should_update = True
        else:
            # 比较心跳时间，取较新的
            stored_heartbeat = datetime.fromisoformat(online_info[uid]["last_heartbeat"])
            if client_info.last_heartbeat > stored_heartbeat:
                should_update = True
        
        if should_update:
            online_info[uid] = current_info
    
    if not connected_user_ids:
        # 即使没有识别到用户ID，如果有客户端连接，也尝试显示（调试用）
        if clients:
            # 构造匿名用户显示
            items = []
            for cid, info in clients.items():
                 # 只显示在线的
                 if cid not in active_client_ids:
                     continue
                     
                 items.append({
                    "id": 0,
                    "user_id": f"anon_{cid}",
                    "nickname": f"Anonymous ({cid[:8]})",
                    "balance": 0.0,
                    "is_vip": False,
                    "ip": info.ip,
                    "user_agent": info.user_agent,
                    "connected_at": info.connect_time.isoformat(),
                    "online_info": {
                        "client_id": cid,
                        "connect_time": info.connect_time.isoformat(),
                        "last_heartbeat": info.last_heartbeat.isoformat(),
                        "ip": info.ip,
                        "user_agent": info.user_agent,
                        "is_online": True
                    }
                 })
            return items
            
        return []
    
    result = await db.execute(
        select(User).where(User.user_id.in_(connected_user_ids))
    )
    users = result.scalars().all()
    
    # 转换为字典方便查找
    db_user_map = {u.user_id: u for u in users}
    
    final_items = []
    # 遍历所有收集到的 user_id，确保即使数据库没有记录也能显示
    for user_id in connected_user_ids:
        u = db_user_map.get(user_id)
        online_data = online_info.get(user_id, {})
        
        if u:
            item = {
                "id": u.id,
                "user_id": u.user_id,
                "nickname": u.nickname,
                "balance": float(u.balance or 0),
                "is_vip": u.is_vip,
                "ip": online_data.get("ip"),
                "user_agent": online_data.get("user_agent"),
                "connected_at": online_data.get("connect_time"),
                "online_info": online_data
            }
        else:
            # 数据库中无记录，构造临时显示对象
            item = {
                "id": 0,
                "user_id": user_id,
                "nickname": f"Unknown ({user_id})",
                "balance": 0.0,
                "is_vip": False,
                "ip": online_data.get("ip"),
                "user_agent": online_data.get("user_agent"),
                "connected_at": online_data.get("connect_time"),
                "online_info": online_data
            }
        final_items.append(item)
    
    return final_items


@router.get("/stats")
async def get_user_stats(
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户统计"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # 总用户数
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0
    
    # 活跃用户
    result = await db.execute(
        select(func.count(User.id)).where(User.status == UserStatus.ACTIVE)
    )
    active_users = result.scalar() or 0
    
    # VIP用户
    result = await db.execute(
        select(func.count(User.id)).where(User.is_vip == True)
    )
    vip_users = result.scalar() or 0
    
    # 今日新增
    result = await db.execute(
        select(func.count(User.id)).where(User.first_seen_at >= today)
    )
    today_new = result.scalar() or 0
    
    # 本周活跃
    result = await db.execute(
        select(func.count(User.id)).where(User.last_seen_at >= week_ago)
    )
    week_active = result.scalar() or 0
    
    # 本月活跃
    result = await db.execute(
        select(func.count(User.id)).where(User.last_seen_at >= month_ago)
    )
    month_active = result.scalar() or 0
    
    # 总余额
    result = await db.execute(select(func.sum(User.balance)))
    total_balance = float(result.scalar() or 0)
    
    # 总充值
    result = await db.execute(select(func.sum(User.total_recharge)))
    total_recharge = float(result.scalar() or 0)
    
    # 总消费
    result = await db.execute(select(func.sum(User.total_consume)))
    total_consume = float(result.scalar() or 0)
    
    # 当前在线
    from main import manager
    online_count = len(manager.active_connections)
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "vip_users": vip_users,
        "today_new": today_new,
        "week_active": week_active,
        "month_active": month_active,
        "online_count": online_count,
        "total_balance": total_balance,
        "total_recharge": total_recharge,
        "total_consume": total_consume
    }


@router.get("/vip")
async def get_vip_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取VIP用户列表"""
    query = select(User).where(User.is_vip == True)
    
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    query = query.order_by(desc(User.vip_expire_at))
    query = query.offset((page - 1) * size).limit(size)
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {
        "items": [
            {
                "id": u.id,
                "user_id": u.user_id,
                "username": u.nickname or u.user_id,
                "email": u.email,
                "vip_level": 1,
                "vip_expire_at": u.vip_expire_at.isoformat() if u.vip_expire_at else None,
                "balance": float(u.balance or 0)
            }
            for u in users
        ],
        "total": total
    }


@router.get("/model-access")
async def get_user_model_access(
    user_id: str,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    status = await user_service.get_model_access_status(db, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "data": status}


@router.get("/{user_id}")
async def get_user_detail(
    user_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户详情"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return {
        "id": user.id,
        "user_id": user.user_id,
        "nickname": user.nickname,
        "email": user.email,
        "phone": user.phone,
        "avatar": user.avatar,
        "balance": float(user.balance or 0),
        "total_recharge": float(user.total_recharge or 0),
        "total_consume": float(user.total_consume or 0),
        "total_connections": user.total_connections,
        "total_online_duration": user.total_online_duration,
        "total_messages": user.total_messages,
        "total_api_calls": user.total_api_calls,
        "status": user.status.value if user.status else "active",
        "is_vip": user.is_vip,
        "vip_expire_at": user.vip_expire_at.isoformat() if user.vip_expire_at else None,
        "first_seen_at": user.first_seen_at.isoformat() if user.first_seen_at else None,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """更新用户信息"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    update_data = request.model_dump(exclude_unset=True)
    
    if "status" in update_data:
        update_data["status"] = UserStatus(update_data["status"])
    
    if "vip_days" in update_data:
        days = update_data.pop("vip_days")
        if days and days > 0:
            user.is_vip = True
            if user.vip_expire_at and user.vip_expire_at > datetime.now():
                user.vip_expire_at = user.vip_expire_at + timedelta(days=days)
            else:
                user.vip_expire_at = datetime.now() + timedelta(days=days)
    
    for key, value in update_data.items():
        setattr(user, key, value)
    
    await db.commit()
    
    # 通知管理员用户数据更新
    await notify_user_update(db, user_id)
    
    return {"success": True, "message": "用户信息已更新"}


@router.post("/{user_id}/toggle")
async def toggle_user_status(
    user_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """切换用户状态（启用/禁用）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 查找该用户的活跃连接
    # 增加调试日志和更宽松的匹配逻辑
    print(f"DEBUG: 正在尝试更新用户 {user.user_id} (DB ID: {user_id}) 的连接状态")
    
    active_client_ids = []
    target_user_id = str(user.user_id).strip()
    target_db_id = str(user.id)
    
    for cid, info in ws_clients.items():
        if cid in ws_manager.active_connections:
            client_user_id = str(info.user_id).strip() if info.user_id else ""
            
            # 匹配业务 user_id 或 数据库 ID
            if client_user_id and (client_user_id == target_user_id or client_user_id == target_db_id):
                active_client_ids.append(cid)
                print(f"DEBUG: 找到匹配连接 {cid} (Client UserID: {info.user_id})")

    print(f"DEBUG: 共找到 {len(active_client_ids)} 个需要更新的连接")
    
    # 获取活跃的提供商列表
    active_providers_list = await key_pool_service.get_active_providers(db)
    active_providers = {p.name: p for p in active_providers_list}
    
    # 切换状态
    if user.status == UserStatus.ACTIVE:
        user.status = UserStatus.BANNED  # 禁用
        action = "禁用"
        
        # 发送禁用消息，不强制断开
        for cid in active_client_ids:
            # 1. 推送 model_access_update
            await ws_manager.send_to_client(cid, {
                "type": "model_access_update",
                "enabled": False,
                "used": 0, 
                "used_total": 0,
                "limit": 0,
                "reset_days": 30,
                "last_reset_time": None,
                "reason": "您的账号已被禁用",
                "timestamp": datetime.now().isoformat()
            })
            
            # 2. 推送 model_config_update (Key -> DISABLED)
            await ws_manager.send_to_client(cid, {
                "type": "model_config_update",
                "timestamp": datetime.now().isoformat(),
                "model_providers": {
                    p_name: {
                        "api_key": "DISABLED",
                        "base_url": p_info.base_url or ""
                    } for p_name, p_info in active_providers.items()
                }
            })
            
            # 3. 释放之前分配的 key
            await key_pool_service.release_key_for_client(db, cid)
            
            print(f"DEBUG: 已向连接 {cid} 推送禁用状态")
            
    else:
        user.status = UserStatus.ACTIVE  # 启用
        action = "启用"
        
        # 刷新状态以便后续查询
        await db.flush()
        
        # 获取最新的模型访问状态 (包括 usage limit 等)
        status_info = await user_service.get_model_access_status(db, target_user_id)
        is_model_enabled = status_info.get("enabled", True) if status_info else True
        
        for cid in active_client_ids:
             # 1. 分配密钥 (仅当模型权限允许时)
             allocated_keys = {}
             if is_model_enabled:
                 for p_name in active_providers.keys():
                     # 为该客户端重新分配 key
                     key = await key_pool_service.allocate_key_for_client(db, p_name, cid, target_user_id)
                     if key:
                         allocated_keys[p_name] = key
             
             # 2. 推送 model_access_update (恢复正常状态)
             await ws_manager.send_to_client(cid, {
                "type": "model_access_update",
                "enabled": is_model_enabled,
                "used": status_info.get("used", 0) if status_info else 0,
                "used_total": status_info.get("used_total", 0) if status_info else 0,
                "limit": status_info.get("limit", 1000) if status_info else 1000,
                "reset_days": status_info.get("reset_days", 30) if status_info else 30,
                "last_reset_time": status_info.get("last_reset_time") if status_info else None,
                "reason": status_info.get("disabled_reason") if status_info else None,
                "timestamp": datetime.now().isoformat()
            })

             # 3. 推送 model_config_update
             if is_model_enabled and allocated_keys:
                 await ws_manager.send_to_client(cid, {
                    "type": "model_config_update",
                    "timestamp": datetime.now().isoformat(),
                    "model_providers": {
                        p_name: {
                            "api_key": key,
                            "base_url": active_providers[p_name].base_url or ""
                        } for p_name, key in allocated_keys.items()
                    }
                })
             elif not is_model_enabled:
                 # 如果账户启用了，但模型权限还是禁用的 (如超额)，推送 DISABLED
                 await ws_manager.send_to_client(cid, {
                    "type": "model_config_update",
                    "timestamp": datetime.now().isoformat(),
                    "model_providers": {
                        p_name: {
                            "api_key": "DISABLED",
                            "base_url": p_info.base_url or ""
                        } for p_name, p_info in active_providers.items()
                    }
                })
             
             print(f"DEBUG: 已向连接 {cid} 推送启用状态 (Enabled: {is_model_enabled})")
    
    # 通知管理员用户数据更新
    await notify_user_update(db, user_id)
    
    return {
        "success": True, 
        "message": f"用户已{action}",
        "status": user.status.value
    }


@router.post("/{user_id}/recharge")
async def recharge_user(
    user_id: int,
    request: RechargeRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """为用户充值"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    amount = Decimal(str(request.amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于0")
    
    balance_before = user.balance or Decimal("0")
    balance_after = balance_before + amount
    
    # 更新用户余额
    user.balance = balance_after
    user.total_recharge = (user.total_recharge or Decimal("0")) + amount
    
    # 创建充值订单记录
    order = Order(
        order_no=f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
        user_id=user.id,
        order_type="recharge",
        product_name="后台充值",
        amount=amount,
        paid_amount=amount,
        payment_method=PaymentMethod.ADMIN,
        status=OrderStatus.PAID,
        paid_at=datetime.now(),
        remark=request.remark
    )
    db.add(order)
    await db.flush()  # 获取order.id

    # 创建交易记录
    transaction = Transaction(
        transaction_no=f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
        user_id=user.id,
        order_id=order.id,
        type=TransactionType.RECHARGE,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        description=f"管理员充值 ¥{amount}",
        remark=request.remark,
        operator=session.get("username", "admin")
    )
    db.add(transaction)
    
    await db.commit()
    
    # 通知管理员用户数据更新
    await notify_user_update(db, user_id)
    
    return {
        "success": True,
        "message": f"充值成功，当前余额：¥{balance_after}",
        "balance": float(balance_after)
    }


@router.post("/{user_id}/adjust-balance")
async def adjust_balance(
    user_id: int,
    request: AdjustBalanceRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """调整用户余额"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    amount = Decimal(str(request.amount))
    balance_before = user.balance or Decimal("0")
    balance_after = balance_before + amount
    
    if balance_after < 0:
        raise HTTPException(status_code=400, detail="调整后余额不能为负数")
    
    # 更新用户余额
    user.balance = balance_after
    
    # 创建交易记录
    trans_type = TransactionType.ADJUSTMENT
    transaction = Transaction(
        transaction_no=f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
        user_id=user.id,
        type=trans_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        description=f"余额调整 {'+' if amount > 0 else ''}{amount}",
        remark=request.remark,
        operator=session.get("username", "admin")
    )
    db.add(transaction)
    
    await db.commit()
    
    # 通知管理员用户数据更新
    await notify_user_update(db, user_id)
    
    return {
        "success": True,
        "message": f"余额调整成功，当前余额：¥{balance_after}",
        "balance": float(balance_after)
    }


@router.get("/{user_id}/transactions")
async def get_user_transactions(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户交易记录"""
    # 先通过user表的id查找
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    query = select(Transaction).where(Transaction.user_id == user_id)
    
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    query = query.order_by(desc(Transaction.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    return {
        "items": [
            {
                "id": t.id,
                "transaction_no": t.transaction_no,
                "type": t.type.value,
                "amount": float(t.amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "description": t.description,
                "remark": t.remark,
                "operator": t.operator,
                "created_at": t.created_at.isoformat()
            }
            for t in transactions
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{user_id}/usage")
async def get_user_usage(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    usage_type: Optional[str] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户使用记录"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    query = select(UsageLog).where(UsageLog.user_id == user_id)
    
    if usage_type:
        query = query.where(UsageLog.usage_type == usage_type)
    
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    query = query.order_by(desc(UsageLog.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "items": [
            {
                "id": log.id,
                "usage_type": log.usage_type,
                "usage_detail": log.usage_detail,
                "tokens_used": log.tokens_used,
                "cost": float(log.cost),
                "request_ip": log.request_ip,
                "request_duration": log.request_duration,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/model-access")
async def update_user_model_access(
    request: ModelAccessUpdateRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    status = await user_service.set_model_access(
        db,
        request.user_id,
        enabled=request.enabled,
        usage_limit=request.usage_limit,
        reset_used=request.reset_used,
        reason=request.reason,
    )
    if not status:
        raise HTTPException(status_code=404, detail="用户不存在")

    active_client_ids = [
        cid
        for cid, info in ws_clients.items()
        if info.user_id == request.user_id and cid in ws_manager.active_connections
    ]

    if not status.get("enabled"):
        providers = await key_pool_service.get_active_providers(db)
        for cid in active_client_ids:
            await key_pool_service.release_key_for_client(db, cid)
        await key_pool_service.release_key_for_user(db, request.user_id)

        for cid in active_client_ids:
            await ws_manager.send_to_client(
                cid,
                {
                    "type": "model_config_update",
                    "timestamp": datetime.now().isoformat(),
                    "model_providers": {
                        p.name: {
                            "api_key": "DISABLED",
                            "base_url": p.base_url or "",
                        }
                        for p in providers
                    },
                },
            )
    else:
        providers = await key_pool_service.get_active_providers(db)
        provider_map = {p.name: p for p in providers}

        for cid in active_client_ids:
            allocated_keys = {}
            for p in providers:
                api_key = await key_pool_service.allocate_key_for_client(
                    db,
                    p.name,
                    cid,
                    request.user_id,
                )
                if api_key:
                    allocated_keys[p.name] = api_key

            model_providers = {
                name: {
                    "api_key": api_key,
                    "base_url": provider_map[name].base_url or "",
                }
                for name, api_key in allocated_keys.items()
                if name in provider_map
            }
            await ws_manager.send_to_client(
                cid,
                {
                    "type": "model_config_update",
                    "timestamp": datetime.now().isoformat(),
                    "model_providers": model_providers,
                },
            )

    await ws_manager.send_to_user(
        request.user_id,
        {
            "type": "model_access_update",
            "enabled": status.get("enabled"),
            "used": status.get("used"),
            "limit": status.get("limit"),
            "reason": status.get("disabled_reason"),
            "timestamp": datetime.now().isoformat(),
        },
    )

    # 通知管理员用户数据更新
    # 需要先获取用户的数据库ID
    result = await db.execute(select(User).where(User.user_id == request.user_id))
    user = result.scalar_one_or_none()
    if user:
        await notify_user_update(db, user.id)

    return {
        "success": True,
        "data": status,
        "notified_clients": len(active_client_ids),
    }





@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除用户"""
    success = await user_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 广播删除消息
    await ws_manager.broadcast_admin({
        "type": "user_delete",
        "user_id": user_id
    })
    
    return {"success": True, "message": "用户已删除"}
