"""
订单管理API路由
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc, and_
from pydantic import BaseModel

from src.core.database import get_db
from src.models.models import User, Order, Transaction, RechargePackage, OrderStatus, TransactionType, PaymentMethod
from src.api.admin import verify_token

router = APIRouter(prefix="/api/admin/orders", tags=["Order Management"])


# ============ 请求模型 ============
class CreateOrderRequest(BaseModel):
    user_id: int
    order_type: str = "recharge"
    product_name: str
    amount: float
    remark: Optional[str] = None


class UpdateOrderRequest(BaseModel):
    status: Optional[str] = None
    remark: Optional[str] = None


class PackageRequest(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    bonus_amount: float = 0
    is_active: bool = True
    is_hot: bool = False
    sort_order: int = 0


# ============ 订单API ============
@router.get("")
async def get_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    order_type: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取订单列表"""
    query = select(Order, User).join(User, Order.user_id == User.id)
    
    if status:
        query = query.where(Order.status == OrderStatus(status))
    
    if order_type:
        query = query.where(Order.order_type == order_type)
    
    if user_id:
        query = query.where(Order.user_id == user_id)
    
    if search:
        query = query.where(Order.order_no.like(f"%{search}%"))
    
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.where(Order.created_at >= start)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.where(Order.created_at < end)
    
    # 获取总数
    count_query = select(func.count()).select_from(
        select(Order).where(query.whereclause).subquery() if query.whereclause is not None else Order
    )
    result = await db.execute(select(func.count(Order.id)))
    
    # 重新计算带条件的总数
    base_query = select(Order)
    if status:
        base_query = base_query.where(Order.status == OrderStatus(status))
    if order_type:
        base_query = base_query.where(Order.order_type == order_type)
    if user_id:
        base_query = base_query.where(Order.user_id == user_id)
    if search:
        base_query = base_query.where(Order.order_no.like(f"%{search}%"))
    
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0
    
    # 分页
    query = query.order_by(desc(Order.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    orders = result.all()
    
    return {
        "items": [
            {
                "id": order.id,
                "order_no": order.order_no,
                "user_id": order.user_id,
                "user_name": user.nickname or user.user_id,
                "order_type": order.order_type,
                "product_name": order.product_name,
                "amount": float(order.amount),
                "paid_amount": float(order.paid_amount or 0),
                "discount_amount": float(order.discount_amount or 0),
                "payment_method": order.payment_method.value if order.payment_method else None,
                "status": order.status.value,
                "remark": order.remark,
                "created_at": order.created_at.isoformat(),
                "paid_at": order.paid_at.isoformat() if order.paid_at else None
            }
            for order, user in orders
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/stats")
async def get_order_stats(
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取订单统计"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    
    # 总订单数
    result = await db.execute(select(func.count(Order.id)))
    total_orders = result.scalar() or 0
    
    # 待支付订单
    result = await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)
    )
    pending_orders = result.scalar() or 0
    
    # 已支付订单
    result = await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
    )
    paid_orders = result.scalar() or 0
    
    # 今日订单数
    result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= today)
    )
    today_orders = result.scalar() or 0
    
    # 今日收入
    result = await db.execute(
        select(func.sum(Order.paid_amount)).where(
            and_(
                Order.status == OrderStatus.PAID,
                Order.paid_at >= today
            )
        )
    )
    today_income = float(result.scalar() or 0)
    
    # 本月收入
    result = await db.execute(
        select(func.sum(Order.paid_amount)).where(
            and_(
                Order.status == OrderStatus.PAID,
                Order.paid_at >= month_start
            )
        )
    )
    month_income = float(result.scalar() or 0)
    
    # 总收入
    result = await db.execute(
        select(func.sum(Order.paid_amount)).where(Order.status == OrderStatus.PAID)
    )
    total_income = float(result.scalar() or 0)
    
    return {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "paid_orders": paid_orders,
        "today_orders": today_orders,
        "today_income": today_income,
        "month_income": month_income,
        "total_income": total_income
    }


