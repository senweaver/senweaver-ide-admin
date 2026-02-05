"""
用户统计API路由
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct

from src.core.database import get_db
from src.models.models import ConnectionLog, DailyStats, UserActivity
from src.schemas.schemas import DailyStatsResponse, UserStatsOverview

router = APIRouter(prefix="/api/stats", tags=["Statistics"])


@router.get("/overview", response_model=UserStatsOverview)
async def get_stats_overview(db: AsyncSession = Depends(get_db)):
    """获取统计概览"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 今日连接数
    result = await db.execute(
        select(func.count(ConnectionLog.id))
        .where(
            and_(
                ConnectionLog.action == "connect",
                ConnectionLog.created_at >= today
            )
        )
    )
    today_connections = result.scalar() or 0
    
    # 今日独立用户
    result = await db.execute(
        select(func.count(distinct(ConnectionLog.user_id)))
        .where(
            and_(
                ConnectionLog.action == "connect",
                ConnectionLog.created_at >= today,
                ConnectionLog.user_id.isnot(None)
            )
        )
    )
    today_unique_users = result.scalar() or 0
    
    # 今日峰值在线
    result = await db.execute(
        select(DailyStats.peak_concurrent)
        .where(DailyStats.date == today)
    )
    today_peak = result.scalar() or 0
    
    # 总连接数
    result = await db.execute(
        select(func.count(ConnectionLog.id))
        .where(ConnectionLog.action == "connect")
    )
    total_connections = result.scalar() or 0
    
    # 总独立用户
    result = await db.execute(
        select(func.count(distinct(ConnectionLog.user_id)))
        .where(
            and_(
                ConnectionLog.action == "connect",
                ConnectionLog.user_id.isnot(None)
            )
        )
    )
    total_unique_users = result.scalar() or 0
    
    # 平均在线时长
    result = await db.execute(
        select(func.avg(UserActivity.duration_seconds))
        .where(UserActivity.duration_seconds > 0)
    )
    avg_duration = result.scalar() or 0
    avg_duration_minutes = round(avg_duration / 60, 2) if avg_duration else 0
    
    return UserStatsOverview(
        today_connections=today_connections,
        today_unique_users=today_unique_users,
        today_peak_concurrent=today_peak,
        total_connections=total_connections,
        total_unique_users=total_unique_users,
        average_duration_minutes=avg_duration_minutes
    )


@router.get("/daily", response_model=List[DailyStatsResponse])
async def get_daily_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """获取每日统计数据"""
    start_date = datetime.now() - timedelta(days=days)
    
    result = await db.execute(
        select(DailyStats)
        .where(DailyStats.date >= start_date)
        .order_by(DailyStats.date.desc())
    )
    stats = result.scalars().all()
    
    return [
        DailyStatsResponse(
            date=stat.date.strftime("%Y-%m-%d"),
            total_connections=stat.total_connections,
            unique_users=stat.unique_users,
            peak_concurrent=stat.peak_concurrent,
            total_duration_seconds=stat.total_duration_seconds,
            new_users=stat.new_users,
            returning_users=stat.returning_users
        )
        for stat in stats
    ]


@router.get("/hourly")
async def get_hourly_stats(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取小时统计数据"""
    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    else:
        target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    end_date = target_date + timedelta(days=1)
    
    # 按小时统计连接数
    result = await db.execute(
        select(
            func.hour(ConnectionLog.created_at).label("hour"),
            func.count(ConnectionLog.id).label("count")
        )
        .where(
            and_(
                ConnectionLog.action == "connect",
                ConnectionLog.created_at >= target_date,
                ConnectionLog.created_at < end_date
            )
        )
        .group_by(func.hour(ConnectionLog.created_at))
    )
    hourly_data = result.all()
    
    # 构建24小时数据
    hours = {h: 0 for h in range(24)}
    for row in hourly_data:
        hours[row.hour] = row.count
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "hourly": [{"hour": h, "connections": c} for h, c in hours.items()]
    }


@router.get("/connections/recent")
async def get_recent_connections(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """获取最近的连接记录"""
    result = await db.execute(
        select(ConnectionLog)
        .order_by(ConnectionLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    
    return [
        {
            "id": log.id,
            "client_id": log.client_id,
            "user_id": log.user_id,
            "action": log.action,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]


@router.get("/users/active")
async def get_active_users(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db)
):
    """获取活跃用户列表"""
    since = datetime.now() - timedelta(hours=hours)
    
    result = await db.execute(
        select(
            UserActivity.user_id,
            func.count(UserActivity.id).label("sessions"),
            func.sum(UserActivity.duration_seconds).label("total_duration"),
            func.max(UserActivity.connect_time).label("last_seen")
        )
        .where(
            and_(
                UserActivity.connect_time >= since,
                UserActivity.user_id.isnot(None)
            )
        )
        .group_by(UserActivity.user_id)
        .order_by(func.max(UserActivity.connect_time).desc())
    )
    users = result.all()
    
    return [
        {
            "user_id": user.user_id,
            "sessions": user.sessions,
            "total_duration_minutes": round((user.total_duration or 0) / 60, 2),
            "last_seen": user.last_seen.isoformat() if user.last_seen else None
        }
        for user in users
    ]
