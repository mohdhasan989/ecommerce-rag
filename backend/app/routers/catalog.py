from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Category, Product
from app.schemas import CategoryOut, ProductOut, ProductPage
from app.services import product_service

products = APIRouter(prefix="/products", tags=["products"])
categories = APIRouter(prefix="/categories", tags=["categories"])


@products.get("", response_model=ProductPage)
def list_(search: str | None = None, category_id: int | None = None, min_price: float | None = Query(None, ge=0),
          max_price: float | None = Query(None, ge=0),
          sort: Literal["newest", "price_asc", "price_desc", "name"] = "newest",
          page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=100), db: Session = Depends(get_db)):
    return product_service.list_products(db, search, category_id, min_price, max_price, sort, page, limit)


@products.get("/{product_id}", response_model=ProductOut)
def get_(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p or not p.is_active:
        raise HTTPException(404, "Product not found")
    return p


@categories.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name).all()
