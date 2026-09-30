from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin

PRODUCT_CLASSES = ("small_molecule", "biologic")


class Product(Base, UUIDPkMixin, TenantScopedMixin):
    """A drug product a tenant may submit applications for (spec §4).

    Immutable for now — no established mutation story like document.status
    has, so no updated_at column. A rename/correction workflow is a
    deliberate future decision (possibly a product_version table), not a
    default column added just in case.
    """

    __tablename__ = "product"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        # Composite-FK target for application.product_id.
        UniqueConstraint("id", "tenant_id"),
        CheckConstraint(
            "product_class IN (" + ", ".join(f"'{c}'" for c in PRODUCT_CLASSES) + ")",
            name="product_class_valid",
        ),
    )

    name: Mapped[str] = mapped_column(nullable=False)
    # International Nonproprietary Name — nullable, not every early-stage
    # product has one assigned yet.
    inn: Mapped[str | None]
    dosage_form: Mapped[str] = mapped_column(nullable=False)
    # Free text (e.g. "10 mg") per spec §4's literal column; a structured,
    # reusable value belongs in `fact` (subject_key='product.strength')
    # once that table exists — out of scope here.
    strength: Mapped[str] = mapped_column(nullable=False)
    product_class: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