@router.post("")
async def create_order(
    request: CreateOrderRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """创建订单（管理员手动创建）"""
    # 验证用户存在
    result = await db.execute(select(User).where(User.id == request.user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    order = Order(
        order_no=f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
        user_id=request.user_id,
        order_type=request.order_type,
        product_name=request.product_name,
        amount=Decimal(str(request.amount)),
        status=OrderStatus.PENDING,
        remark=request.remark,
        expired_at=datetime.now() + timedelta(hours=24)
    )
    
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    return {
        "success": True,
        "message": "订单创建成功",
        "order_no": order.order_no,
        "order_id": order.id
    }


@router.put("/{order_id}/pay")
async def pay_order(
    order_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """确认订单支付（管理员操作）"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="订单状态不允许支付")
    
    # 获取用户
    result = await db.execute(select(User).where(User.id == order.user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新订单状态
    order.status = OrderStatus.PAID
    order.paid_amount = order.amount
    order.paid_at = datetime.now()
    order.payment_method = PaymentMethod.ADMIN
    
    # 如果是充值订单，给用户加余额
    if order.order_type == "recharge":
        balance_before = user.balance or Decimal("0")
        balance_after = balance_before + order.amount
        
        user.balance = balance_after
        user.total_recharge = (user.total_recharge or Decimal("0")) + order.amount
        
        # 创建交易记录
        transaction = Transaction(
            transaction_no=f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
            user_id=user.id,
            order_id=order.id,
            type=TransactionType.RECHARGE,
            amount=order.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"订单充值 {order.order_no}",
            operator=session.get("username", "admin")
        )
        db.add(transaction)
    
    await db.commit()
    
    return {"success": True, "message": "订单已确认支付"}


@router.put("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """取消订单"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="只能取消待支付订单")
    
    order.status = OrderStatus.CANCELLED
    await db.commit()
    
    return {"success": True, "message": "订单已取消"}


@router.put("/{order_id}/refund")
async def refund_order(
    order_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """退款订单"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    if order.status != OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="只能退款已支付订单")
    
    # 获取用户
    result = await db.execute(select(User).where(User.id == order.user_id))
    user = result.scalar_one_or_none()
    
    if user and order.order_type == "recharge":
        # 如果余额足够，扣除余额
        refund_amount = order.paid_amount or order.amount
        if user.balance >= refund_amount:
            balance_before = user.balance
            balance_after = balance_before - refund_amount
            
            user.balance = balance_after
            
            # 创建退款交易记录
            transaction = Transaction(
                transaction_no=f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}",
                user_id=user.id,
                order_id=order.id,
                type=TransactionType.REFUND,
                amount=-refund_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"订单退款 {order.order_no}",
                operator=session.get("username", "admin")
            )
            db.add(transaction)
    
    order.status = OrderStatus.REFUNDED
    await db.commit()
    
    return {"success": True, "message": "订单已退款"}


# ============ 充值套餐API ============
@router.get("/packages")
async def get_packages(
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取充值套餐列表"""
    result = await db.execute(
        select(RechargePackage).order_by(RechargePackage.sort_order)
    )
    packages = result.scalars().all()
    
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": float(p.price),
                "original_price": float(p.original_price) if p.original_price else None,
                "bonus_amount": float(p.bonus_amount or 0),
                "is_active": p.is_active,
                "is_hot": p.is_hot,
                "sort_order": p.sort_order
            }
            for p in packages
        ]
    }


@router.post("/packages")
async def create_package(
    request: PackageRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """创建充值套餐"""
    package = RechargePackage(
        name=request.name,
        description=request.description,
        price=Decimal(str(request.price)),
        original_price=Decimal(str(request.original_price)) if request.original_price else None,
        bonus_amount=Decimal(str(request.bonus_amount)),
        is_active=request.is_active,
        is_hot=request.is_hot,
        sort_order=request.sort_order
    )
    
    db.add(package)
    await db.commit()
    
    return {"success": True, "message": "套餐创建成功"}


@router.put("/packages/{package_id}")
async def update_package(
    package_id: int,
    request: PackageRequest,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """更新充值套餐"""
    result = await db.execute(select(RechargePackage).where(RechargePackage.id == package_id))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="套餐不存在")
    
    package.name = request.name
    package.description = request.description
    package.price = Decimal(str(request.price))
    package.original_price = Decimal(str(request.original_price)) if request.original_price else None
    package.bonus_amount = Decimal(str(request.bonus_amount))
    package.is_active = request.is_active
    package.is_hot = request.is_hot
    package.sort_order = request.sort_order
    
    await db.commit()
    
    return {"success": True, "message": "套餐更新成功"}


@router.delete("/packages/{package_id}")
async def delete_package(
    package_id: int,
    session: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除充值套餐"""
    result = await db.execute(select(RechargePackage).where(RechargePackage.id == package_id))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="套餐不存在")
    
    await db.delete(package)
    await db.commit()
    
    return {"success": True, "message": "套餐已删除"}
