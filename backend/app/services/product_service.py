from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.models import Product, ProductImage

SORTS = {"newest": Product.id.desc(), "name": Product.name.asc()}


def list_products(db: Session, search=None, category_id=None, min_price=None, max_price=None,
                  sort="newest", page=1, limit=12, include_inactive=False):
    q = db.query(Product)
    if not include_inactive:
        q = q.filter(Product.is_active.is_(True))
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Product.name.like(like), Product.brand.like(like), Product.description.like(like)))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    eff = func.coalesce(Product.discount_price, Product.price)
    if min_price is not None:
        q = q.filter(eff >= min_price)
    if max_price is not None:
        q = q.filter(eff <= max_price)
    total = q.count()
    orders = {"price_asc": eff.asc(), "price_desc": eff.desc(), **SORTS}
    order = orders.get(sort, Product.id.desc())
    items = q.order_by(order).offset((page - 1) * limit).limit(limit).all()
    return {"items": items, "total": total, "page": page, "limit": limit}


def save_product(db: Session, data, product: Product | None = None) -> Product:
    d = data.model_dump()
    urls = d.pop("image_urls")
    if d["discount_price"] is not None and d["discount_price"] >= d["price"]:
        raise HTTPException(400, "Discount price must be lower than price")
    clash = db.query(Product).filter(Product.sku == d["sku"])
    if product:
        clash = clash.filter(Product.id != product.id)
    if clash.first():
        raise HTTPException(409, "SKU already exists")
    product = product or Product()
    for k, v in d.items():
        setattr(product, k, v)
    product.images = [ProductImage(image_url=u) for u in urls]
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
