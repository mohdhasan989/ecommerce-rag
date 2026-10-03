from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.auth import require_admin
from app.models import AuditLog, Category, ChatFeedback, Order, OrderStatus, Product, User
from app.schemas import (ActiveUpdate, AuditLogOut, CategoryIn, CategoryOut, ChatFeedbackOut,
                         OrderOut, ProductIn, ProductOut, ProductPage, StatusUpdate, UserOut)
from app.services import audit_service, product_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    recent = db.query(Order).order_by(Order.id.desc()).limit(5).all()
    return {"total_products": db.query(Product).count(), "total_orders": db.query(Order).count(),
            "total_users": db.query(User).count(),
            "revenue": float(db.query(func.coalesce(func.sum(Order.total_amount), 0)).scalar()),
            "recent_orders": [OrderOut.model_validate(o) for o in recent]}


@router.get("/products", response_model=ProductPage)
def products(search: str | None = None, page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    return product_service.list_products(db, search=search, page=page, limit=limit, include_inactive=True)


@router.get("/products/{pid}", response_model=ProductOut)
def product(pid: int, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found")
    return p


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    return product_service.save_product(db, data)


@router.put("/products/{pid}", response_model=ProductOut)
def update_product(pid: int, data: ProductIn, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found")
    return product_service.save_product(db, data, p)


@router.delete("/products/{pid}", status_code=204)
def delete_product(pid: int, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found")
    p.is_active = False  # soft delete keeps order history intact
    db.commit()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: Session = Depends(get_db)):
    if db.query(Category).filter(Category.name == data.name).first():
        raise HTTPException(409, "Category already exists")
    c = Category(**data.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/categories/{cid}", response_model=CategoryOut)
def update_category(cid: int, data: CategoryIn, db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "Category not found")
    c.name, c.description = data.name, data.description
    db.commit()
    return c


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: int, db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "Category not found")
    if c.products:
        raise HTTPException(400, "Category still has products")
    db.delete(c)
    db.commit()


@router.get("/orders", response_model=list[OrderOut])
def orders(db: Session = Depends(get_db)):
    return db.query(Order).order_by(Order.id.desc()).limit(200).all()


@router.put("/orders/{oid}/status", response_model=OrderOut)
def set_status(oid: int, data: StatusUpdate, db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Order not found")
    try:
        o.status = OrderStatus(data.status)
    except ValueError:
        raise HTTPException(400, "Invalid status")
    db.commit()
    return o


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.patch("/users/{uid}/active", response_model=UserOut)
def set_active(uid: int, data: ActiveUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot deactivate yourself")
    u.is_active = data.is_active
    db.commit()
    return u


@router.get("/audit-logs", response_model=list[AuditLogOut])
def audit_logs(action: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    """Append-only event trail, newest first.

    ``require_admin`` is already enforced for the whole router, so no customer
    can reach this endpoint.
    """
    return audit_service.list_recent(db, limit=limit, action=action)


@router.get("/chat-feedback", response_model=list[ChatFeedbackOut])
def chat_feedback(limit: int = 50, db: Session = Depends(get_db)):
    """Raw experience ratings, newest first."""
    rows = db.query(ChatFeedback).order_by(ChatFeedback.id.desc()).limit(max(1, min(limit, 200))).all()
    return rows
