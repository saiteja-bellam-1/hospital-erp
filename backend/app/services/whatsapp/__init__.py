"""WhatsApp document sending for any hospital module.

Other modules register a document kind (see ``registry.py``) or call
``send_prepared_document`` when they already have PDF bytes.
"""

from app.services.whatsapp.registry import (
    DocumentKind,
    PreparedDocument,
    get_document_kind,
    list_document_kinds,
    register_document_kind,
)
from app.services.whatsapp.sender import send_prepared_document

__all__ = [
    "DocumentKind",
    "PreparedDocument",
    "get_document_kind",
    "list_document_kinds",
    "register_document_kind",
    "send_prepared_document",
]
