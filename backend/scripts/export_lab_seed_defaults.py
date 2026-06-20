#!/usr/bin/env python3
"""Export active lab tests from a hospital DB into _get_seed_data() Python source."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.paths import get_db_path


def _parse_json(value):
    if value is None or value == "null":
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _compact_range(row: dict) -> dict:
    out = {}
    if row.get("min") is not None:
        out["min"] = row["min"]
    if row.get("max") is not None:
        out["max"] = row["max"]
    gender = row.get("gender") or "common"
    if gender != "common":
        out["gender"] = gender
    if row.get("age_min") is not None:
        out["age_min"] = row["age_min"]
    if row.get("age_max") is not None:
        out["age_max"] = row["age_max"]
    if row.get("description"):
        out["description"] = row["description"]
    return out


def _legacy_to_ranges(param: dict) -> list[dict] | None:
    stored = _parse_json(param.get("reference_ranges"))
    if stored:
        return [_compact_range(row) for row in stored]

    ranges: list[dict] = []
    if param.get("reference_min_male") is not None or param.get("reference_max_male") is not None:
        ranges.append(_compact_range({
            "min": param.get("reference_min_male"),
            "max": param.get("reference_max_male"),
            "gender": "male",
        }))
    if param.get("reference_min_female") is not None or param.get("reference_max_female") is not None:
        ranges.append(_compact_range({
            "min": param.get("reference_min_female"),
            "max": param.get("reference_max_female"),
            "gender": "female",
        }))
    if param.get("reference_min_default") is not None or param.get("reference_max_default") is not None:
        ranges.append(_compact_range({
            "min": param.get("reference_min_default"),
            "max": param.get("reference_max_default"),
            "gender": "common",
        }))
    if param.get("reference_min_child") is not None or param.get("reference_max_child") is not None:
        ranges.append(_compact_range({
            "min": param.get("reference_min_child"),
            "max": param.get("reference_max_child"),
            "gender": "child",
        }))
    return ranges or None


def _param_to_seed(param: dict) -> dict:
    out = {"name": param["parameter_name"]}
    if param.get("unit"):
        out["unit"] = param["unit"]
    if param.get("field_type") and param["field_type"] != "numeric":
        out["field_type"] = param["field_type"]
    for key in ("section", "method", "notes", "normal_value"):
        if param.get(key):
            out[key] = param[key]
    ranges = _legacy_to_ranges(param)
    if ranges:
        out["reference_ranges"] = ranges
    possible_values = _parse_json(param.get("possible_values"))
    if possible_values:
        out["possible_values"] = possible_values
    abnormal_values = _parse_json(param.get("abnormal_values"))
    if abnormal_values:
        out["abnormal_values"] = abnormal_values
    if param.get("critical_low") is not None:
        out["critical_low"] = param["critical_low"]
    if param.get("critical_high") is not None:
        out["critical_high"] = param["critical_high"]
    return out


def _format_param(param: dict) -> str:
    parts = [f'"name": {json.dumps(param["name"])}']
    for key in (
        "unit", "field_type", "section", "method", "notes", "normal_value",
        "critical_low", "critical_high",
    ):
        if key in param:
            parts.append(f'"{key}": {json.dumps(param[key])}')
    if param.get("reference_ranges"):
        range_parts = []
        for row in param["reference_ranges"]:
            row_parts = []
            if "min" in row:
                row_parts.append(f'"min": {row["min"]}')
            if "max" in row:
                row_parts.append(f'"max": {row["max"]}')
            if row.get("gender") and row.get("gender") != "common":
                row_parts.append(f'"gender": {json.dumps(row["gender"])}')
            if "age_min" in row:
                row_parts.append(f'"age_min": {row["age_min"]}')
            if "age_max" in row:
                row_parts.append(f'"age_max": {row["age_max"]}')
            if row.get("description"):
                row_parts.append(f'"description": {json.dumps(row["description"])}')
            range_parts.append("{" + ", ".join(row_parts) + "}")
        parts.append(f'"reference_ranges": [{", ".join(range_parts)}]')
    if param.get("possible_values"):
        parts.append(f'"possible_values": {json.dumps(param["possible_values"])}')
    if param.get("abnormal_values"):
        parts.append(f'"abnormal_values": {json.dumps(param["abnormal_values"])}')
    return "{" + ", ".join(parts) + "}"


def export_seed_data(db_path: str) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tests = conn.execute(text("""
            SELECT t.test_code, t.name, t.description, t.cost, t.sample_type, t.method,
                   t.preparation_instructions, c.name AS category_name, t.id
            FROM lab_tests t
            JOIN lab_test_categories c ON c.id = t.category_id
            WHERE t.is_active = 1
            ORDER BY c.name, t.test_code
        """)).mappings().all()
        params = conn.execute(text("""
            SELECT * FROM lab_test_parameters
            WHERE is_active = 1
            ORDER BY test_id, display_order, id
        """)).mappings().all()

    by_test: dict[int, list[dict]] = {}
    for param in params:
        by_test.setdefault(param["test_id"], []).append(dict(param))

    grouped: dict[str, list[dict]] = {}
    for test in tests:
        category = test["category_name"]
        grouped.setdefault(category, [])
        entry = {
            "code": test["test_code"],
            "name": test["name"],
        }
        if test["description"]:
            entry["description"] = test["description"]
        cost = test["cost"]
        entry["cost"] = int(cost) if float(cost).is_integer() else cost
        if test["sample_type"]:
            entry["sample_type"] = test["sample_type"]
        if test["method"]:
            entry["method"] = test["method"]
        if test["preparation_instructions"]:
            entry["instructions"] = test["preparation_instructions"]
        entry["parameters"] = [_param_to_seed(param) for param in by_test.get(test["id"], [])]
        grouped[category].append(entry)

    lines = ["def _get_seed_data():", "    return {"]
    for category, category_tests in grouped.items():
        lines.append(f"        {json.dumps(category)}: [")
        for test in category_tests:
            lines.append("            {")
            lines.append(
                f'                "code": {json.dumps(test["code"])}, '
                f'"name": {json.dumps(test["name"])},'
            )
            if test.get("description"):
                lines.append(f'                "description": {json.dumps(test["description"])},')
            lines.append(f'                "cost": {test["cost"]},')
            if test.get("sample_type"):
                lines.append(f'                "sample_type": {json.dumps(test["sample_type"])},')
            if test.get("method"):
                lines.append(f'                "method": {json.dumps(test["method"])},')
            if test.get("instructions"):
                lines.append(f'                "instructions": {json.dumps(test["instructions"])},')
            lines.append('                "parameters": [')
            for param in test["parameters"]:
                lines.append(f"                    {_format_param(param)},")
            lines.append("                ]")
            lines.append("            },")
        lines.append("        ],")
    lines.append("    }")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=get_db_path(), help="SQLite DB path")
    parser.add_argument("--output", help="Write generated function to this file")
    args = parser.parse_args()

    source = export_seed_data(args.db_path)
    if args.output:
        Path(args.output).write_text(source, encoding="utf-8")
        print(f"Wrote seed defaults to {args.output}")
    else:
        print(source)


if __name__ == "__main__":
    main()
