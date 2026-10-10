"""Document kinds other modules register so staff can send them on WhatsApp.

A module adds a kind by calling ``register_document_kind`` with:

- ``key``: stable id the UI sends, such as ``pharmacy_sale``
- ``template_family``: one of invoice, lab_report, prescription, discharge
- ``load``: builds the PDF and returns a ``PreparedDocument``
- ``suggest_phone``: optional lookup used to prefill the confirm dialog

``load`` must enforce the same permission as that document's download route
and raise ``HTTPException`` when the caller cannot have the PDF.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session


@dataclass
class PreparedDocument:
    pdf_bytes: bytes
    filename: str
    phone: str
    patient_name: str
    reference: str
    document_date: str
    resource_type: str
    resource_id: str
    template_family: str


Loader = Callable[[Session, object, str, Optional[bool]], PreparedDocument]
PhoneLookup = Callable[[Session, object, str], str]


@dataclass
class DocumentKind:
    key: str
    template_family: str
    load: Loader
    suggest_phone: Optional[PhoneLookup] = None


_kinds: dict[str, DocumentKind] = {}


def register_document_kind(kind: DocumentKind) -> None:
    _kinds[kind.key] = kind


def get_document_kind(key: str) -> Optional[DocumentKind]:
    return _kinds.get(key)


def list_document_kinds() -> list[str]:
    return sorted(_kinds)


def unregister_document_kind(key: str) -> None:
    _kinds.pop(key, None)
