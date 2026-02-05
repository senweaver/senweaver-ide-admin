from typing import Dict, Optional, List
from datetime import datetime
import uuid
import json
import asyncio
from fastapi import WebSocket
from pydantic import BaseModel

class ClientInfo(BaseModel):
    client_id: str
    user_id: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    connect_time: datetime
    last_heartbeat: datetime
    is_online: bool
    is_admin: bool = False
    websocket: Optional[WebSocket] = None
    
    class Config:
        arbitrary_types_allowed = True

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.current_version = "2.8.0"  # 默认版本，启动后会被main.py更新
        self.version_update_event = asyncio.Event()

    async def trigger_version_update(self, version: str):
        """触发版本更新通知"""
        self.current_version = version
        self.version_update_event.set()

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None, ip: Optional[str] = None, user_agent: Optional[str] = None, is_admin: bool = False) -> str:
        """接受WebSocket连接并返回客户端ID"""
        await websocket.accept()
        client_id = str(uuid.uuid4())
        
        # 存储连接信息
        self.active_connections[client_id] = websocket
        
        # 创建客户端信息
        client_info = ClientInfo(
            client_id=client_id,
            user_id=user_id,
            ip=ip,
            user_agent=user_agent,
            connect_time=datetime.now(),
            last_heartbeat=datetime.now(),
            is_online=True,
            is_admin=is_admin,
            websocket=websocket
        )
        clients[client_id] = client_info
        
        print(f"客户端 {client_id} (用户ID: {user_id}, 管理员: {is_admin}) 已连接")
        return client_id

    def disconnect(self, client_id: str):
        """断开WebSocket连接"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        
        # 更新客户端状态为离线
        if client_id in clients:
            clients[client_id].is_online = False
            clients[client_id].websocket = None
            print(f"客户端 {client_id} 已断开连接")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

    async def send_heartbeat(self, client_id: str, message: dict):
        """发送心跳包给指定客户端"""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                await websocket.send_text(json.dumps(message))
                
                # 更新最后心跳时间
                if client_id in clients:
                    clients[client_id].last_heartbeat = datetime.now()
                
                return True
            except Exception as e:
                print(f"发送心跳包给客户端 {client_id} 失败: {e}")
                self.disconnect(client_id)
                return False
        return False

    async def send_to_client(self, client_id: str, message: dict) -> bool:
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                await websocket.send_text(json.dumps(message))
                return True
            except Exception as e:
                print(f"发送消息给客户端 {client_id} 失败: {e}")
                self.disconnect(client_id)
                return False
        return False

    async def send_to_user(self, user_id: str, message: dict) -> int:
        if not user_id:
            return 0
            
        count = 0
        message_str = json.dumps(message)
        
        # 查找该用户的所有活跃连接
        for cid, info in clients.items():
            if str(info.user_id) == str(user_id) and info.is_online and info.websocket:
                try:
                    await info.websocket.send_text(message_str)
                    count += 1
                except Exception as e:
                    print(f"向用户 {user_id} (Client: {cid}) 发送消息失败: {e}")
        
        return count

    async def broadcast_admin(self, message: dict):
        """向所有管理员广播消息"""
        message_str = json.dumps(message)
        for client_id, info in clients.items():
            if info.is_admin and info.is_online and info.websocket:
                try:
                    await info.websocket.send_text(message_str)
                except Exception as e:
                    print(f"向管理员 {client_id} 发送消息失败: {e}")
            
    async def broadcast_heartbeat(self, version: str):
        """广播心跳包"""
        message = {
            "type": "heartbeat",
            "version": version,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(json.dumps(message))

# 全局变量
clients: Dict[str, ClientInfo] = {}
manager = ConnectionManager()
