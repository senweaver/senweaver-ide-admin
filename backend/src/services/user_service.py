"""
用户服务 - 管理用户数据
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.models.models import User, UserStatus, UserModelAccess, UsageLog

class UserService:
    async def get_or_create_model_access(
        self,
        db: AsyncSession,
        user: User,
        *,
        ensure_enabled: bool = False
    ) -> UserModelAccess:
        result = await db.execute(
            select(UserModelAccess).where(UserModelAccess.user_id == user.id)
        )
        access = result.scalar_one_or_none()

        now = datetime.now()

        if not access:
            access = UserModelAccess(
                user_id=user.id,
                enabled=True,
                usage_limit=10000,
                used_count=0,
                created_at=now,
                updated_at=now,
            )
            db.add(access)
        else:
            if ensure_enabled and not access.enabled:
                access.enabled = True
                access.disabled_reason = None
                access.disabled_at = None
                access.enabled_at = now

        await db.commit()
        await db.refresh(access)
        return access

    async def get_or_create_user(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        touch_last_seen: bool = True,
        increment_connections: bool = False
    ) -> User:
        if not user_id:
            return None

        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        now = datetime.now()

        if not user:
            user = User(
                user_id=user_id,
                nickname=user_id,
                status=UserStatus.ACTIVE,
                first_seen_at=now,
                last_seen_at=now,
                total_connections=1 if increment_connections else 0
            )
            db.add(user)
            print(f"创建新用户: {user_id}")
        else:
            if touch_last_seen:
                user.last_seen_at = now
            if increment_connections:
                user.total_connections = (user.total_connections or 0) + 1
            if user.status == UserStatus.INACTIVE:
                user.status = UserStatus.ACTIVE

        await db.commit()
        await db.refresh(user)
        return user

    async def ensure_user_exists(self, db: AsyncSession, user_id: str) -> User:
        """确保用户存在，如果不存在则创建"""
        return await self.get_or_create_user(
            db,
            user_id,
            touch_last_seen=True,
            increment_connections=True
        )

    async def get_user_by_user_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """根据user_id获取用户（不创建）"""
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_model_access_status(self, db: AsyncSession, user_id: str) -> Optional[dict]:
        user = await self.get_or_create_user(
            db,
            user_id,
            touch_last_seen=True,
            increment_connections=False
        )
        if not user:
            return None

        access = await self.get_or_create_model_access(db, user)
        
        # 检查是否需要重置周期
        now = datetime.now()
        last_reset = access.last_reset_time or access.created_at
        reset_days = access.reset_period_days or 30
        
        if (now - last_reset).days >= reset_days:
            access.used_count = 0
            access.last_reset_time = now
            # 如果是因为超额被禁用的，重置后自动启用
            if not access.enabled and access.disabled_reason == "usage_limit_reached":
                access.enabled = True
                access.disabled_reason = None
                access.disabled_at = None
                access.enabled_at = now
            
            await db.commit()
            await db.refresh(access)

        return {
            "enabled": bool(access.enabled),
            "used": int(access.used_count or 0),
            "used_total": int(access.used_total or 0),
            "limit": int(access.usage_limit or 0),
            "reset_days": int(reset_days),
            "last_reset_time": access.last_reset_time.isoformat() if access.last_reset_time else None,
            "disabled_reason": access.disabled_reason,
        }

    async def increment_model_usage(self, db: AsyncSession, user_id: str, *, inc: int = 1, model_name: str = None, client_id: str = None) -> Optional[dict]:
        user = await self.get_or_create_user(
            db,
            user_id,
            touch_last_seen=True,
            increment_connections=False
        )
        if not user:
            return None

        # 记录详细使用日志
        if model_name or client_id:
            usage_log = UsageLog(
                user_id=user.id,
                client_id=client_id or "unknown",
                usage_type="model_use",
                usage_detail=model_name or "unknown",
                tokens_used=inc,
                created_at=datetime.now()
            )
            db.add(usage_log)

        access = await self.get_or_create_model_access(db, user)

        # 检查是否需要重置周期
        now = datetime.now()
        last_reset = access.last_reset_time or access.created_at
        reset_days = access.reset_period_days or 30
        
        if (now - last_reset).days >= reset_days:
            access.used_count = 0
            access.last_reset_time = now
            # 如果是因为超额被禁用的，重置后自动启用
            if not access.enabled and access.disabled_reason == "usage_limit_reached":
                access.enabled = True
                access.disabled_reason = None
                access.disabled_at = None
                access.enabled_at = now
        
        just_disabled = False
        if access.enabled:
            access.used_count = int(access.used_count or 0) + int(inc)
            access.used_total = int(access.used_total or 0) + int(inc)  # 累计总使用量
            
            if int(access.used_count or 0) >= int(access.usage_limit or 0):
                access.enabled = False
                access.disabled_reason = "usage_limit_reached"
                access.disabled_at = datetime.now()
                just_disabled = True

        user.total_api_calls = int(user.total_api_calls or 0) + int(inc)

        await db.commit()
        await db.refresh(access)
        return {
            "enabled": bool(access.enabled),
            "used": int(access.used_count or 0),
            "used_total": int(access.used_total or 0),
            "limit": int(access.usage_limit or 0),
            "reset_days": int(reset_days),
            "last_reset_time": access.last_reset_time.isoformat() if access.last_reset_time else None,
            "disabled_reason": access.disabled_reason,
            "just_disabled": just_disabled,
        }

    async def set_model_access(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        enabled: bool,
        usage_limit: Optional[int] = None,
        reset_used: bool = False,
        reason: Optional[str] = None
    ) -> Optional[dict]:
        user = await self.get_or_create_user(
            db,
            user_id,
            touch_last_seen=True,
            increment_connections=False
        )
        if not user:
            return None

        access = await self.get_or_create_model_access(db, user)
        now = datetime.now()

        access.enabled = bool(enabled)
        if usage_limit is not None:
            access.usage_limit = int(usage_limit)
        if reset_used:
            access.used_count = 0
            access.last_reset_time = now

        if access.enabled:
            access.disabled_reason = None
            access.disabled_at = None
            access.enabled_at = now
        else:
            access.disabled_reason = reason or access.disabled_reason or "manual_disable"
            access.disabled_at = now

        await db.commit()
        await db.refresh(access)
        return {
            "enabled": bool(access.enabled),
            "used": int(access.used_count or 0),
            "limit": int(access.usage_limit or 0),
            "disabled_reason": access.disabled_reason,
        }

    async def update_online_duration(self, db: AsyncSession, user_id: str, duration_seconds: int):
        """更新用户在线时长"""
        if not user_id or duration_seconds <= 0:
            return
            
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            user.total_online_duration = (user.total_online_duration or 0) + duration_seconds
            await db.commit()

    async def delete_user(self, db: AsyncSession, user_id: int) -> bool:
        """删除用户（逻辑删除）"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # 逻辑删除：更新状态为 DELETED
        user.status = UserStatus.DELETED
        
        # 禁用模型权限
        result = await db.execute(select(UserModelAccess).where(UserModelAccess.user_id == user_id))
        access = result.scalar_one_or_none()
        if access:
            access.enabled = False
            access.disabled_reason = "User deleted"
            access.disabled_at = datetime.now()
            
        await db.commit()
        return True

user_service = UserService()
