"""
用户统计服务 - 管理WebSocket连接统计和持久化
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from src.models.models import ConnectionLog, DailyStats, UserActivity
from src.services.user_service import user_service


class StatsService:
    """统计服务类"""
    
    def __init__(self):
        self.current_connections = 0
        self.peak_concurrent_today = 0
        self.connection_start_times: Dict[str, datetime] = {}
    
    async def log_connection(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """记录连接事件"""
        log = ConnectionLog(
            client_id=client_id,
            user_id=user_id,
            action="connect",
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(log)
        
        # 记录用户活动开始
        activity = UserActivity(
            user_id=user_id,
            client_id=client_id,
            connect_time=datetime.now(),
            ip_address=ip_address
        )
        db.add(activity)
        
        await db.commit()
        
        # 更新内存中的统计
        self.current_connections += 1
        self.connection_start_times[client_id] = datetime.now()
        
        if self.current_connections > self.peak_concurrent_today:
            self.peak_concurrent_today = self.current_connections
        
        # 更新每日统计
        await self._update_daily_stats(db, is_connect=True, user_id=user_id)
    
    async def log_disconnection(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: Optional[str] = None
    ):
        """记录断开连接事件"""
        log = ConnectionLog(
            client_id=client_id,
            user_id=user_id,
            action="disconnect"
        )
        db.add(log)
        
        # 更新用户活动结束时间
        disconnect_time = datetime.now()
        duration = 0
        
        if client_id in self.connection_start_times:
            start_time = self.connection_start_times[client_id]
            duration = int((disconnect_time - start_time).total_seconds())
            del self.connection_start_times[client_id]
        
        # 更新最近的用户活动记录
        result = await db.execute(
            select(UserActivity)
            .where(
                and_(
                    UserActivity.client_id == client_id,
                    UserActivity.disconnect_time.is_(None)
                )
            )
            .order_by(UserActivity.connect_time.desc())
            .limit(1)
        )
        activity = result.scalar_one_or_none()
        
        if activity:
            activity.disconnect_time = disconnect_time
            activity.duration_seconds = duration
        
        # 更新用户累计在线时长
        if user_id and duration > 0:
            await user_service.update_online_duration(db, user_id, duration)
        
        await db.commit()
        
        # 更新内存中的统计
        self.current_connections = max(0, self.current_connections - 1)
        
        # 更新每日统计
        await self._update_daily_stats(db, is_connect=False, duration=duration)
    
    async def log_heartbeat(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: Optional[str] = None
    ):
        """记录心跳事件"""
        log = ConnectionLog(
            client_id=client_id,
            user_id=user_id,
            action="heartbeat"
        )
        db.add(log)
        await db.commit()
    
    async def _update_daily_stats(
        self,
        db: AsyncSession,
        is_connect: bool = False,
        user_id: Optional[str] = None,
        duration: int = 0
    ):
        """更新每日统计"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 获取或创建今日统计记录
        result = await db.execute(
            select(DailyStats).where(DailyStats.date == today)
        )
        stats = result.scalar_one_or_none()
        
        if not stats:
            stats = DailyStats(
                date=today,
                total_connections=0,
                unique_users=0,
                peak_concurrent=0,
                total_duration_seconds=0,
                new_users=0,
                returning_users=0
            )
            db.add(stats)
        
        if is_connect:
            stats.total_connections += 1
            
            # 检查是否是新用户
            if user_id:
                yesterday = today - timedelta(days=1)
                result = await db.execute(
                    select(ConnectionLog)
                    .where(
                        and_(
                            ConnectionLog.user_id == user_id,
                            ConnectionLog.action == "connect",
                            ConnectionLog.created_at < today
                        )
                    )
                    .limit(1)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    stats.returning_users += 1
                else:
                    stats.new_users += 1
        
        # 更新峰值
        if self.current_connections > stats.peak_concurrent:
            stats.peak_concurrent = self.current_connections
        
        # 累加在线时长
        stats.total_duration_seconds += duration
        
        await db.commit()
    
    async def update_unique_users(self, db: AsyncSession):
        """更新今日独立用户数"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        from sqlalchemy import func, distinct
        
        result = await db.execute(
            select(func.count(distinct(ConnectionLog.user_id)))
            .where(
                and_(
                    ConnectionLog.action == "connect",
                    ConnectionLog.created_at >= today,
                    ConnectionLog.created_at < tomorrow,
                    ConnectionLog.user_id.isnot(None)
                )
            )
        )
        unique_count = result.scalar() or 0
        
        await db.execute(
            update(DailyStats)
            .where(DailyStats.date == today)
            .values(unique_users=unique_count)
        )
        await db.commit()
    
    def reset_daily_peak(self):
        """重置每日峰值统计（应在每天0点调用）"""
        self.peak_concurrent_today = self.current_connections


# 全局统计服务实例
stats_service = StatsService()
