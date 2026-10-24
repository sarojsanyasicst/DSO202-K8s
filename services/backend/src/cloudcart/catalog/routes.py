"""Public product listing and instructor stock changes."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update

from cloudcart.catalog.models import Product
from cloudcart.catalog.schemas import ProductView, StockUpdate
from cloudcart.db import DbSession
from cloudcart.identity.routes import instructor_for_change

router = APIRouter(tags=["catalog"])


@router.get("/products", response_model=list[ProductView])
def list_products(session: DbSession) -> Sequence[Product]:
    """List every product with its current price and available stock. No session is needed."""
    return session.scalars(select(Product).order_by(Product.name, Product.id)).all()


@router.put(
    "/admin/products/{product_id}/stock",
    response_model=ProductView,
    dependencies=[Depends(instructor_for_change)],
)
def set_stock(product_id: UUID, change: StockUpdate, session: DbSession) -> Product:
    """Set a product's available stock (instructor only)."""
    product = session.scalars(
        update(Product).where(Product.id == product_id).values(stock=change.stock).returning(Product)
    ).one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    return product
