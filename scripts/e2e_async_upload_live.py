#!/usr/bin/env python3
"""Live HTTP e2e for outside-scholarships async upload + streaming progress.

Loads real backend/.env Azure credentials, overrides auth, starts uvicorn, POSTs a
real scanned PDF, polls job progress until preview, then prints a summary.

Usage (from repo root or anywhere):
  /path/to/myenv/bin/python scripts/e2e_async_upload_live.py [pdf_path]
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DEFAULT_PDF = Path(
    "/Users/jasoncharwin/Personal Code Projects/charlotte/charlotte/"
    "10132026 Scholarship Check Images with Supporting Documentation 1382444.pdf"
)
HOST = "127.0.0.1"
PORT = 8765
BASE = f"http://{HOST}:{PORT}"
UPLOAD_URL = f"{BASE}/api/banking/outside-scholarships"
JOB_URL = f"{BASE}/api/banking/outside-scholarships/jobs"


def main() -> int:
    pdf_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    load_dotenv(BACKEND_DIR / ".env", override=True)
    sys.path.insert(0, str(BACKEND_DIR))

    import main as app_main
    from api.dependencies import get_graph_user_directory
    from outside_scholarships_fakes import FakeGraph
    from services.azure_services import GraphUserDirectory
    from services.banking.outside_scholarships.jobs import reset_jobs
    from utils.auth import get_bearer_token, get_current_user

    app = app_main.app
    reset_jobs()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "e2e-live-user",
        "email": "e2e@unc.edu",
        "name": "E2E Live",
        "department": "admin",
    }
    app.dependency_overrides[get_bearer_token] = lambda: "e2e-live-graph-token"
    # Keep Graph offline; vision extraction still hits real Azure OpenAI.
    app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(
        transport=FakeGraph().transport
    )

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline and not server.started:
        time.sleep(0.1)
    if not server.started:
        print("uvicorn failed to start", file=sys.stderr)
        return 1

    print(f"PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("POST upload…")
    started = time.perf_counter()
    progress_events = []

    try:
        with httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            with pdf_path.open("rb") as handle:
                response = client.post(
                    UPLOAD_URL,
                    files={"files": (pdf_path.name, handle, "application/pdf")},
                    data={"aid_year": "2026", "aid_term": "F"},
                    headers={"Authorization": "Bearer e2e-live"},
                )
            post_seconds = round(time.perf_counter() - started, 2)
            print(f"POST status={response.status_code} elapsed={post_seconds}s body={response.text[:300]}")
            if response.status_code != 202:
                return 1

            body = response.json()
            job_id = body["job_id"]
            assert body.get("status") == "processing"
            # Critical for the timeout fix: upload response must return quickly.
            if post_seconds > 60:
                print(f"WARN: POST took {post_seconds}s; expected fast 202 after bytes are read")

            print(f"Polling job {job_id}…")
            preview = None
            last_fingerprint = None
            poll_deadline = time.time() + 45 * 60
            while time.time() < poll_deadline:
                poll = client.get(
                    f"{JOB_URL}/{job_id}",
                    headers={"Authorization": "Bearer e2e-live"},
                )
                if poll.status_code != 200:
                    print(f"GET failed status={poll.status_code} body={poll.text[:500]}")
                    return 1
                data = poll.json()
                if isinstance(data.get("checks"), list):
                    preview = data
                    break
                fingerprint = (
                    data.get("stage"),
                    data.get("message"),
                    data.get("pages_classified"),
                    data.get("checks_done"),
                    data.get("checks_total"),
                )
                if fingerprint != last_fingerprint:
                    last_fingerprint = fingerprint
                    progress_events.append(data)
                    print(
                        f"  progress stage={data.get('stage')} "
                        f"pages={data.get('pages_classified')}/{data.get('pages_total')} "
                        f"checks={data.get('checks_done')}/{data.get('checks_total')} "
                        f"msg={data.get('message')!r}"
                    )
                time.sleep(1.5)
            else:
                print("Timed out waiting for preview", file=sys.stderr)
                return 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()
        reset_jobs()

    total_seconds = round(time.perf_counter() - started, 2)
    checks = preview.get("checks") or []
    print("---")
    print(f"DONE total_seconds={total_seconds} checks={len(checks)} progress_events={len(progress_events)}")
    if progress_events:
        stages = [event.get("stage") for event in progress_events]
        print(f"stages_seen={stages}")
    sample = [
        {
            "check_index": check.get("check_index"),
            "amount": check.get("amount"),
            "provider": check.get("provider"),
            "pid_count": len(check.get("pids") or []),
        }
        for check in checks[:5]
    ]
    print("first_checks=" + json.dumps(sample, indent=2))

    ok = True
    if post_seconds >= 240:
        print("FAIL: POST held open past Azure App Service ~240s window")
        ok = False
    if not progress_events:
        print("FAIL: no streaming progress updates observed while polling")
        ok = False
    if not checks:
        print("FAIL: preview had zero checks")
        ok = False
    if ok:
        print("PASS: async upload + streaming progress + preview")
    return 0 if ok else 1


if __name__ == "__main__":
    # outside_scholarships_fakes lives under tests/
    sys.path.insert(0, str(BACKEND_DIR / "tests"))
    raise SystemExit(main())
