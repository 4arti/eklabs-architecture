"""Import every model so Alembic's autogenerate (target_metadata = Base.metadata)
sees all of them, regardless of which module actually gets imported first."""

from eklabs_platform.core.db.models.app_user import AppUser
from eklabs_platform.core.db.models.audit_log import AuditLog
from eklabs_platform.core.db.models.chunk import Chunk
from eklabs_platform.core.db.models.document import Document
from eklabs_platform.core.db.models.page import Page
from eklabs_platform.core.db.models.tenant import Tenant

__all__ = ["AppUser", "AuditLog", "Chunk", "Document", "Page", "Tenant"]
