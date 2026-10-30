"""Validated donation and expense routes for the local educational project."""
import csv
from decimal import Decimal
import io
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from core import funds, store

router = APIRouter(prefix="/api/funds", tags=["Donations and funds"])
Money = Annotated[Decimal, Field(ge=Decimal("0.01"), le=Decimal("1000000000"), decimal_places=2, allow_inf_nan=False)]
Category = Literal["GENERAL", "FOOD", "WATER", "MEDICAL", "TRANSPORT", "SHELTER", "OTHER"]


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID = Field(default_factory=uuid4)
    kind: Literal["DONATION", "EXPENSE"] = "DONATION"
    amount: Money
    party: str = Field(default="", max_length=100)
    category: Category = "GENERAL"
    payment_method: Literal["CASH", "UPI", "BANK_TRANSFER", "OTHER"] = "OTHER"
    reference: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=500)
    donation_status: Literal["RECEIVED", "PLEDGED"] | None = "RECEIVED"
    plan_id: str | None = Field(default=None, max_length=64)
    area_id: str | None = Field(default=None, max_length=100)

    @field_validator("party", "reference", "note")
    @classmethod
    def trim_text(cls, value):
        return value.strip()

    @model_validator(mode="after")
    def coherent_entry(self):
        self.party = self.party or ("Anonymous donor" if self.kind == "DONATION" else "Relief operations")
        if self.kind == "EXPENSE":
            self.donation_status = None
            if len(self.note) < 3:
                raise ValueError("Describe what the expense was used for.")
        elif self.donation_status is None:
            raise ValueError("Choose received or pledged for a donation.")
        if self.area_id and not self.plan_id:
            raise ValueError("Select a saved scenario before choosing an affected area.")
        return self


class GoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), decimal_places=2, allow_inf_nan=False)]


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Enter a short reason for voiding this record.")
        return value.strip()


@router.get("")
def get_fund():
    return funds.snapshot()


@router.post("/entries")
def record_entry(req: EntryRequest):
    scenario_name, area_name = None, None
    if req.plan_id:
        plan = store.get_plan(req.plan_id)
        if not plan:
            raise HTTPException(404, "Saved scenario not found. Choose another scenario or leave the link blank.")
        config, result = json.loads(plan["request"]), json.loads(plan["result"])
        scenario_name = config.get("scenario_name", config["disaster_type"] + " response")
        if req.area_id:
            area = next((area for area in result["areas"] if area["area_id"] == req.area_id), None)
            if not area:
                raise HTTPException(422, "Affected area does not belong to the selected scenario.")
            area_name = area["area_name"]
    record = req.model_dump(exclude={"request_id", "amount"})
    record.update(amount_paise=int(req.amount * 100), scenario_name=scenario_name, area_name=area_name)
    try:
        entry = funds.create_entry(req.request_id.hex, record)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"entry": entry, "fund": funds.snapshot()}


@router.post("/entries/{entry_id}/receive")
def receive_pledge(entry_id: str):
    try:
        entry = funds.receive_pledge(entry_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"entry": entry, "fund": funds.snapshot()}


@router.post("/entries/{entry_id}/void")
def void_entry(entry_id: str, req: VoidRequest):
    try:
        entry = funds.void_entry(entry_id, req.reason)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"entry": entry, "fund": funds.snapshot()}


@router.post("/goal")
def update_goal(req: GoalRequest):
    funds.set_goal(int(req.amount * 100))
    return funds.snapshot()


@router.get("/export.csv")
def export_ledger():
    fields = ["entry_id", "created", "kind", "party", "amount_inr", "currency", "category", "payment_method", "reference", "status", "scenario_name", "area_name", "note", "received_at", "voided_at", "void_reason"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for entry in funds.snapshot()["entries"]:
        row = {key: entry.get(key) or "" for key in fields}
        row.update(amount_inr=f"{Decimal(entry['amount_paise']) / 100:.2f}", currency="INR",
            status="VOIDED" if entry["voided_at"] else entry["donation_status"] or "SPENT")
        # Treat user text as spreadsheet text, including names starting with '='.
        row = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for key, value in row.items()}
        writer.writerow(row)
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="reliefplan-fund-ledger.csv"'})

