from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas import CartItemIn, CartItemUpdate, CartOut
from app.services import cart_service as svc

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartOut)
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.serialize(svc.get_or_create_cart(db, user))


@router.post("/items", response_model=CartOut, status_code=201)
def add(data: CartItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.serialize(svc.add_item(db, user, data.product_id, data.quantity))


@router.put("/items/{item_id}", response_model=CartOut)
def update(item_id: int, data: CartItemUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.serialize(svc.update_item(db, user, item_id, data.quantity))


@router.delete("/items/{item_id}", response_model=CartOut)
def remove(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.serialize(svc.remove_item(db, user, item_id))
