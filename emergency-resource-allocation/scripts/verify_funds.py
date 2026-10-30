"""Check a running local fund ledger without adding money records."""
import argparse
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8008")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    def call(path, body=None, status=200, raw=False):
        req = urllib.request.Request(args.url + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                code, value = response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            code, value = error.code, error.read().decode()
        assert code == status, (path, code, value)
        return value if raw else json.loads(value)
    check("Fund-capable server version", call("/api/health")["version"] == "3.2.0")
    fund = call("/api/funds")
    active = [entry for entry in fund["entries"] if not entry["voided_at"]]
    received = sum(entry["amount_paise"] for entry in active if entry["kind"] == "DONATION" and entry["donation_status"] == "RECEIVED")
    pledged = sum(entry["amount_paise"] for entry in active if entry["kind"] == "DONATION" and entry["donation_status"] == "PLEDGED")
    spent = sum(entry["amount_paise"] for entry in active if entry["kind"] == "EXPENSE")
    check("INR manual ledger", fund["currency"] == "INR" and fund["recording_mode"] == "MANUAL_LOCAL_LEDGER")
    check("All amounts use integer paise", all(type(entry["amount_paise"]) is int for entry in fund["entries"]))
    check("Received totals match active receipts", received == fund["totals"]["received_paise"])
    check("Pledges tracked separately", pledged == fund["totals"]["pledged_paise"])
    check("Expense totals exclude voided rows", spent == fund["totals"]["spent_paise"])
    check("Available balance excludes pledges", received - spent == fund["totals"]["available_paise"] >= 0)
    check("Category totals match actual spending", sum(row["amount_paise"] for row in fund["category_spend"]) == spent)
    expected_progress = min(100, round(100 * received / fund["goal_paise"], 1)) if fund["goal_paise"] else 0
    check("Fundraising target uses received funds", fund["goal_progress_pct"] == expected_progress)
    exported = list(csv.DictReader(io.StringIO(call("/api/funds/export.csv", raw=True))))
    check("CSV includes complete history", len(exported) == len(fund["entries"]))
    amounts = {entry["entry_id"]: entry["amount_paise"] for entry in fund["entries"]}
    check("CSV preserves two-decimal money values", all(Decimal(row["amount_inr"]) * 100 == amounts[row["entry_id"]] for row in exported))
    for entry in fund["entries"]:
        if entry["plan_id"] and entry["area_id"]:
            plan = call("/api/plans/" + entry["plan_id"])
            check("Linked area belongs to saved scenario", any(area["area_id"] == entry["area_id"] and area["area_name"] == entry["area_name"] for area in plan["areas"]))
            break
    call("/api/funds/entries", {"amount": "-1"}, status=422)
    check("Invalid amount rejected without a ledger write", len(call("/api/funds")["entries"]) == len(fund["entries"]))
    call("/api/funds/entries/verification-not-an-entry/receive", {}, status=404)
    check("Unknown receipt confirmation rejected", True)
    result = {"server": args.url, "passed": len(checks), "checks": checks, "snapshot": fund,
        "verification_mode": "Read checks and invalid requests only; no money entries created"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
