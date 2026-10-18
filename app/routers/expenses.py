from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import Numeric, cast, func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import AppError
from ..models import Expense
from ..schemas import ExpenseCreate, ExpenseList, ExpenseRead, ExpenseUpdate
from ..services import csv_service

router = APIRouter(prefix="/api/expenses", tags=["expenses"])
NO_CURRENCY = "UNSPECIFIED"


def _filtered(q: str | None, currency: str | None, date_from: date | None, date_to: date | None,
              ids: list[str] | None = None):
    stmt = select(Expense)
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(Expense.supplier.ilike(like, escape="\\"),
                              Expense.invoice_number.ilike(like, escape="\\")))
    if currency:
        stmt = stmt.where(Expense.currency == currency.upper())
    if date_from:
        stmt = stmt.where(Expense.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.invoice_date <= date_to)
    if ids:
        stmt = stmt.where(Expense.id.in_(ids))
    return stmt


def _ordered(stmt, sort: str, order: str):
    col = {"date": Expense.invoice_date, "amount": cast(Expense.total, Numeric),
           "supplier": func.lower(Expense.supplier), "created": Expense.created_at}[sort]
    col = col.asc() if order == "asc" else col.desc()
    return stmt.order_by(col.nulls_last() if sort == "date" else col, Expense.created_at.desc())


def _totals(rows: list[Expense]) -> dict[str, str]:
    t: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        t[r.currency or NO_CURRENCY] += r.total
    return {k: format(v, "f") for k, v in sorted(t.items())}


@router.get("", response_model=ExpenseList)
def list_expenses(
    q: str | None = None, currency: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    sort: Literal["date", "amount", "supplier", "created"] = "created",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    base = _filtered(q, currency, date_from, date_to)
    everything = db.scalars(base).all()
    items = db.scalars(_ordered(base, sort, order).limit(page_size).offset((page - 1) * page_size)).all()
    return ExpenseList(items=items, total_count=len(everything), page=page, page_size=page_size,
                       totals_by_currency=_totals(everything))


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    rows = db.scalars(select(Expense)).all()
    counts = Counter(r.currency or NO_CURRENCY for r in rows)
    known = {k: v for k, v in counts.items() if k != NO_CURRENCY}
    return {"count": len(rows), "totals_by_currency": _totals(rows), "counts_by_currency": dict(counts),
            "most_used_currency": max(known, key=known.get) if known else None}


@router.get("/export.csv")
def export_csv(q: str | None = None, currency: str | None = None,
               date_from: date | None = None, date_to: date | None = None,
               ids: str | None = Query(None, description="Comma-separated expense ids"),
               db: Session = Depends(get_db)):
    id_list = [i for i in (ids or "").split(",") if i] or None
    rows = db.scalars(_ordered(_filtered(q, currency, date_from, date_to, id_list), "date", "desc")).all()
    body = "﻿" + csv_service.to_csv(rows)  # BOM so Excel detects UTF-8
    name = f"receiptdesk-expenses-{date.today().isoformat()}.csv"
    return Response(body.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _get(db: Session, expense_id: str) -> Expense:
    e = db.get(Expense, expense_id)
    if e is None:
        raise AppError(404, "not_found", "Expense not found.")
    return e


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(body: ExpenseCreate, db: Session = Depends(get_db)):
    e = Expense(**body.model_dump(mode="python"))
    e.source_type = body.source_type.value
    db.add(e)
    db.commit()
    return e


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(expense_id: str, db: Session = Depends(get_db)):
    return _get(db, expense_id)


@router.put("/{expense_id}", response_model=ExpenseRead)
def update_expense(expense_id: str, body: ExpenseUpdate, db: Session = Depends(get_db)):
    e = _get(db, expense_id)
    for k, v in body.model_dump(mode="python", exclude={"source_type"}).items():
        setattr(e, k, v)
    db.commit()
    return e


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: str, db: Session = Depends(get_db)):
    db.delete(_get(db, expense_id))
    db.commit()
