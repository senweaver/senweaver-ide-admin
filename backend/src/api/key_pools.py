"""
密钥池管理路由
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.core.database import get_db
from src.models.models import KeyPoolProvider, KeyPool, KeyAllocation
from src.services.key_pool_service import key_pool_service
from src.api.admin import verify_token
from sqlalchemy import select, func

router = APIRouter(prefix="/api/admin/key-pools", tags=["Key Pool Management"])


# Pydantic 模型
class ProviderCreateRequest(BaseModel):
    name: str
    display_name: str
    base_url: Optional[str] = None
    description: Optional[str] = None
    priority: int = 0


class ProviderUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class ProviderResponse(BaseModel):
    id: int
    name: str
    display_name: str
    base_url: Optional[str]
    description: Optional[str]
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime


class KeyPoolCreateRequest(BaseModel):
    provider_id: int
    name: str
    api_key: str
    description: Optional[str] = None
    max_clients: int = -1


class KeyPoolUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    max_clients: Optional[int] = None
    is_active: Optional[bool] = None


class KeyPoolResponse(BaseModel):
    id: int
    provider_id: int
    name: str
    description: Optional[str]
    max_clients: int
    current_clients: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KeyAllocationResponse(BaseModel):
    id: int
    key_pool_id: int
    client_id: str
    user_id: Optional[str]
    allocated_at: datetime
    released_at: Optional[datetime]
    is_active: bool


# 提供商管理接口
@router.get("/providers", response_model=List[ProviderResponse])
async def get_providers(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取所有提供商"""
    result = await db.execute(
        select(KeyPoolProvider).order_by(KeyPoolProvider.priority.desc(), KeyPoolProvider.name)
    )
    providers = result.scalars().all()
    return providers


