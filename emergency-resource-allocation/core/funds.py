"""Local relief-fund bookkeeping. Amounts are integer paise; no payments occur."""
from contextlib import contextmanager
import hashlib
import json
import uuid
from core import store


@contextmanager
def connection():
    with store.connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS fund_settings (setting TEXT PRIMARY KEY, value INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS fund_entries (
          entry_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
          created TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('DONATION','EXPENSE')),
          amount_paise INTEGER NOT NULL CHECK(amount_paise > 0), party TEXT NOT NULL,
          category TEXT NOT NULL, payment_method TEXT NOT NULL, reference TEXT NOT NULL,
          note TEXT NOT NULL, donation_status TEXT, plan_id TEXT, scenario_name TEXT,
          area_id TEXT, area_name TEXT, received_at TEXT, voided_at TEXT, void_reason TEXT
        );
        """)
        yield db


def _event(db, entry, kind, message):
    db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, store.timestamp(), entry.get("plan_id") or "relief-fund", kind,
         entry["entry_id"], json.dumps({"entry_id": entry["entry_id"], "message": message,
             "amount_paise": entry["amount_paise"], "currency": "INR"})))


def _totals(db):
    row = db.execute("""SELECT
      COALESCE(SUM(CASE WHEN kind='DONATION' AND donation_status='RECEIVED' THEN amount_paise ELSE 0 END),0) received,
      COALESCE(SUM(CASE WHEN kind='DONATION' AND donation_status='PLEDGED' THEN amount_paise ELSE 0 END),0) pledged,
      COALESCE(SUM(CASE WHEN kind='EXPENSE' THEN amount_paise ELSE 0 END),0) spent,
      SUM(CASE WHEN kind='DONATION' THEN 1 ELSE 0 END) donation_count,
      SUM(CASE WHEN kind='EXPENSE' THEN 1 ELSE 0 END) expense_count
      FROM fund_entries WHERE voided_at IS NULL""").fetchone()
    return {"received_paise": row["received"], "pledged_paise": row["pledged"], "spent_paise": row["spent"],
        "available_paise": row["received"] - row["spent"], "donation_count": row["donation_count"] or 0,
        "expense_count": row["expense_count"] or 0}


def _get(db, entry_id):
    row = db.execute("SELECT * FROM fund_entries WHERE entry_id=?", (entry_id,)).fetchone()
    if not row:
        raise LookupError("Fund record not found.")
    return dict(row)


def public_entry(entry):
    return {key: value for key, value in entry.items() if key not in {"request_id", "request_hash"}}


def snapshot():
    with connection() as db:
        # One consistent read of the balance, goal and ledger during concurrent writes.
        db.execute("BEGIN")
        totals = _totals(db)
        goal = db.execute("SELECT value FROM fund_settings WHERE setting='goal_paise'").fetchone()
        entries = [public_entry(dict(row)) for row in db.execute("SELECT * FROM fund_entries ORDER BY created DESC, rowid DESC")]
        categories = [dict(row) for row in db.execute("SELECT category, SUM(amount_paise) amount_paise FROM fund_entries WHERE kind='EXPENSE' AND voided_at IS NULL GROUP BY category ORDER BY amount_paise DESC")]
    goal_paise = goal["value"] if goal else 0
    return {"currency": "INR", "goal_paise": goal_paise, "totals": totals, "entries": entries,
        "category_spend": categories,
        "goal_progress_pct": min(100, round(100 * totals["received_paise"] / goal_paise, 1)) if goal_paise else 0,
        "recording_mode": "MANUAL_LOCAL_LEDGER"}


def create_entry(request_id, record):
    if type(record["amount_paise"]) is not int or record["amount_paise"] <= 0:
        raise ValueError("Amount must be a positive whole number of paise.")
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM fund_entries WHERE request_id=?", (request_id,)).fetchone()
        if existing:
            if existing["request_hash"] != fingerprint:
                raise ValueError("This form was already saved with different details. Refresh the ledger and start a new record.")
            return public_entry(dict(existing))
        if record["kind"] == "EXPENSE" and record["amount_paise"] > _totals(db)["available_paise"]:
            raise ValueError("Expense exceeds available received funds. Pledges cannot be spent.")
        created = store.timestamp()
        entry = dict(record, entry_id=uuid.uuid4().hex, request_id=request_id, request_hash=fingerprint,
            created=created, received_at=created if record["kind"] == "DONATION" and record["donation_status"] == "RECEIVED" else None,
            voided_at=None, void_reason=None)
        columns = list(entry)
        db.execute("INSERT INTO fund_entries (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", tuple(entry.values()))
        label = "Expense recorded" if entry["kind"] == "EXPENSE" else "Donation " + entry["donation_status"].lower()
        _event(db, entry, "FUND_ENTRY_RECORDED", f"{label}: INR {entry['amount_paise'] / 100:,.2f} — {entry['party']}")
    return public_entry(entry)


def receive_pledge(entry_id):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        entry = _get(db, entry_id)
        if entry["voided_at"] or entry["kind"] != "DONATION":
            raise ValueError("Only an active donation pledge can be marked received.")
        if entry["donation_status"] == "RECEIVED":
            return public_entry(entry)
        received_at = store.timestamp()
        db.execute("UPDATE fund_entries SET donation_status='RECEIVED', received_at=? WHERE entry_id=?", (received_at, entry_id))
        _event(db, entry, "FUND_PLEDGE_RECEIVED", f"Pledge manually marked received: INR {entry['amount_paise'] / 100:,.2f} — {entry['party']}")
        entry.update(donation_status="RECEIVED", received_at=received_at)
    return public_entry(entry)


def void_entry(entry_id, reason):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        entry = _get(db, entry_id)
        if entry["voided_at"]:
            return public_entry(entry)
        if entry["kind"] == "DONATION" and entry["donation_status"] == "RECEIVED" and entry["amount_paise"] > _totals(db)["available_paise"]:
            raise ValueError("These funds have already been used. Correct the related expense records before voiding this donation.")
        entry.update(voided_at=store.timestamp(), void_reason=reason)
        db.execute("UPDATE fund_entries SET voided_at=?, void_reason=? WHERE entry_id=?", (entry["voided_at"], reason, entry_id))
        _event(db, entry, "FUND_ENTRY_VOIDED", f"{entry['kind'].title()} record voided: INR {entry['amount_paise'] / 100:,.2f}. Reason: {reason}")
    return public_entry(entry)


def set_goal(amount_paise):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO fund_settings VALUES ('goal_paise',?) ON CONFLICT(setting) DO UPDATE SET value=excluded.value", (amount_paise,))
        entry = {"entry_id": uuid.uuid4().hex, "amount_paise": amount_paise, "plan_id": None}
        _event(db, entry, "FUND_GOAL_UPDATED", f"Fundraising target set to INR {amount_paise / 100:,.2f}.")

