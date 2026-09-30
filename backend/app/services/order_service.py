import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import Order, OrderItem, User
from app.services.cart_service import get_or_create_cart


def create_order(db: Session, user: User, shipping: dict) -> Order:
    cart = get_or_create_cart(db, user)
    if not cart.items:
        raise HTTPException(400, "Your cart is empty")
    order = Order(user_id=user.id, total_amount=Decimal("0"), shipping_address=json.dumps(shipping))
    total = Decimal("0")
    for it in cart.items:
        p = it.product
        if not p.is_active or it.quantity > p.stock:
            raise HTTPException(400, f"'{p.name}' does not have enough stock")
        sub = p.unit_price * it.quantity
        total += sub
        p.stock -= it.quantity
        order.items.append(OrderItem(product_id=p.id, quantity=it.quantity, price=p.unit_price, subtotal=sub))
    order.total_amount = total
    db.add(order)
    for it in list(cart.items):
        db.delete(it)
    db.commit()
    db.refresh(order)
    return order
