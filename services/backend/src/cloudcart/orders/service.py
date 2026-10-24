"""Checkout and order reads.

Checkout turns the guest's cart into an accepted order in one transaction:
it locks the guest's cart row, then the cart's product rows in product-id order,
charges stock with guarded updates, records the order at current server-side
prices, writes the order's outbox event, and empties the cart. Every writer
locks a cart before products, and products in id order, so checkouts cannot
deadlock one another. Cart changes take only KEY SHARE locks on products, which
do not conflict with checkout's NO KEY UPDATE locks.

An Idempotency-Key names one checkout of one guest. A retry with the same key and
body returns the existing order; the same key with a different body is refused.
Only accepted orders record their key: a declined or refused attempt leaves no
trace, so retrying it is evaluated afresh.
"""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from cloudcart.cart.models import CartItem
from cloudcart.cart.service import clear_cart, lock_guest_cart
from cloudcart.catalog.models import Product
from cloudcart.orders.models import ORDER_STATUSES, Order, OrderItem, OutboxEvent
from cloudcart.orders.schemas import (
    AdminOrdersView,
    AdminOrderView,
    OrderItemView,
    OrderStatusCounts,
    OrderView,
    PaymentOutcome,
    ReceiptView,
)

MAX_LISTED_ORDERS = 50


@dataclass(frozen=True)
class CheckoutResult:
    order: OrderView
    replayed: bool  # True when an earlier request with the same key and body created the order


class CheckoutConflictError(Exception):
    """The checkout cannot proceed in the cart's or the key's current state."""


class IdempotencyKeyReusedError(CheckoutConflictError):
    """The key already belongs to an order placed with a different request body."""


class StaleCartError(CheckoutConflictError):
    """The cart changed after the shopper reviewed it."""


class EmptyCartError(CheckoutConflictError):
    """There is nothing to check out."""


class InsufficientStockError(CheckoutConflictError):
    """A cart line asks for more units than are in stock."""


class PaymentDeclinedError(Exception):
    """The simulated payment was declined."""


class OrderNotFoundError(LookupError):
    """No order with this id belongs to the guest."""


class ReceiptNotAvailableError(LookupError):
    """The guest's order has no receipt yet."""