@router.post("/providers", response_model=ProviderResponse)
async def create_provider(request: ProviderCreateRequest, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """创建提供商"""
    try:
        provider = await key_pool_service.create_provider(
            db=db,
            name=request.name,
            display_name=request.display_name,
            base_url=request.base_url,
            description=request.description,
            priority=request.priority
        )
        return provider
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建提供商失败: {str(e)}")


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(provider_id: int, request: ProviderUpdateRequest, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """更新提供商"""
    try:
        update_data = request.model_dump(exclude_unset=True)
        provider = await key_pool_service.update_provider(db, provider_id, **update_data)
        if not provider:
            raise HTTPException(status_code=404, detail="提供商不存在")
        return provider
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"更新提供商失败: {str(e)}")


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """删除提供商"""
    try:
        success = await key_pool_service.delete_provider(db, provider_id)
        if not success:
            raise HTTPException(status_code=400, detail="无法删除提供商，可能存在关联的密钥池")
        return {"message": "提供商已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除提供商失败: {str(e)}")


# 密钥池管理接口
@router.get("/pools")
async def get_key_pools(
    page: int = 1,
    page_size: int = 20,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取所有密钥池（分页）"""
    offset = (page - 1) * page_size
    
    # 获取总数
    total_result = await db.execute(select(func.count(KeyPool.id)))
    total = total_result.scalar() or 0
    
    # 获取分页数据
    result = await db.execute(
        select(KeyPool, KeyPoolProvider)
        .join(KeyPoolProvider)
        .order_by(KeyPoolProvider.name, KeyPool.name)
        .offset(offset)
        .limit(page_size)
    )

    # 获取所有活跃的分配记录，用于显示占用用户
    active_allocations_result = await db.execute(
        select(KeyAllocation.key_pool_id, KeyAllocation.user_id, KeyAllocation.client_id)
        .where(KeyAllocation.is_active == True)
    )
    
    allocations_map = {}
    for row in active_allocations_result:
        pool_id = row.key_pool_id
        if pool_id not in allocations_map:
            allocations_map[pool_id] = []
        # 优先显示user_id，如果没有则显示client_id
        display_id = row.user_id if row.user_id else f"Client:{row.client_id}"
        allocations_map[pool_id].append(display_id)

    pools = []
    for pool, provider in result:
        pool_dict = {
            "id": pool.id,
            "provider_id": pool.provider_id,
            "name": pool.name,
            "description": pool.description,
            "api_key": pool.api_key, # 确保前端能获取到API Key
            "max_clients": pool.max_clients,
            "current_clients": pool.current_clients,
            "active_users": allocations_map.get(pool.id, []),
            "is_active": pool.is_active,
            "created_at": pool.created_at,
            "updated_at": pool.updated_at,
            "provider": {
                "id": provider.id,
                "name": provider.name,
                "display_name": provider.display_name
            }
        }
        pools.append(pool_dict)

    return {
        "items": pools,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/pools", response_model=KeyPoolResponse)
async def create_key_pool(request: KeyPoolCreateRequest, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """创建密钥池"""
    try:
        # 检查提供商是否存在
        result = await db.execute(
            select(KeyPoolProvider).where(KeyPoolProvider.id == request.provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="提供商不存在")

        key_pool = await key_pool_service.create_key_pool(
            db=db,
            provider_id=request.provider_id,
            name=request.name,
            api_key=request.api_key,
            description=request.description,
            max_clients=request.max_clients
        )
        return {
            "id": key_pool.id,
            "provider_id": key_pool.provider_id,
            "name": key_pool.name,
            "description": key_pool.description,
            "max_clients": key_pool.max_clients,
            "current_clients": key_pool.current_clients,
            "is_active": key_pool.is_active,
            "created_at": key_pool.created_at,
            "updated_at": key_pool.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建密钥池失败: {str(e)}")


class KeyPoolBatchCreateRequest(BaseModel):
    provider_id: int
    api_keys: List[str]
    description: Optional[str] = None
    max_clients: int = -1
    name_prefix: str = "Pool"


@router.post("/pools/batch", response_model=List[KeyPoolResponse])
async def batch_create_key_pools(request: KeyPoolBatchCreateRequest, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """批量创建密钥池"""
    try:
        # 检查提供商是否存在
        result = await db.execute(
            select(KeyPoolProvider).where(KeyPoolProvider.id == request.provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="提供商不存在")

        key_pools = await key_pool_service.batch_create_key_pools(
            db=db,
            provider_id=request.provider_id,
            api_keys=request.api_keys,
            description=request.description,
            max_clients=request.max_clients,
            name_prefix=request.name_prefix
        )
        
        return [
            {
                "id": kp.id,
                "provider_id": kp.provider_id,
                "name": kp.name,
                "description": kp.description,
                "max_clients": kp.max_clients,
                "current_clients": kp.current_clients,
                "is_active": kp.is_active,
                "created_at": kp.created_at,
                "updated_at": kp.updated_at
            }
            for kp in key_pools
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"批量创建密钥池失败: {str(e)}")


@router.put("/pools/{pool_id}", response_model=KeyPoolResponse)
async def update_key_pool(pool_id: int, request: KeyPoolUpdateRequest, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """更新密钥池"""
    try:
        update_data = request.model_dump(exclude_unset=True)
        key_pool = await key_pool_service.update_key_pool(db, pool_id, **update_data)
        if not key_pool:
            raise HTTPException(status_code=404, detail="密钥池不存在")

        return {
            "id": key_pool.id,
            "provider_id": key_pool.provider_id,
            "name": key_pool.name,
            "description": key_pool.description,
            "max_clients": key_pool.max_clients,
            "current_clients": key_pool.current_clients,
            "is_active": key_pool.is_active,
            "created_at": key_pool.created_at,
            "updated_at": key_pool.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"更新密钥池失败: {str(e)}")


@router.delete("/pools/{pool_id}")
async def delete_key_pool(pool_id: int, session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """删除密钥池"""
    try:
        success = await key_pool_service.delete_key_pool(db, pool_id)
        if not success:
            raise HTTPException(status_code=400, detail="无法删除密钥池，可能存在活跃的分配")
        return {"message": "密钥池已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除密钥池失败: {str(e)}")


# 分配记录查询接口
@router.get("/allocations", response_model=List[KeyAllocationResponse])
async def get_allocations(
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取分配记录"""
    query = select(KeyAllocation)

    if client_id:
        query = query.where(KeyAllocation.client_id == client_id)
    if user_id:
        query = query.where(KeyAllocation.user_id == user_id)
    if is_active is not None:
        query = query.where(KeyAllocation.is_active == is_active)

    query = query.order_by(KeyAllocation.allocated_at.desc())

    result = await db.execute(query)
    allocations = result.scalars().all()
    return allocations


# 统计信息接口
@router.get("/stats")
async def get_key_pool_stats(session: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """获取密钥池统计信息"""
    try:
        stats = await key_pool_service.get_key_pool_status(db)
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")
