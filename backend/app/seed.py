"""Idempotent demo data. Run: python -m app.seed"""
import json
from decimal import Decimal
from pydantic import EmailStr, TypeAdapter, ValidationError
from app.config import settings
from app.database import SessionLocal
from app.models import Category, Order, OrderItem, Product, ProductImage, User, UserRole
from app.services.cart_service import add_item
from app.utils.security import hash_password

U = "https://images.unsplash.com/photo-{}?w=800&q=80"
CATS = {"Electronics": "Gadgets, audio and everyday tech", "Clothing": "Modern essentials for every season",
        "Shoes": "Sneakers, runners and boots", "Accessories": "Bags, watches and finishing touches"}
# name, category, brand, sku, price, discount, stock, photo id, description
PRODUCTS = [
    ("Wireless Noise-Cancelling Headphones", "Electronics", "Sonix", "EL-HP-001", 199.99, 159.99, 40, "1505740420928-5e560c06d30e", "Over-ear Bluetooth headphones with 30-hour battery and active noise cancellation."),
    ("Smart Watch Series 5", "Electronics", "Pulsar", "EL-SW-002", 249.00, None, 25, "1523275335684-37898b6baf30", "Fitness tracking, heart-rate monitor and a bright AMOLED display."),
    ("Portable Bluetooth Speaker", "Electronics", "Sonix", "EL-SP-003", 79.00, 59.00, 60, "1608043152269-423dbba4e7e1", "Waterproof 360° sound with 12 hours of playtime."),
    ("Mechanical Keyboard", "Electronics", "KeyCraft", "EL-KB-004", 129.00, None, 30, "1587829741301-dc798b83add3", "Hot-swappable switches, RGB backlight and aluminium frame."),
    ("Classic Cotton T-Shirt", "Clothing", "Northline", "CL-TS-001", 24.99, None, 120, "1521572163474-6864f9cf17ab", "Soft 100% organic cotton tee in a relaxed fit."),
    ("Slim Fit Denim Jacket", "Clothing", "Northline", "CL-DJ-002", 89.00, 69.00, 35, "1576995853123-5a10305d93c0", "Timeless denim jacket with a modern slim cut."),
    ("Merino Wool Sweater", "Clothing", "Alder & Co", "CL-SW-003", 119.00, None, 28, "1434389677669-e08b4cac3105", "Lightweight merino knit that keeps you warm without bulk."),
    ("Everyday Running Shoes", "Shoes", "Stride", "SH-RN-001", 110.00, 89.00, 50, "1542291026-7eec264c27ff", "Cushioned, breathable trainers for daily miles."),
    ("Leather Chelsea Boots", "Shoes", "Alder & Co", "SH-CB-002", 159.00, None, 18, "1608256246200-53e635b5b65f", "Full-grain leather boots with elastic side panels."),
    ("Minimal White Sneakers", "Shoes", "Stride", "SH-WS-003", 95.00, None, 64, "1549298916-b41d501d3772", "Clean low-top sneakers that go with everything."),
    ("Leather Crossbody Bag", "Accessories", "Alder & Co", "AC-CB-001", 135.00, 109.00, 22, "1548036328-c9fa89d128fa", "Compact genuine-leather bag with an adjustable strap."),
    ("Aviator Sunglasses", "Accessories", "Pulsar", "AC-SG-002", 65.00, None, 80, "1572635196237-14b3f281503f", "Polarised UV400 lenses in a lightweight metal frame."),
    ("Canvas Backpack", "Accessories", "Northline", "AC-BP-003", 59.00, 45.00, 70, "1553062407-98eeb64c6a62", "Water-resistant 20L backpack with padded laptop sleeve."),
]
DEMO_USERS = [("Alice Demo", "alice@demo.com"), ("Bob Demo", "bob@demo.com")]
DEMO_PASSWORD = "Password123!"


def seed():
    try:
        TypeAdapter(EmailStr).validate_python(settings.ADMIN_EMAIL)
    except ValidationError:
        raise SystemExit(f"ADMIN_EMAIL '{settings.ADMIN_EMAIL}' is not accepted (reserved domains like .local/.test are rejected). Use e.g. admin@yourdomain.com")
    db = SessionLocal()
    try:
        cats = {}
        for name, desc in CATS.items():
            c = db.query(Category).filter_by(name=name).first() or Category(name=name, description=desc)
            db.add(c)
            cats[name] = c
        db.flush()
        for name, cat, brand, sku, price, disc, stock, photo, desc in PRODUCTS:
            if db.query(Product).filter_by(sku=sku).first():
                continue
            p = Product(name=name, description=desc, price=Decimal(str(price)),
                        discount_price=Decimal(str(disc)) if disc else None, stock=stock, sku=sku,
                        brand=brand, category_id=cats[cat].id)
            p.images = [ProductImage(image_url=U.format(photo))]
            db.add(p)
        if settings.ADMIN_PASSWORD and not db.query(User).filter_by(email=settings.ADMIN_EMAIL.lower()).first():
            db.add(User(name="Store Admin", email=settings.ADMIN_EMAIL.lower(),
                        password_hash=hash_password(settings.ADMIN_PASSWORD), role=UserRole.ADMIN))
        elif not settings.ADMIN_PASSWORD:
            print("! ADMIN_PASSWORD not set in .env - admin account was NOT created")
        users = []
        for name, email in DEMO_USERS:
            u = db.query(User).filter_by(email=email).first() or User(
                name=name, email=email, password_hash=hash_password(DEMO_PASSWORD), role=UserRole.USER)
            db.add(u)
            users.append(u)
        db.commit()
        # sample orders (only once per demo user) and a sample cart
        prods = db.query(Product).order_by(Product.id).all()
        for i, u in enumerate(users):
            if db.query(Order).filter_by(user_id=u.id).first():
                continue
            order = Order(user_id=u.id, total_amount=Decimal("0"), status="DELIVERED" if i == 0 else "PROCESSING",
                          shipping_address=json.dumps({"full_name": u.name, "address": "12 Market Street",
                                                       "city": "Ludhiana", "postal_code": "141001", "phone": "9876543210"}))
            total = Decimal("0")
            for p, q in ((prods[i], 1), (prods[i + 4], 2)):
                price = p.unit_price
                order.items.append(OrderItem(product_id=p.id, quantity=q, price=price, subtotal=price * q))
                total += price * q
            order.total_amount = total
            db.add(order)
        db.commit()
        alice = users[0]
        if not alice.cart or not alice.cart.items:
            add_item(db, alice, prods[2].id, 1)
            add_item(db, alice, prods[7].id, 2)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
