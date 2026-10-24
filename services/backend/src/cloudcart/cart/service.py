"""Cart rules: one cart per guest, line and stock limits, and a version that counts changes.

Every change locks the guest's cart row for the rest of the transaction, so
concurrent changes to one cart apply one at a time and each increments the
version by exactly one. Writers lock the cart row before any product row:
checkout (orders/service.py) relies on that order to avoid deadlocks.
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cloudcart.cart.models import Cart, CartItem
from cloudcart.cart.schemas import MAX_LINE_QUANTITY, CartItemView, CartView
from cloudcart.catalog.models import Product

MAX_CART_LINES = 20


class UnknownProductError(LookupError):
    """No product has the requested id."""


class CartLineNotFoundError(LookupError):
    """The cart has no line for the requested product."""


class CartConflictError(Exception):
    """The change would exceed a cart limit or the product's current stock."""


def get_cart(session: Session, guest_id: UUID) -> CartView:
    """The guest's cart; a guest who never changed it gets an empty cart at version 0."""
    return _cart_view(session, _guest_cart(session, guest_id, lock=False))


def set_cart_item(session: Session, guest_id: UUID, product_id: UUID, quantity: int) -> CartView:
    """Set (not add to) the quantity of one product in the guest's cart."""
    if not 1 <= quantity <= MAX_LINE_QUANTITY:
        raise ValueError(f"quantity must be between 1 and {MAX_LINE_QUANTITY}")
    product = session.get(Product, product_id)
    if product is None:
        raise UnknownProductError(product_id)
    if quantity > product.stock:
        raise CartConflictError(f"Only {product.stock} of this product are in stock.")

    cart = _guest_cart(session, guest_id, lock=True)
    item = session.get(CartItem, (cart.id, product_id))
    if item is not None:
        item.quantity = quantity
    elif _line_count(session, cart.id) >= MAX_CART_LINES:
        raise CartConflictError(f"A cart holds at most {MAX_CART_LINES} different products.")
    else:
        session.add(CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity))
    return _record_change(session, cart)


def remove_cart_item(session: Session, guest_id: UUID, product_id: UUID) -> CartView:
    """Remove one product's line from the guest's cart."""
    cart = _guest_cart(session, guest_id, lock=True)
    removed = session.execute(
        delete(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
    )
    if removed.rowcount == 0:
        raise CartLineNotFoundError(product_id)
    return _record_change(session, cart)


def lock_guest_cart(session: Session, guest_id: UUID) -> Cart:
    """The guest's cart row, created empty on first use and locked until the transaction ends.

    Take this lock before locking any product row.
    """
    return _guest_cart(session, guest_id, lock=True)


def clear_cart(session: Session, cart: Cart) -> CartView:
    """Remove every line from a cart locked with `lock_guest_cart`; emptying it counts as one change."""
    session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    return _record_change(session, cart)


def _guest_cart(session: Session, guest_id: UUID, *, lock: bool) -> Cart:
    """The guest's cart, created empty on first use. With `lock`, the row stays locked until the transaction ends."""
    query = select(Cart).where(Cart.guest_id == guest_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    cart = session.scalars(query).one_or_none()
    if cart is None:
        # Concurrent first requests may both get here; ON CONFLICT lets exactly one INSERT win.
        session.execute(insert(Cart).values(guest_id=guest_id).on_conflict_do_nothing(index_elements=[Cart.guest_id]))
        cart = session.scalars(query).one()
    return cart


def _line_count(session: Session, cart_id: UUID) -> int:
    return session.scalar(select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart_id)) or 0


def _record_change(session: Session, cart: Cart) -> CartView:
    cart.version = Cart.version + 1
    session.flush()
    return _cart_view(session, cart)


def _cart_view(session: Session, cart: Cart) -> CartView:
    rows = session.execute(
        select(CartItem.product_id, CartItem.quantity, Product.price_cents)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(Product.name, Product.id)
    )
    items = [
        CartItemView(product_id=product_id, quantity=quantity, unit_price_cents=price_cents)
        for product_id, quantity, price_cents in rows
    ]
    return CartView(
        id=cart.id,
        version=cart.version,
        items=items,
        total_cents=sum(item.quantity * item.unit_price_cents for item in items),
    )
