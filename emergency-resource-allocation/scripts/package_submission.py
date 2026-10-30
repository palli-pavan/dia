"""Build the project-only submission archive, including the prebuilt dashboard."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import uuid
import zipfile


def main():
    project = Path(__file__).resolve().parents[1]
    root = project.parent
    evidence = root / "review-ready/project-updates"
    evidence.mkdir(parents=True, exist_ok=True)
    excluded = {"node_modules", "__pycache__", ".pytest_cache", ".test-runs", ".venv", "venv", ".git"}
    entries = {}
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if not path.is_file() or any(part in excluded for part in relative.parts):
            continue
        if ".sqlite3" in path.name or path.name.startswith(".env") or path.suffix in {".pyc", ".log"}:
            continue
        entries[f"emergency-resource-allocation/{relative.as_posix()}"] = path.read_bytes()
    for name in ["START_PROJECT.cmd", "SETUP_PROJECT.cmd", "README.md", "PROJECT_DEMO.md"]:
        entries[name] = (root / name).read_bytes()
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.suffix in {".jpg", ".json"} and path.name != "package-check.json":
            if path.suffix == ".jpg" and not path.name.startswith("ui-"):
                continue  # Keep the current dashboard previews in this edition.
            entries[f"verification/{path.relative_to(evidence).as_posix()}"] = path.read_bytes()
    entries["README_FIRST.txt"] = (
        "ReliefPlan AI 3.2 — project submission update, 27 October 2026\n\n"
        "Extract the complete ZIP. Run START_PROJECT.cmd and keep its console open.\n"
        "Visit http://127.0.0.1:8008. On Describe click Load custom-location demo,\n"
        "then Run AI analysis. PROJECT_DEMO.md gives the demonstration sequence.\n\n"
        "Donations & funds tracks received donations, pledges, expenses and a\n"
        "fundraising target in INR. The local ledger starts empty. It does not\n"
        "collect payments or transfer money.\n\n"
        "Python 3.13 and the requirements-tested.txt dependencies are required.\n"
        "The frontend is already built; Node.js is needed only for rebuilding.\n"
        "A fresh local SQLite database is created at first run. Browser drafts\n"
        "are stored locally. Basemap tiles require internet. All model training\n"
        "data and demonstration observations are synthetic. Dispatch statuses\n"
        "are local confirmations. This ZIP contains the working project only.\n"
    ).encode("utf-8")
    manifest = "\n".join(f"{hashlib.sha256(data).hexdigest()}  {name}" for name, data in sorted(entries.items())) + "\n"
    entries["SHA256SUMS.txt"] = manifest.encode()
    archive = root / "review-ready/ReliefPlan_AI_Project_Updated.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, data in sorted(entries.items()):
            zipped.writestr(name, data)
    extracted = root / ".review-verification" / uuid.uuid4().hex
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        for line in manifest.splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(zipped.read(name)).hexdigest() == digest
        assert "emergency-resource-allocation/frontend/dist/index.html" in zipped.namelist()
        assert all(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts for name in zipped.namelist())
        extracted.mkdir(parents=True)
        zipped.extractall(extracted)
    result = {"archive": str(archive), "files": len(entries), "bytes": archive.stat().st_size,
        "checksums": "passed", "extracted_to": str(extracted), "prebuilt_frontend": True}
    (evidence / "package-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
