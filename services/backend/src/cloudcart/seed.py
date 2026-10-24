"""Idempotent demo data: catalog products and the instructor account.

Run as `python -m cloudcart.seed` (the seed Job). Database settings come from
CLOUDCART_* variables like every other entry point; the instructor password comes
from CLOUDCART_SEED_ADMIN_PASSWORD, which a Kubernetes Secret provides. Reruns
insert only products whose SKU is missing, leaving existing rows (including
operator-changed stock and prices) untouched, and always store a fresh hash of the
current instructor password, so a rotated Secret takes effect on the next run.
"""

import os
import sys
from collections.abc import Mapping

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cloudcart.catalog.models import Product
from cloudcart.config import ConfigurationError, Settings
from cloudcart.db import Database
from cloudcart.identity.models import Instructor
from cloudcart.identity.schemas import PASSWORD_MAX_LENGTH
from cloudcart.identity.security import hash_password

ADMIN_PASSWORD_VARIABLE = "CLOUDCART_SEED_ADMIN_PASSWORD"
ADMIN_PASSWORD_MIN_LENGTH = 12
INSTRUCTOR_USERNAME = "instructor"

# Prices are USD cents. Product.image_path is /products/<sku>.svg, an image the storefront bundles.
PRODUCTS = (
    {
        "sku": "kube-mug",
        "name": "Kubernetes Mug",
        "description": "A 350 ml ceramic mug for long rollouts and short coffee breaks.",
        "price_cents": 1499,
        "stock": 40,
    },
    {
        "sku": "pod-hoodie",
        "name": "Pod Hoodie",
        "description": "A warm hoodie with room for one main container and a sidecar pocket.",
        "price_cents": 4999,
        "stock": 25,
    },
    {
        "sku": "helm-cap",
        "name": "Helm Cap",
        "description": "A six-panel cap that keeps the sun off your release charts.",
        "price_cents": 2199,
        "stock": 30,
    },
    {
        "sku": "node-sticker-pack",
        "name": "Node Sticker Pack",
        "description": "Ten vinyl stickers, one for every worker node you wish you had.",
        "price_cents": 599,
        "stock": 120,
    },
    {
        "sku": "yaml-notebook",
        "name": "YAML Notebook",
        "description": "A dotted A5 notebook where indentation errors cannot hurt you.",
        "price_cents": 899,
        "stock": 60,
    },
    {
        "sku": "container-tote",
        "name": "Container Tote",
        "description": "A sturdy canvas tote that packs everything your app needs to run.",
        "price_cents": 1799,
        "stock": 35,
    },
    {
        "sku": "cluster-socks",
        "name": "Cluster Socks",
        "description": "Three pairs, scheduled across your feet with anti-affinity.",
        "price_cents": 1299,
        "stock": 50,
    },
    {
        "sku": "gitops-poster",
        "name": "GitOps Poster",
        "description": "An A2 poster of the reconcile loop, the one true source of wall decor.",
        "price_cents": 1999,
        "stock": 20,
    },
)


def seed_database(session: Session, admin_password: str) -> None:
    """Insert missing products and upsert the instructor account with a fresh password hash."""
    session.execute(insert(Product).on_conflict_do_nothing(index_elements=[Product.sku]), list(PRODUCTS))
    instructor = insert(Instructor).values(username=INSTRUCTOR_USERNAME, password_hash=hash_password(admin_password))
    session.execute(
        instructor.on_conflict_do_update(
            index_elements=[Instructor.username], set_={"password_hash": instructor.excluded.password_hash}
        )
    )


def admin_password_from(environ: Mapping[str, str]) -> str:
    """Read the instructor password, raising ConfigurationError that never includes its value."""
    password = environ.get(ADMIN_PASSWORD_VARIABLE, "")
    if not ADMIN_PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ConfigurationError(
            f"{ADMIN_PASSWORD_VARIABLE} must be set to between {ADMIN_PASSWORD_MIN_LENGTH} "
            f"and {PASSWORD_MAX_LENGTH} characters."
        )
    return password


def main() -> None:
    settings = Settings.from_env()
    admin_password = admin_password_from(os.environ)
    database = Database(settings)
    try:
        with database.session_scope() as session:
            seed_database(session, admin_password)
    finally:
        database.dispose()


if __name__ == "__main__":
    try:
        main()
    except ConfigurationError as error:
        sys.exit(f"cloudcart.seed: {error}")
