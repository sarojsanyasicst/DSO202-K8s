"""Checkout, the caller's own orders, and the instructor's order overview.

A guest's order id only works for the guest session that placed the order.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from cloudcart.db import DbSession
from cloudcart.identity.models import Guest
from cloudcart.identity.routes import current_guest, current_instructor, guest_for_change
from cloudcart.orders.schemas import IDEMPOTENCY_KEY_PATTERN, AdminOrdersView, CheckoutRequest, OrderView, ReceiptView
from cloudcart.orders.service import (
    CheckoutConflictError,
    OrderNotFoundError,
    PaymentDeclinedError,
    ReceiptNotAvailableError,
    checkout,
    get_order,
    get_receipt,
    list_orders,
    order_overview,
)

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description="A new random value (8–128 of A-Z a-z 0-9 _ -) per checkout; resend it unchanged on retries.",
    ),
]

router = APIRouter(prefix="/orders", tags=["orders"])
admin_router = APIRouter(prefix="/admin/orders", tags=["admin"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"model": OrderView, "description": "A retry: the order this key and body already placed."},
        status.HTTP_402_PAYMENT_REQUIRED: {"description": "The simulated payment was declined; nothing changed."},
        status.HTTP_409_CONFLICT: {
            "description": "Stale or empty cart, not enough stock, or a key reused with a different body."
        },
    },
)
def place_order(
    body: CheckoutRequest,
    idempotency_key: IdempotencyKey,
    request: Request,
    response: Response,
    session: DbSession,
    guest: Annotated[Guest, Depends(guest_for_change)],
) -> OrderView:
    """Check out the caller's cart at current prices: charge stock, accept the order, and empty the cart."""
    try:
        result = checkout(session, guest.id, body.cart_version, body.payment_outcome, idempotency_key)
    except CheckoutConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except PaymentDeclinedError as error:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(error)) from None
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = request.app.url_path_for("read_order", order_id=str(result.order.id))
    return result.order


@router.get("")
def read_orders(session: DbSession, guest: Annotated[Guest, Depends(current_guest)]) -> list[OrderView]:
    """The caller's 50 most recent orders, newest first."""
    return list_orders(session, guest.id)


@router.get("/{order_id}", responses={status.HTTP_404_NOT_FOUND: {"description": "No such order for this guest."}})
def read_order(order_id: UUID, session: DbSession, guest: Annotated[Guest, Depends(current_guest)]) -> OrderView:
    try:
        return get_order(session, guest.id, order_id)
    except OrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.") from None


@router.get(
    "/{order_id}/receipt",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such order for this guest, or no receipt yet."}},
)
def read_receipt(order_id: UUID, session: DbSession, guest: Annotated[Guest, Depends(current_guest)]) -> ReceiptView:
    try:
        return get_receipt(session, guest.id, order_id)
    except OrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.") from None
    except ReceiptNotAvailableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The receipt is not available yet.") from None


@admin_router.get("", dependencies=[Depends(current_instructor)])
def read_order_overview(session: DbSession) -> AdminOrdersView:
    """Every guest's 50 most recent orders and counts over all orders (instructor only)."""
    return order_overview(session)
