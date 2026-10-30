"""One-process local review launcher: API and built React UI on the same origin."""
import argparse
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Start the complete ReliefPlan project")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    required = ["fastapi", "uvicorn", "numpy", "pandas", "scipy", "sklearn", "xgboost", "shap", "joblib"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        sys.exit("Missing dependencies: " + ", ".join(missing) + "\nRun: python -m pip install -r requirements.txt")
    if not (ROOT / "frontend/dist/index.html").exists():
        sys.exit("Build the dashboard first: cd frontend && npm ci && npm run build")
    for name in ["best_model.pkl", "label_encoder.pkl", "shap_explainer.pkl", "metrics.json"]:
        if not (ROOT / "models" / name).exists():
            sys.exit(f"Missing model artifact {name}. Run python core/model.py from the project folder.")
    with socket.socket() as check:
        try:
            check.bind(("127.0.0.1", args.port))
        except OSError:
            try:
                running_url = f"http://127.0.0.1:{args.port}"
                with urllib.request.urlopen(running_url + "/api/health", timeout=2) as response:
                    health = json.load(response)
                if health.get("system") == "ReliefPlan AI" and health.get("version") == "3.2.0" and health.get("model_ready"):
                    print(f"ReliefPlan AI is already running: {running_url}")
                    if not args.no_browser:
                        webbrowser.open(running_url)
                    return
            except (OSError, ValueError):
                pass
            sys.exit(f"Port {args.port} is already in use. Open http://127.0.0.1:{args.port} or use --port 8009.")
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        def open_when_ready():
            for _ in range(120):
                try:
                    with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except (OSError, TimeoutError):
                    time.sleep(0.5)
        threading.Thread(target=open_when_ready, daemon=True).start()
    print(f"\nReliefPlan AI: {url}\nAPI documentation: {url}/docs\nPress Ctrl+C to stop.\n")
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=args.port, app_dir=str(ROOT))


if __name__ == "__main__":
    main()
