"""One payload for the billing dashboard.

Figures come from the same helpers as Sales register, Daily collection, and
Doctor revenue, so the tiles match those reports for the same dates.
"""
from datetime import date

from sqlalchemy.orm import Session


def _slim_invoice(row: dict) -> dict:
    return {
        "date": row.get("date") or "",
        "number": row.get("number") or "",
        "party": row.get("party") or "",
        "module": row.get("module") or "",
        "module_label": row.get("module_label") or "",
        "billed": row.get("billed") or 0,
        "collected": row.get("collected") or 0,
        "outstanding": row.get("outstanding") or 0,
        "status": row.get("status") or "",
    }


def billing_dashboard(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    from app.services.collection_by_method import collection_by_method
    from app.services.front_desk_expenses import attach_front_desk_expenses
    from app.services.gst_report_service import sales_summary
    from app.services.revenue_reports import doctor_revenue

    sales = sales_summary(db, hospital_id, d_from, d_to, group_by="day")
    collection = attach_front_desk_expenses(
        db, hospital_id, collection_by_method(db, hospital_id, d_from, d_to),
    )
    doctors = doctor_revenue(db, hospital_id, d_from, d_to)

    invoices = sales.get("invoices") or []
    recent = sorted(
        invoices,
        key=lambda row: (row.get("date") or "", row.get("number") or ""),
        reverse=True,
    )[:8]
    outstanding = sorted(
        (row for row in invoices if float(row.get("outstanding") or 0) > 0.005),
        key=lambda row: float(row.get("outstanding") or 0),
        reverse=True,
    )[:8]

    modules = [
        {
            "module": row["module"],
            "module_label": row["module_label"],
            "billed": row["billed"],
            "collected": row["collected"],
            "outstanding": row["outstanding"],
            "count": row["count"],
        }
        for row in (sales.get("by_module") or [])
    ]
    trend = [
        {
            "date": row.get("bucket") or "",
            "billed": row.get("billed") or 0,
            "collected": row.get("collected") or 0,
            "outstanding": row.get("outstanding") or 0,
            "count": row.get("count") or 0,
        }
        for row in (sales.get("rows") or [])
    ]

    totals = sales.get("totals") or {}
    receipts = collection.get("totals") or {}
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "billed": totals.get("billed", 0),
            "collected": totals.get("collected", 0),
            "outstanding": totals.get("outstanding", 0),
            "discount": totals.get("discount", 0),
            "tax": totals.get("tax", 0),
            "count": totals.get("count", 0),
            "net_receipts": receipts.get("net_collected", 0),
            "refunds": receipts.get("refunds", 0),
            "expenses": receipts.get("expenses", 0),
            "net_after_expenses": receipts.get("net_after_expenses", receipts.get("net_collected", 0)),
        },
        "by_module": modules,
        "by_method": collection.get("by_method") or {},
        "methods": collection.get("methods") or [],
        "trend": trend,
        "top_doctors": [
            {
                "doctor_id": row.get("doctor_id"),
                "doctor_name": row.get("doctor_name") or "",
                "total_revenue": row.get("total_revenue") or 0,
            }
            for row in (doctors.get("rows") or [])[:5]
        ],
        "recent": [_slim_invoice(row) for row in recent],
        "outstanding_invoices": [_slim_invoice(row) for row in outstanding],
    }
