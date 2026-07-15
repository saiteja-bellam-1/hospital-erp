"""Unit tests for discharge summary template validation/service."""

from app.services.discharge_summary_template_service import (
    build_default_template,
    standard_section_content,
    validate_summary_against_template,
    validate_template,
)


def test_default_template_valid():
    tpl = build_default_template()
    out = validate_template(tpl)
    assert out["version"] == 1
    assert len(out["blocks"]) >= 10
    assert any(
        b["type"] == "standard_section" and b["field_key"] == "primary_diagnosis" and b["required"]
        for b in out["blocks"]
    )


def test_validate_rejects_duplicate_standard():
    tpl = build_default_template()
    tpl["blocks"].append({
        "id": "dup",
        "type": "standard_section",
        "field_key": "primary_diagnosis",
        "label": "Dup",
        "required": False,
    })
    try:
        validate_template(tpl)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Duplicate" in str(e)


def test_validate_custom_field_slug():
    tpl = {
        "version": 1,
        "document_title": "X",
        "show_department_line": True,
        "blocks": [{
            "id": "1",
            "type": "custom_field",
            "field_key": "Bad Key!",
            "label": "Bad",
            "input": "text",
        }],
    }
    try:
        validate_template(tpl)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "slug" in str(e).lower() or "field_key" in str(e).lower()


def test_standard_section_content_fallbacks():
    data = {
        "primary_diagnosis": "",
        "diagnosis": "Legacy dx",
        "course_in_hospital": "",
        "treatment": "Legacy tx",
    }
    assert standard_section_content(data, "primary_diagnosis") == "Legacy dx"
    assert standard_section_content(data, "course_in_hospital") == "Legacy tx"


class _Summary:
    def __init__(self, **kw):
        self.primary_diagnosis = kw.get("primary_diagnosis", "")
        self.custom_fields = kw.get("custom_fields", {})
        for k, v in kw.items():
            setattr(self, k, v)


def test_validate_summary_required_custom():
    tpl = {
        "version": 1,
        "document_title": "X",
        "show_department_line": True,
        "blocks": [
            {
                "id": "1",
                "type": "standard_section",
                "field_key": "primary_diagnosis",
                "label": "Primary Diagnosis",
                "required": True,
            },
            {
                "id": "2",
                "type": "custom_field",
                "field_key": "notes",
                "label": "Notes",
                "input": "textarea",
                "required": True,
            },
        ],
    }
    tpl = validate_template(tpl)
    err = validate_summary_against_template(
        _Summary(primary_diagnosis="OK", custom_fields={}), tpl)
    assert err and "Notes" in err
    err2 = validate_summary_against_template(
        _Summary(primary_diagnosis="OK", custom_fields={"notes": "filled"}), tpl)
    assert err2 is None
