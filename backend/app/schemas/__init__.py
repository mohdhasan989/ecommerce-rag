import json
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):  # deliberately has NO role field
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, v):
        return getattr(v, "value", v)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class CategoryOut(ORM, CategoryIn):
    id: int


class ImageOut(ORM):
    id: int
    image_url: str


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: float = Field(gt=0)
    discount_price: float | None = Field(default=None, gt=0)
    stock: int = Field(ge=0)
    sku: str = Field(min_length=1, max_length=64)
    brand: str | None = None
    category_id: int | None = None
    is_active: bool = True
    image_urls: list[str] = []


class ProductOut(ORM):
    id: int
    name: str
    description: str | None
    price: float
    discount_price: float | None
    stock: int
    sku: str
    brand: str | None
    category_id: int | None
    category_name: str | None
    is_active: bool
    images: list[ImageOut]


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    limit: int


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=99)


class CartItemOut(BaseModel):
    id: int
    product: ProductOut
    quantity: int
    unit_price: float
    line_total: float


class CartOut(BaseModel):
    id: int
    items: list[CartItemOut]
    item_count: int
    subtotal: float
    total: float


class ShippingIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=3, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    phone: str = Field(min_length=6, max_length=20)


class OrderCreate(BaseModel):
    shipping: ShippingIn


class OrderItemOut(ORM):
    id: int
    product_id: int
    product_name: str | None
    image_url: str | None
    quantity: int
    price: float
    subtotal: float


class OrderOut(ORM):
    id: int
    user_id: int
    total_amount: float
    status: str
    shipping_address: dict
    created_at: datetime
    items: list[OrderItemOut]

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        return getattr(v, "value", v)

    @field_validator("shipping_address", mode="before")
    @classmethod
    def _addr(cls, v):
        return json.loads(v) if isinstance(v, str) else v


class StatusUpdate(BaseModel):
    status: str


class ActiveUpdate(BaseModel):
    is_active: bool


class AuditLogOut(ORM):
    id: int
    action: str
    details: str
    user_id: int | None = None
    created_at: datetime


class ChatFeedbackOut(ORM):
    id: int
    conversation_id: str
    rating: int
    user_id: int | None = None
    created_at: datetime
