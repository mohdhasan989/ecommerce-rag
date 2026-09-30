from tests.conftest import login

SHIP = {"full_name": "Test User", "address": "1 Main St", "city": "Ludhiana", "postal_code": "141001", "phone": "9999999999"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_register_creates_user_and_ignores_role(client):
    r = client.post("/api/auth/register", json={"name": "New One", "email": "new@x.com", "password": "Secret123!", "role": "ADMIN"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "USER"
    assert client.post("/api/auth/register", json={"name": "Dup", "email": "NEW@x.com", "password": "Secret123!"}).status_code == 409


def test_register_validation(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "bad", "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_me_and_failures(client, user_h):
    assert client.get("/api/auth/me", headers=user_h).json()["email"] == "alice@demo.com"
    assert client.post("/api/auth/login", json={"email": "alice@demo.com", "password": "wrong"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_admin_login(client, admin_h):
    assert client.get("/api/auth/me", headers=admin_h).json()["role"] == "ADMIN"


def test_products_and_filters(client):
    data = client.get("/api/products").json()
    assert data["total"] == 13 and data["items"][0]["images"]
    assert client.get("/api/products?search=headphones").json()["total"] == 1
    cats = client.get("/api/categories").json()
    assert len(cats) == 4
    shoes = next(c for c in cats if c["name"] == "Shoes")["id"]
    assert client.get(f"/api/products?category_id={shoes}").json()["total"] == 3
    prices = [p["price"] for p in client.get("/api/products?sort=price_asc&max_price=60").json()["items"]]
    assert prices and client.get("/api/products?min_price=1000").json()["total"] == 0
    assert client.get("/api/products/1").status_code == 200
    assert client.get("/api/products/9999").status_code == 404


def test_cart_flow(client, user2_h):
    assert client.get("/api/cart", headers=user2_h).json()["items"] == []
    r = client.post("/api/cart/items", json={"product_id": 1, "quantity": 2}, headers=user2_h)
    assert r.status_code == 201 and r.json()["item_count"] == 2
    item_id = r.json()["items"][0]["id"]
    assert client.put(f"/api/cart/items/{item_id}", json={"quantity": 3}, headers=user2_h).json()["item_count"] == 3
    assert client.post("/api/cart/items", json={"product_id": 1, "quantity": 9999}, headers=user2_h).status_code == 422
    assert client.delete(f"/api/cart/items/{item_id}", headers=user2_h).json()["items"] == []
    assert client.get("/api/cart").status_code == 401


def test_cart_isolated_between_users(client, user_h, user2_h):
    item_id = client.get("/api/cart", headers=user_h).json()["items"][0]["id"]
    assert client.put(f"/api/cart/items/{item_id}", json={"quantity": 1}, headers=user2_h).status_code == 404
    assert client.delete(f"/api/cart/items/{item_id}", headers=user2_h).status_code == 404


def test_place_order_and_retrieve(client, user2_h):
    assert client.post("/api/orders", json={"shipping": SHIP}, headers=user2_h).status_code == 400  # empty cart
    before = client.get("/api/products/1").json()["stock"]
    client.post("/api/cart/items", json={"product_id": 1, "quantity": 2}, headers=user2_h)
    r = client.post("/api/orders", json={"shipping": SHIP}, headers=user2_h)
    assert r.status_code == 201 and r.json()["total_amount"] == 319.98
    assert client.get("/api/products/1").json()["stock"] == before - 2
    assert client.get("/api/cart", headers=user2_h).json()["items"] == []
    oid = r.json()["id"]
    assert client.get(f"/api/orders/{oid}", headers=user2_h).json()["items"][0]["quantity"] == 2
    assert len(client.get("/api/orders", headers=user2_h).json()) == 2  # seeded + new


def test_orders_isolated(client, user_h, user2_h):
    bob_order = client.get("/api/orders", headers=user2_h).json()[0]["id"]
    assert client.get(f"/api/orders/{bob_order}", headers=user_h).status_code == 404
    assert client.get("/api/orders").status_code == 401


def test_admin_authorization(client, user_h, admin_h):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/stats", headers=user_h).status_code == 403
    assert client.get("/api/admin/users", headers=user_h).status_code == 403
    s = client.get("/api/admin/stats", headers=admin_h).json()
    assert s["total_products"] == 13 and s["total_users"] == 3 and len(s["recent_orders"]) == 2


def test_admin_product_crud(client, admin_h, user_h):
    body = {"name": "Test Item", "price": 50, "discount_price": 40, "stock": 5, "sku": "T-1", "category_id": 1, "image_urls": ["https://x/y.jpg"]}
    assert client.post("/api/admin/products", json=body, headers=user_h).status_code == 403
    r = client.post("/api/admin/products", json=body, headers=admin_h)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.post("/api/admin/products", json=body, headers=admin_h).status_code == 409
    assert client.put(f"/api/admin/products/{pid}", json={**body, "discount_price": 60}, headers=admin_h).status_code == 400
    assert client.put(f"/api/admin/products/{pid}", json={**body, "stock": 9}, headers=admin_h).json()["stock"] == 9
    assert client.delete(f"/api/admin/products/{pid}", headers=admin_h).status_code == 204
    assert client.get(f"/api/products/{pid}").status_code == 404


def test_admin_orders_users(client, admin_h):
    oid = client.get("/api/admin/orders", headers=admin_h).json()[0]["id"]
    assert client.put(f"/api/admin/orders/{oid}/status", json={"status": "SHIPPED"}, headers=admin_h).json()["status"] == "SHIPPED"
    assert client.put(f"/api/admin/orders/{oid}/status", json={"status": "NOPE"}, headers=admin_h).status_code == 400
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=admin_h).json() if u["email"] == "bob@demo.com")
    assert client.patch(f"/api/admin/users/{uid}/active", json={"is_active": False}, headers=admin_h).json()["is_active"] is False
    assert client.post("/api/auth/login", json={"email": "bob@demo.com", "password": "Password123!"}).status_code == 403


def test_profile_and_password(client, user_h):
    assert client.put("/api/auth/me", json={"name": "Alice X", "email": "alice@demo.com"}, headers=user_h).json()["name"] == "Alice X"
    assert client.put("/api/auth/me/password", json={"current_password": "bad", "new_password": "NewPass123!"}, headers=user_h).status_code == 400
    assert client.put("/api/auth/me/password", json={"current_password": "Password123!", "new_password": "NewPass123!"}, headers=user_h).status_code == 204
    login(client, "alice@demo.com", "NewPass123!")


def test_seed_is_idempotent(client):
    from app import seed as s
    s.seed()
    s.seed()
    assert client.get("/api/products").json()["total"] == 13
