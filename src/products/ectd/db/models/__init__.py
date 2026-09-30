"""Import every model so Alembic's autogenerate (target_metadata = Base.metadata)
sees all of them, regardless of which module actually gets imported first."""

from products.ectd.db.models.application import Application
from products.ectd.db.models.product import Product
from products.ectd.db.models.section import Section

__all__ = ["Application", "Product", "Section"]
