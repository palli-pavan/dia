"""Fund balances, pledge handling and immutable, traceable local records."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from core import funds, store
import funds_api as api
import server


@pytest.fixture(autouse=True)
def isolated_fund(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "fund-test.sqlite3")


def record(**changes):
    return api.record_entry(api.EntryRequest(**{"amount": "100.00", **changes}))


def expense(amount="25.00", **changes):
    return record(kind="EXPENSE", amount=amount, note="Purchased drinking water", category="WATER", **changes)


def test_empty_ledger_has_zero_totals_and_csv_headers():
    snapshot = funds.snapshot()
    assert snapshot["entries"] == [] and snapshot["goal_paise"] == 0
    assert all(value == 0 for value in snapshot["totals"].values())
    assert len(api.export_ledger().body.decode().splitlines()) == 1


def test_received_donations_use_exact_paise_and_anonymous_default():
    record(amount="10.01")
    result = record(amount="0.02")
    assert result["fund"]["totals"]["received_paise"] == 1003
    assert result["fund"]["totals"]["available_paise"] == 1003
    assert result["entry"]["party"] == "Anonymous donor"
    assert len(funds.snapshot()["entries"]) == 2


def test_pledges_are_not_spendable_until_received_once():
    pledged = record(donation_status="PLEDGED")
    assert pledged["fund"]["totals"]["pledged_paise"] == 10000
    assert pledged["fund"]["totals"]["available_paise"] == 0
    with pytest.raises(HTTPException) as error:
        expense()
    assert error.value.status_code == 409
    api.receive_pledge(pledged["entry"]["entry_id"])
    result = api.receive_pledge(pledged["entry"]["entry_id"])
    assert result["fund"]["totals"]["available_paise"] == 10000
    assert result["fund"]["totals"]["pledged_paise"] == 0
    assert len([event for event in store.events() if event["kind"] == "FUND_PLEDGE_RECEIVED"]) == 1


def test_expense_reduces_balance_and_groups_actual_spend():
    record()
    result = expense("35.25")
    assert result["fund"]["totals"]["available_paise"] == 6475
    assert result["fund"]["totals"]["spent_paise"] == 3525
    assert result["fund"]["category_spend"] == [{"category": "WATER", "amount_paise": 3525}]
    with pytest.raises(HTTPException):
        expense("65.00")
    assert len(funds.snapshot()["entries"]) == 2


def test_retries_are_idempotent_and_changed_payload_is_rejected():
    request_id = uuid4()
    first = record(request_id=request_id, amount="10")
    second = record(request_id=request_id, amount="10.00")
    assert first["entry"]["entry_id"] == second["entry"]["entry_id"]
    assert second["fund"]["totals"]["donation_count"] == 1
    with pytest.raises(HTTPException) as error:
        record(request_id=request_id, amount="11")
    assert error.value.status_code == 409
    assert funds.snapshot()["totals"]["received_paise"] == 1000


def test_voiding_preserves_history_and_does_not_allow_negative_balance():
    donation = record()["entry"]
    spent = expense()["entry"]
    with pytest.raises(HTTPException):
        api.void_entry(donation["entry_id"], api.VoidRequest(reason="Entry correction"))
    api.void_entry(spent["entry_id"], api.VoidRequest(reason="Expense entered twice"))
    assert funds.snapshot()["totals"]["available_paise"] == 10000
    api.void_entry(donation["entry_id"], api.VoidRequest(reason="Demo entry correction"))
    result = api.void_entry(donation["entry_id"], api.VoidRequest(reason="Retry same correction"))
    assert result["fund"]["totals"]["available_paise"] == 0
    assert len(result["fund"]["entries"]) == 2
    assert all(entry["voided_at"] and entry["void_reason"] for entry in result["fund"]["entries"])
    assert len([event for event in store.events() if event["kind"] == "FUND_ENTRY_VOIDED"]) == 2


def test_received_and_voided_pledge_rules():
    pledge = record(donation_status="PLEDGED")["entry"]
    api.void_entry(pledge["entry_id"], api.VoidRequest(reason="Pledge withdrawn"))
    assert funds.snapshot()["totals"]["pledged_paise"] == 0
    with pytest.raises(HTTPException):
        api.receive_pledge(pledge["entry_id"])
    record()
    spent = expense()["entry"]
    with pytest.raises(HTTPException):
        api.receive_pledge(spent["entry_id"])


def test_goal_counts_received_donations_and_caps_progress():
    api.update_goal(api.GoalRequest(amount="200"))
    record(donation_status="PLEDGED")
    assert funds.snapshot()["goal_progress_pct"] == 0
    record()
    assert funds.snapshot()["goal_progress_pct"] == 50
    record(amount="200")
    assert funds.snapshot()["goal_progress_pct"] == 100
    api.update_goal(api.GoalRequest(amount="0"))
    assert funds.snapshot()["goal_progress_pct"] == 0


def test_expense_link_resolves_real_scenario_and_area():
    plan = server.analyze_disaster(server.AnalyzeRequest(scenario_name="Linked relief plan", area_populations={"Area A": 1000}))
    record()
    result = expense(plan_id=plan["plan_id"], area_id="A")
    assert result["entry"]["scenario_name"] == "Linked relief plan"
    assert result["entry"]["area_name"] == "Area A"
    with pytest.raises(HTTPException) as error:
        expense(plan_id=plan["plan_id"], area_id="not-in-plan")
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        record(plan_id="missing")
    assert error.value.status_code == 404


def test_concurrent_expenses_cannot_overdraw_shared_fund():
    record()
    def attempt(_):
        try:
            expense("75")
            return "saved"
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(attempt, range(2)))
    assert outcomes.count("saved") == 1 and outcomes.count(409) == 1
    assert funds.snapshot()["totals"]["available_paise"] == 2500


def test_csv_exports_exact_amounts_statuses_and_safe_user_text():
    record(amount="12.34", party="=Demo donor", reference="@reference")
    rows = list(csv.DictReader(io.StringIO(api.export_ledger().body.decode())))
    assert rows[0]["amount_inr"] == "12.34" and rows[0]["currency"] == "INR"
    assert rows[0]["status"] == "RECEIVED"
    assert rows[0]["party"] == "'=Demo donor"
    assert rows[0]["reference"] == "'@reference"


@pytest.mark.parametrize("changes", [
    {"amount": "0"}, {"amount": "-1"}, {"amount": "0.001"}, {"amount": "NaN"}, {"amount": "Infinity"},
    {"amount": "1000000001"}, {"category": "UNKNOWN"}, {"donation_status": None},
    {"party": "x" * 101}, {"area_id": "A"}, {"kind": "EXPENSE", "note": " "},
])
def test_invalid_fund_entries_are_rejected(changes):
    with pytest.raises(ValidationError):
        api.EntryRequest(**{"amount": "1", **changes})


def test_http_fund_routes_and_persistence():
    with TestClient(server.app) as client:
        assert client.get("/api/funds").json()["totals"]["available_paise"] == 0
        result = client.post("/api/funds/entries", json={"amount": "123.45", "donation_status": "PLEDGED"})
        assert result.status_code == 200
        entry_id = result.json()["entry"]["entry_id"]
        assert client.post(f"/api/funds/entries/{entry_id}/receive", json={}).status_code == 200
        assert client.get("/api/funds").json()["totals"]["available_paise"] == 12345
        assert client.post("/api/funds/goal", json={"amount": "500"}).json()["goal_paise"] == 50000
        assert client.post("/api/funds/entries", json={"amount": 0}).status_code == 422
        assert client.post("/api/funds/entries/unknown/receive", json={}).status_code == 404
        assert client.get("/api/funds/export.csv").status_code == 200
