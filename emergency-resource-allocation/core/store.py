"""Persistent local plans and decisions; no external dispatch or messaging."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid

DB_PATH = Path(os.environ.get("RELIEFPLAN_DB", Path(__file__).resolve().parents[1] / "data/review.sqlite3"))


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, created TEXT, request TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, created TEXT, plan_id TEXT,
          kind TEXT, item_id TEXT, payload TEXT, UNIQUE(plan_id, kind, item_id));
        """)
        yield db
        db.commit()
    finally:
        db.close()


def save_plan(config, result):
    result.update(plan_id=uuid.uuid4().hex, created_at=timestamp())
    with connection() as db:
        db.execute("INSERT INTO plans VALUES (?, ?, ?, ?)", (result["plan_id"], result["created_at"], json.dumps(config), json.dumps(result)))
    return result


def get_plan(plan_id):
    with connection() as db:
        row = db.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
    return dict(row) if row else None


def latest_plan():
    with connection() as db:
        row = db.execute("SELECT plan_id FROM plans ORDER BY created DESC, rowid DESC LIMIT 1").fetchone()
    return get_plan(row["plan_id"]) if row else None


def list_plans():
    with connection() as db:
        rows = db.execute("SELECT * FROM plans ORDER BY created DESC, rowid DESC LIMIT 50").fetchall()
    summaries = []
    for row in rows:
        config, result = json.loads(row["request"]), json.loads(row["result"])
        summaries.append({"plan_id": row["plan_id"], "created_at": row["created"],
            "scenario_name": config.get("scenario_name", f"{config['disaster_type']} response"),
            "disaster_type": config["disaster_type"], "location_count": len(result["areas"]),
            "total_affected": result["overview"]["total_affected"]})
    return summaries


def advance_dispatch(plan_id, action_id, target):
    """Sequential, idempotent status changes protected by one DB transaction."""
    stages = ["PLANNED", "APPROVED", "DISPATCHED", "DELIVERED"]
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT result FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
        action = next((a for a in json.loads(row["result"])["actions"] if a["action_id"] == action_id), None) if row else None
        if not action:
            raise ValueError("Action does not belong to this plan.")
        kinds = {r[0] for r in db.execute("SELECT kind FROM events WHERE plan_id=? AND item_id=?", (plan_id, action_id))}
        current = next((stage for stage in reversed(stages[1:]) if f"DISPATCH_{stage}" in kinds), "PLANNED")
        if current == target:
            return current
        if target not in stages or stages.index(target) != stages.index(current) + 1:
            raise ValueError(f"Cannot move from {current} to {target}. Follow the dispatch stages in order.")
        db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, timestamp(), plan_id, f"DISPATCH_{target}", action_id,
             json.dumps({"action_id": action_id, "status": target, "area_name": action["area_name"],
                         "resource": action["resource"], "quantity": action["quantity"], "source": "Local operator confirmation"})))
    return target


def record_event(plan_id, kind, item_id, payload):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, timestamp(), plan_id, kind, item_id, json.dumps(payload)))
        row = db.execute("SELECT * FROM events WHERE plan_id=? AND kind=? AND item_id=?", (plan_id, kind, item_id)).fetchone()
    return dict(row)


def events(plan_id=None):
    with connection() as db:
        if plan_id:
            rows = db.execute("SELECT * FROM events WHERE plan_id=? ORDER BY created DESC, rowid DESC", (plan_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM events ORDER BY created DESC, rowid DESC LIMIT 200").fetchall()
    return [dict(row) for row in rows]
