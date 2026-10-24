"""The caller's own cart. There is no cart id in any URL: the guest session selects the cart."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from cloudcart.cart.schemas import CartItemQuantity, CartView
from cloudcart.cart.service import (
    CartConflictError,
    CartLineNotFoundError,
    UnknownProductError,
    get_cart,
    remove_cart_item,
    set_cart_item,
)
from cloudcart.db import DbSession
from cloudcart.identity.models import Guest
from cloudcart.identity.routes import current_guest, guest_for_change

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("")
def read_cart(session: DbSession, guest: Annotated[Guest, Depends(current_guest)]) -> CartView:
    """The caller's cart; the first read creates it empty at version 0."""
    return get_cart(session, guest.id)


@router.put("/items/{product_id}")
def set_item(
    product_id: UUID,
    change: CartItemQuantity,
    session: DbSession,
    guest: Annotated[Guest, Depends(guest_for_change)],
) -> CartView:
    """Set a product's quantity in the caller's cart. 404: unknown product; 409: line or stock limit."""
    try:
        return set_cart_item(session, guest.id, product_id, change.quantity)
    except UnknownProductError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.") from None
    except CartConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


@router.delete("/items/{product_id}")
def remove_item(
    product_id: UUID, session: DbSession, guest: Annotated[Guest, Depends(guest_for_change)]
) -> CartView:
    """Remove a product from the caller's cart and return the updated cart. 404: not in the cart."""
    try:
        return remove_cart_item(session, guest.id, product_id)
    except CartLineNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product is not in the cart.") from None
