from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import Cart, CartItem, Product, User


def get_or_create_cart(db: Session, user: User) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def serialize(cart: Cart) -> dict:
    items, subtotal = [], Decimal("0")
    for it in cart.items:
        line = it.product.unit_price * it.quantity
        subtotal += line
        items.append({"id": it.id, "product": it.product, "quantity": it.quantity,
                      "unit_price": it.product.unit_price, "line_total": line})
    return {"id": cart.id, "items": items, "item_count": sum(i.quantity for i in cart.items),
            "subtotal": subtotal, "total": subtotal}


def add_item(db: Session, user: User, product_id: int, qty: int) -> Cart:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(404, "Product not found")
    cart = get_or_create_cart(db, user)
    item = next((i for i in cart.items if i.product_id == product_id), None)
    new_qty = (item.quantity if item else 0) + qty
    if new_qty > product.stock:
        raise HTTPException(400, f"Only {product.stock} in stock")
    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(cart_id=cart.id, product_id=product_id, quantity=qty))
    db.commit()
    db.refresh(cart)
    return cart


def _own_item(db: Session, user: User, item_id: int) -> CartItem:
    item = db.query(CartItem).join(Cart).filter(CartItem.id == item_id, Cart.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Cart item not found")
    return item


def update_item(db: Session, user: User, item_id: int, qty: int) -> Cart:
    item = _own_item(db, user, item_id)
    if qty > item.product.stock:
        raise HTTPException(400, f"Only {item.product.stock} in stock")
    item.quantity = qty
    db.commit()
    return get_or_create_cart(db, user)


def remove_item(db: Session, user: User, item_id: int) -> Cart:
    db.delete(_own_item(db, user, item_id))
    db.commit()
    cart = get_or_create_cart(db, user)
    db.refresh(cart)
    return cart
