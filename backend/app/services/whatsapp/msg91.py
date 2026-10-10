"""MSG91 WhatsApp template client. This is the only module that calls MSG91."""

import requests

SEND_URL = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"


class Msg91Error(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _request_id(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("request_id", "requestId", "message_id", "messageId", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("data", "payload", "result"):
        found = _request_id(payload.get(key))
        if found:
            return found
    return ""


def _error_text(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("message", "error", "detail", "errors"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    text = (response.text or "").strip()
    if text:
        return text[:300]
    return f"MSG91 returned HTTP {response.status_code}"


def send_document_template(
    *,
    auth_key: str,
    integrated_number: str,
    template_name: str,
    phone: str,
    media_url: str,
    filename: str,
    body_values: list[str],
) -> dict:
    components = {
        "header_1": {
            "type": "document",
            "value": media_url,
            "filename": filename,
        }
    }
    for index, value in enumerate(body_values, start=1):
        components[f"body_{index}"] = {"type": "text", "value": value or "-"}

    payload = {
        "integrated_number": integrated_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en", "policy": "deterministic"},
                "to_and_components": [
                    {"to": [phone], "components": components}
                ],
            },
        },
    }
    try:
        response = requests.post(
            SEND_URL,
            json=payload,
            headers={
                "accept": "application/json",
                "authkey": auth_key,
                "content-type": "application/json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise Msg91Error(f"Could not reach MSG91: {exc}") from exc
    if response.status_code >= 400:
        raise Msg91Error(_error_text(response))
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {"request_id": _request_id(body), "raw": body if isinstance(body, dict) else {}}