def request_fingerprint(cart_version: int, payment_outcome: PaymentOutcome) -> str:
    """SHA-256 of the canonical checkout request body."""
    body = json.dumps({"cart_version": cart_version, "payment_outcome": payment_outcome}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def checkout(
    session: Session, guest_id: UUID, cart_version: int, payment_outcome: PaymentOutcome, idempotency_key: str
) -> CheckoutResult:
    """Place the guest's cart as an order, or return the order an identical earlier request placed."""
    fingerprint = request_fingerprint(cart_version, payment_outcome)
    # The cart lock serializes this guest's checkouts and cart changes, so a concurrent
    # retry waits here and then finds the order the first request committed.
    cart = lock_guest_cart(session, guest_id)
    earlier = session.execute(
        select(Order.id, Order.request_fingerprint).where(
            Order.guest_id == guest_id, Order.idempotency_key == idempotency_key
        )
    ).one_or_none()
    if earlier is not None:
        if earlier.request_fingerprint != fingerprint:
            raise IdempotencyKeyReusedError("This Idempotency-Key was already used for a different checkout request.")
        return CheckoutResult(order=get_order(session, guest_id, earlier.id), replayed=True)

    if cart.version != cart_version:
        raise StaleCartError("The cart changed since it was reviewed; reload the cart and check out again.")
    lines = session.execute(
        select(CartItem.quantity, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(Product.id)
        .with_for_update(of=Product, key_share=True)  # FOR NO KEY UPDATE OF products
        .execution_options(populate_existing=True)
    ).all()
    if not lines:
        raise EmptyCartError("The cart is empty.")
    short = [product.name for quantity, product in lines if quantity > product.stock]
    if short:
        raise InsufficientStockError(f"Not enough stock for: {', '.join(short)}.")
    if payment_outcome == "declined":
        raise PaymentDeclinedError("The simulated payment was declined.")

    for quantity, product in lines:
        _charge_stock(session, product, quantity)
    order = Order(
        guest_id=guest_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        total_cents=sum(quantity * product.price_cents for quantity, product in lines),
        items=[
            OrderItem(product_id=product.id, name=product.name, quantity=quantity, unit_price_cents=product.price_cents)
            for quantity, product in lines
        ],
        outbox_event=OutboxEvent(),
    )
    session.add(order)
    clear_cart(session, cart)
    session.flush()
    return CheckoutResult(order=get_order(session, guest_id, order.id), replayed=False)


def get_order(session: Session, guest_id: UUID, order_id: UUID) -> OrderView:
    return _order_view(_guest_order(session, guest_id, order_id))


def list_orders(session: Session, guest_id: UUID) -> list[OrderView]:
    """The guest's most recent orders, newest first."""
    orders = session.scalars(
        select(Order)
        .where(Order.guest_id == guest_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(MAX_LISTED_ORDERS)
    )
    return [_order_view(order) for order in orders]


def get_receipt(session: Session, guest_id: UUID, order_id: UUID) -> ReceiptView:
    order = _guest_order(session, guest_id, order_id)
    if order.receipt is None:
        raise ReceiptNotAvailableError(order_id)
    return ReceiptView(
        id=order.receipt.id,
        order_id=order.id,
        issued_at=order.receipt.issued_at,
        items=_item_views(order),
        total_cents=order.total_cents,
        currency=order.currency,
    )


def order_overview(session: Session) -> AdminOrdersView:
    """Every guest's most recent orders for the instructor, with counts over all orders."""
    counts = dict.fromkeys(ORDER_STATUSES, 0)
    by_status = session.execute(select(Order.status, func.count()).group_by(Order.status))
    counts.update({status: count for status, count in by_status})
    pending = session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.published_at.is_(None)))
    orders = session.scalars(
        select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(MAX_LISTED_ORDERS)
    )
    return AdminOrdersView(
        status_counts=OrderStatusCounts(**counts),
        publication_pending=pending or 0,
        orders=[
            AdminOrderView(
                id=order.id,
                status=order.status,
                publication_pending=_publication_pending(order),
                fulfillment_attempts=order.fulfillment_attempts,
                item_count=sum(item.quantity for item in order.items),
                total_cents=order.total_cents,
                created_at=order.created_at,
                receipt_available=order.receipt is not None,
            )
            for order in orders
        ],
    )


def _charge_stock(session: Session, product: Product, quantity: int) -> None:
    """Take `quantity` units; the WHERE guard keeps stock from going negative even without the row lock."""
    charged = session.execute(
        update(Product)
        .where(Product.id == product.id, Product.stock >= quantity)
        .values(stock=Product.stock - quantity)
    )
    if charged.rowcount != 1:
        raise InsufficientStockError(f"Not enough stock for: {product.name}.")


def _guest_order(session: Session, guest_id: UUID, order_id: UUID) -> Order:
    """The guest's own order. Another guest's order is reported exactly like a missing one."""
    order = session.scalars(select(Order).where(Order.id == order_id, Order.guest_id == guest_id)).one_or_none()
    if order is None:
        raise OrderNotFoundError(order_id)
    return order


def _order_view(order: Order) -> OrderView:
    return OrderView(
        id=order.id,
        status=order.status,
        publication_pending=_publication_pending(order),
        total_cents=order.total_cents,
        created_at=order.created_at,
        receipt_available=order.receipt is not None,
        items=_item_views(order),
    )


def _publication_pending(order: Order) -> bool:
    return order.outbox_event is not None and order.outbox_event.published_at is None


def _item_views(order: Order) -> list[OrderItemView]:
    items = sorted(order.items, key=lambda item: (item.name, item.product_id))
    return [OrderItemView.model_validate(item) for item in items]
