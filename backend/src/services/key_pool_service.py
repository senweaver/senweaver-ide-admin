"""
密钥池管理服务
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import selectinload
from src.models.models import KeyPoolProvider, KeyPool, KeyAllocation


from src.core.key_pool_config import PROVIDERS_CONFIG

class KeyPoolService:
    """密钥池管理服务"""

    def __init__(self):
        self._providers_cache = {}
        self._key_pools_cache = {}
        self._last_cache_update = None

    async def initialize_key_pools(self, db: AsyncSession):
        """初始化密钥池数据"""
        try:
            # 1. 检查并初始化默认配置中的提供商和密钥
            for provider_config in PROVIDERS_CONFIG:
                provider_name = provider_config["name"]
                
                # 检查提供商是否存在
                result = await db.execute(
                    select(KeyPoolProvider).where(KeyPoolProvider.name == provider_name)
                )
                provider = result.scalar_one_or_none()
                
                if not provider:
                    print(f"初始化提供商: {provider_name}")
                    provider = await self.create_provider(
                        db, 
                        name=provider_name,
                        display_name=provider_config["display_name"],
                        base_url=provider_config["base_url"],
                        description="系统初始化自动创建",
                        priority=provider_config["priority"]
                    )
                
                # 检查密钥是否已添加
                existing_keys_result = await db.execute(
                    select(KeyPool.api_key)
                    .where(KeyPool.provider_id == provider.id)
                )
                existing_keys = set(existing_keys_result.scalars().all())
                
                keys_to_add = [k for k in provider_config["keys"] if k not in existing_keys]
                
                if keys_to_add:
                    print(f"为提供商 {provider_name} 添加 {len(keys_to_add)} 个新密钥")
                    for i, api_key in enumerate(keys_to_add):
                        pool_name = f"{provider_name}_pool_{len(existing_keys) + i + 1}"
                        # 默认每个key只能分配给1个客户端，模拟原来的pop逻辑
                        # 如果是ownProvider，可能是共享key，但为了保持原有逻辑一致，这里设为1
                        # 如果需要支持并发，可以在管理后台修改 max_clients
                        await self.create_key_pool(
                            db,
                            provider_id=provider.id,
                            name=pool_name,
                            api_key=api_key,
                            description="系统初始化自动导入",
                            max_clients=1 
                        )
            
            # 2. 更新缓存
            # 获取所有活跃的提供商
            providers = await self.get_active_providers(db)
            self._providers_cache = {p.name: p for p in providers}

            # 获取所有活跃的密钥池
            key_pools = await self.get_active_key_pools(db)
            self._key_pools_cache = {}
            for pool in key_pools:
                provider_name = pool.provider.name if pool.provider else "unknown"
                if provider_name not in self._key_pools_cache:
                    self._key_pools_cache[provider_name] = []
                self._key_pools_cache[provider_name].append(pool)

            self._last_cache_update = datetime.now()
            print(f"密钥池初始化完成: {len(providers)} 个提供商, {len(key_pools)} 个密钥池")

        except Exception as e:
            print(f"初始化密钥池失败: {e}")
            raise

    async def get_active_providers(self, db: AsyncSession) -> List[KeyPoolProvider]:
        """获取所有活跃的提供商"""
        result = await db.execute(
            select(KeyPoolProvider)
            .where(KeyPoolProvider.is_active == True)
            .order_by(KeyPoolProvider.priority.desc(), KeyPoolProvider.name)
        )
        return result.scalars().all()

    async def get_active_key_pools(self, db: AsyncSession) -> List[KeyPool]:
        """获取所有活跃的密钥池"""
        result = await db.execute(
            select(KeyPool)
            .join(KeyPoolProvider)
            .where(
                and_(
                    KeyPool.is_active == True,
                    KeyPoolProvider.is_active == True
                )
            )
            .options(selectinload(KeyPool.provider))
            .order_by(KeyPoolProvider.priority.desc(), KeyPool.name)
        )
        return result.scalars().all()

    async def allocate_key_for_client(self, db: AsyncSession, provider_name: str, client_id: str, user_id: Optional[str] = None) -> Optional[str]:
        """为客户端分配密钥"""
        try:
            # 检查客户端是否已经有活跃的分配
            existing_allocation = await db.execute(
                select(KeyAllocation)
                .join(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyAllocation.client_id == client_id,
                        KeyAllocation.is_active == True,
                        KeyPoolProvider.name == provider_name
                    )
                )
                .options(selectinload(KeyAllocation.key_pool))
            )
            existing = existing_allocation.scalar_one_or_none()
            if existing:
                return existing.key_pool.api_key

            # 查找可用的密钥池
            available_pools = await db.execute(
                select(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyPoolProvider.name == provider_name,
                        KeyPool.is_active == True,
                        KeyPoolProvider.is_active == True,
                        or_(
                            KeyPool.max_clients == -1,
                            KeyPool.current_clients < KeyPool.max_clients
                        )
                    )
                )
                .order_by(KeyPool.current_clients.asc())  # 优先选择使用率低的池
            )
            available_pools = available_pools.scalars().all()

            if not available_pools:
                print(f"没有可用的 {provider_name} 密钥池")
                return None

            # 选择第一个可用的池
            selected_pool = available_pools[0]

            # 创建分配记录
            allocation = KeyAllocation(
                key_pool_id=selected_pool.id,
                client_id=client_id,
                user_id=user_id,
                is_active=True
            )
            db.add(allocation)

            # 更新池的使用计数
            await db.execute(
                update(KeyPool)
                .where(KeyPool.id == selected_pool.id)
                .values(current_clients=KeyPool.current_clients + 1)
            )

            await db.commit()
            print(f"为客户端 {client_id} 分配了 {provider_name} 密钥池 {selected_pool.name}")

            return selected_pool.api_key

        except Exception as e:
            await db.rollback()
            print(f"分配密钥失败: {e}")
            return None

    async def release_key_for_client(self, db: AsyncSession, client_id: str):
        """释放客户端的密钥"""
        try:
            # 查找客户端的活跃分配
            allocations = await db.execute(
                select(KeyAllocation)
                .where(
                    and_(
                        KeyAllocation.client_id == client_id,
                        KeyAllocation.is_active == True
                    )
                )
            )
            allocations = allocations.scalars().all()

            if not allocations:
                return

            # 释放所有分配
            for allocation in allocations:
                # 更新分配记录
                allocation.is_active = False
                allocation.released_at = datetime.now()

                # 更新池的使用计数
                await db.execute(
                    update(KeyPool)
                    .where(KeyPool.id == allocation.key_pool_id)
                    .values(current_clients=KeyPool.current_clients - 1)
                )

            await db.commit()
            print(f"释放了客户端 {client_id} 的 {len(allocations)} 个密钥分配")

        except Exception as e:
            await db.rollback()
            print(f"释放密钥失败: {e}")

    async def release_key_for_user(self, db: AsyncSession, user_id: str):
        try:
            if not user_id:
                return

            allocations = await db.execute(
                select(KeyAllocation)
                .where(
                    and_(
                        KeyAllocation.user_id == user_id,
                        KeyAllocation.is_active == True
                    )
                )
            )
            allocations = allocations.scalars().all()
            if not allocations:
                return

            for allocation in allocations:
                allocation.is_active = False
                allocation.released_at = datetime.now()
                await db.execute(
                    update(KeyPool)
                    .where(KeyPool.id == allocation.key_pool_id)
                    .values(current_clients=KeyPool.current_clients - 1)
                )

            await db.commit()
            print(f"释放了用户 {user_id} 的 {len(allocations)} 个密钥分配")
        except Exception as e:
            await db.rollback()
            print(f"释放用户密钥失败: {e}")

    async def validate_client_key(self, db: AsyncSession, provider_name: str, client_id: str, api_key: str) -> bool:
        """验证客户端的密钥是否有效"""
        try:
            result = await db.execute(
                select(KeyAllocation)
                .join(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyAllocation.client_id == client_id,
                        KeyAllocation.is_active == True,
                        KeyPoolProvider.name == provider_name,
                        KeyPool.api_key == api_key
                    )
                )
            )
            allocation = result.scalar_one_or_none()
            return allocation is not None

        except Exception as e:
            print(f"验证密钥失败: {e}")
            return False

    async def get_allocated_key(self, db: AsyncSession, provider_name: str, client_id: str) -> Optional[str]:
        """获取客户端当前分配的密钥（仅查询，不分配）"""
        try:
            result = await db.execute(
                select(KeyAllocation)
                .join(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyAllocation.client_id == client_id,
                        KeyAllocation.is_active == True,
                        KeyPoolProvider.name == provider_name
                    )
                )
                .options(selectinload(KeyAllocation.key_pool))
            )
            allocation = result.scalar_one_or_none()
            if allocation:
                return allocation.key_pool.api_key
            return None
        except Exception as e:
            print(f"获取已分配密钥失败: {e}")
            return None

    async def try_accept_client_key(self, db: AsyncSession, provider_name: str, client_id: str, api_key: str, user_id: str) -> bool:
        """
        尝试接受客户端提供的密钥。
        如果该密钥在库中存在、有效且可用（或已分配给该客户端但状态不一致），则更新分配并返回 True。
        """
        try:
            # 1. 查找密钥对应的池
            pool_result = await db.execute(
                select(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyPoolProvider.name == provider_name,
                        KeyPool.api_key == api_key,
                        KeyPool.is_active == True,
                        KeyPoolProvider.is_active == True
                    )
                )
            )
            target_pool = pool_result.scalar_one_or_none()
            
            if not target_pool:
                return False
                
            # 2. 检查容量 (如果是无限 -1 或者当前 < 最大)
            # 注意：如果客户端之前就占用了这个位置（只是Allocation记录有问题），这里可能会误判
            # 但既然是 try_accept，我们假设它是新的请求
            if target_pool.max_clients != -1 and target_pool.current_clients >= target_pool.max_clients:
                # 检查是否其实就是这个客户端占用的（虽然 validate 失败了）
                # 这种情况很少见，因为如果占用了 validate 应该通过。
                # 除非 allocation is_active=False?
                return False

            # 3. 释放该客户端在该提供商下的旧分配（如果有）
            old_allocations = await db.execute(
                select(KeyAllocation)
                .join(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyAllocation.client_id == client_id,
                        KeyAllocation.is_active == True,
                        KeyPoolProvider.name == provider_name
                    )
                )
            )
            
            for old_alloc in old_allocations.scalars().all():
                # 如果旧分配就是目标池，那为什么 validate 失败了？
                # 可能是 validate 逻辑有问题？或者数据状态不一致。
                #不管怎样，先释放旧的
                old_alloc.is_active = False
                old_alloc.released_at = datetime.now()
                await db.execute(
                    update(KeyPool)
                    .where(KeyPool.id == old_alloc.key_pool_id)
                    .values(current_clients=KeyPool.current_clients - 1)
                )
            
            # 4. 创建新分配
            allocation = KeyAllocation(
                key_pool_id=target_pool.id,
                client_id=client_id,
                user_id=user_id,
                is_active=True
            )
            db.add(allocation)
            
            # 5. 更新目标池计数
            await db.execute(
                update(KeyPool)
                .where(KeyPool.id == target_pool.id)
                .values(current_clients=KeyPool.current_clients + 1)
            )
            
            await db.commit()
            print(f"已将客户端 {client_id} 的分配切换到其提供的密钥 (Provider: {provider_name})")
            return True
            
        except Exception as e:
            await db.rollback()
            print(f"尝试接受客户端密钥失败: {e}")
            return False

    async def get_key_pool_status(self, db: AsyncSession) -> Dict:
        """获取密钥池状态"""
        try:
            # 获取所有活跃的密钥池和提供商
            result = await db.execute(
                select(KeyPool)
                .join(KeyPoolProvider)
                .where(
                    and_(
                        KeyPool.is_active == True,
                        KeyPoolProvider.is_active == True
                    )
                )
                .options(selectinload(KeyPool.provider))
            )
            pools = result.scalars().all()

            provider_stats = {}
            
            # 统计数据
            for pool in pools:
                p_name = pool.provider.name
                p_disp = pool.provider.display_name
                
                if p_name not in provider_stats:
                    provider_stats[p_name] = {
                        "name": p_name,
                        "display_name": p_disp,
                        "total_keys": 0,
                        "used_clients": 0,
                        "max_clients": 0,
                        "has_infinite": False
                    }
                
                stats = provider_stats[p_name]
                stats["total_keys"] += 1
                stats["used_clients"] += pool.current_clients
                
                if pool.max_clients == -1:
                    stats["has_infinite"] = True
                else:
                    stats["max_clients"] += pool.max_clients
            
            # 处理最终统计结果
            final_providers = []
            total_providers = 0
            total_pools = 0
            total_clients = 0
            total_capacity = 0
            has_any_infinite = False
            
            for p_name, stats in provider_stats.items():
                if stats["total_keys"] == 0:
                    continue
                    
                total_providers += 1
                total_pools += stats["total_keys"]
                total_clients += stats["used_clients"]
                
                if stats["has_infinite"]:
                    has_any_infinite = True
                    stats["usage_rate"] = 0.0
                    stats["remaining"] = -1  # 无限
                    stats["capacity_display"] = "∞"
                else:
                    total_capacity += stats["max_clients"]
                    capacity = max(stats["max_clients"], 1)
                    stats["usage_rate"] = (stats["used_clients"] / capacity) * 100
                    stats["remaining"] = stats["max_clients"] - stats["used_clients"]
                    stats["capacity_display"] = str(stats["max_clients"])
                
                final_providers.append(stats)
                
            return {
                "provider_stats": final_providers,
                "summary": {
                    "total_providers": total_providers,
                    "total_pools": total_pools,
                    "total_clients": total_clients,
                    "total_capacity": "∞" if has_any_infinite else total_capacity
                }
            }

        except Exception as e:
            print(f"获取密钥池状态失败: {e}")
            return {"error": str(e)}

    async def create_provider(self, db: AsyncSession, name: str, display_name: str, base_url: Optional[str] = None, description: Optional[str] = None, priority: int = 0) -> KeyPoolProvider:
        """创建提供商"""
        provider = KeyPoolProvider(
            name=name,
            display_name=display_name,
            base_url=base_url,
            description=description,
            priority=priority,
            is_active=True
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)
        return provider

    async def create_key_pool(self, db: AsyncSession, provider_id: int, name: str, api_key: str, description: Optional[str] = None, max_clients: int = -1) -> KeyPool:
        """创建密钥池"""
        key_pool = KeyPool(
            provider_id=provider_id,
            name=name,
            api_key=api_key,
            description=description,
            max_clients=max_clients,
            current_clients=0,
            is_active=True
        )
        db.add(key_pool)
        await db.commit()
        await db.refresh(key_pool)
        return key_pool

    async def batch_create_key_pools(self, db: AsyncSession, provider_id: int, api_keys: List[str], description: Optional[str] = None, max_clients: int = -1, name_prefix: str = "Pool") -> List[KeyPool]:
        """批量创建密钥池"""
        created_pools = []
        try:
            # 获取当前该提供商的密钥池数量，用于生成唯一名称
            result = await db.execute(
                select(func.count(KeyPool.id)).where(KeyPool.provider_id == provider_id)
            )
            count = result.scalar() or 0
            
            for i, api_key in enumerate(api_keys):
                name = f"{name_prefix}_{count + i + 1}"
                # 检查密钥是否已存在（可选，这里简化处理，允许重复）
                
                key_pool = KeyPool(
                    provider_id=provider_id,
                    name=name,
                    api_key=api_key.strip(),
                    description=description,
                    max_clients=max_clients,
                    current_clients=0,
                    is_active=True
                )
                db.add(key_pool)
                created_pools.append(key_pool)
            
            await db.commit()
            for pool in created_pools:
                await db.refresh(pool)
            
            return created_pools
        except Exception as e:
            await db.rollback()
            print(f"批量创建密钥池失败: {e}")
            raise

    async def update_provider(self, db: AsyncSession, provider_id: int, **kwargs) -> Optional[KeyPoolProvider]:
        """更新提供商"""
        await db.execute(
            update(KeyPoolProvider)
            .where(KeyPoolProvider.id == provider_id)
            .values(**kwargs)
        )
        await db.commit()

        result = await db.execute(
            select(KeyPoolProvider).where(KeyPoolProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def update_key_pool(self, db: AsyncSession, pool_id: int, **kwargs) -> Optional[KeyPool]:
        """更新密钥池"""
        await db.execute(
            update(KeyPool)
            .where(KeyPool.id == pool_id)
            .values(**kwargs)
        )
        await db.commit()

        result = await db.execute(
            select(KeyPool).where(KeyPool.id == pool_id)
        )
        return result.scalar_one_or_none()

    async def delete_provider(self, db: AsyncSession, provider_id: int) -> bool:
        """删除提供商"""
        try:
            # 检查是否有关联的密钥池
            result = await db.execute(
                select(func.count(KeyPool.id))
                .where(KeyPool.provider_id == provider_id)
            )
            count = result.scalar()
            if count > 0:
                return False  # 有关联的密钥池，不能删除

            await db.execute(
                update(KeyPoolProvider)
                .where(KeyPoolProvider.id == provider_id)
                .values(is_active=False)
            )
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            print(f"删除提供商失败: {e}")
            return False

    async def delete_key_pool(self, db: AsyncSession, pool_id: int) -> bool:
        """删除密钥池"""
        try:
            # 检查是否有活跃的分配
            result = await db.execute(
                select(func.count(KeyAllocation.id))
                .where(
                    and_(
                        KeyAllocation.key_pool_id == pool_id,
                        KeyAllocation.is_active == True
                    )
                )
            )
            count = result.scalar()
            if count > 0:
                return False  # 有活跃的分配，不能删除

            await db.execute(
                update(KeyPool)
                .where(KeyPool.id == pool_id)
                .values(is_active=False)
            )
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            print(f"删除密钥池失败: {e}")
            return False


# 创建全局实例
key_pool_service = KeyPoolService()
