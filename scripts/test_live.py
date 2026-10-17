"""Run real-provider exercises through the same HTTP API as the browser.

Reports stay under ignored .data/. An optional CG_ACCESS_TOKEN authenticates cloud tests.
"""
import argparse
import json
import os
import time
import uuid
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8087")
parser.add_argument("--scenario", choices=["incorrect-readback", "words-versus-actions", "missing-evidence"], default="incorrect-readback")
parser.add_argument("--preset", choices=["missed", "partial", "complete"], default="partial")
parser.add_argument("--all", action="store_true", help="Run three representative scenario/behaviour combinations")
parser.add_argument("--timeout", type=int, default=300)
args = parser.parse_args()
headers = {"Authorization": f"Bearer {os.environ['CG_ACCESS_TOKEN']}"} if os.environ.get("CG_ACCESS_TOKEN") else {}
cases = [("incorrect-readback", "partial"), ("words-versus-actions", "missed"), ("missing-evidence", "partial")] if args.all else [(args.scenario, args.preset)]
reports = Path(__file__).resolve().parents[1] / ".data" / "test-reports"
reports.mkdir(parents=True, exist_ok=True)
failures = []
with httpx.Client(base_url=args.url, headers=headers, timeout=15) as client:
    health = client.get("/api/health").raise_for_status().json()
    if health["providerMode"] != "live":
        raise SystemExit("Refusing a fixture runtime. Configure live providers and restart the backend.")
    versions = {s["id"]: s["version"] for s in client.get("/api/scenarios").raise_for_status().json()}
    for scenario, preset in cases:
        session = client.post("/api/sessions", headers={"Idempotency-Key": str(uuid.uuid4())},
                              json={"scenarioId": scenario, "scenarioVersion": versions[scenario], "preset": preset, "playback": "typed"}).raise_for_status().json()
        session_id = session["sessionId"]
        client.post(f"/api/sessions/{session_id}/start", json={}, headers={"Idempotency-Key": str(uuid.uuid4())}).raise_for_status()
        started, last = time.monotonic(), None
        monitoring_samples = []
        while True:
            session = client.get(f"/api/sessions/{session_id}").raise_for_status().json()
            if session.get("monitor") and not session.get("simulationFinished"):
                monitoring_samples.append({"observedAfterSeconds": round(time.monotonic() - started, 2),
                                           "simulationTimeMs": session["simulationTimeMs"],
                                           "monitor": session["monitor"]})
            state = (session["status"], len(session["assessments"]), len(session["traces"]))
            if state != last:
                print(json.dumps({"scenario": scenario, "preset": preset, "status": state[0], "decisions": state[1], "actions": state[2]}), flush=True)
                last = state
            if session["status"] == "completed":
                break
            if time.monotonic() - started > args.timeout:
                failures.append(f"{scenario}: timed out")
                break
            time.sleep(1)
        path = reports / f"{session_id}.json"
        path.write_text(json.dumps(session, indent=2))
        path.chmod(0o600)
        monitoring_path = reports / f"{session_id}-monitoring.json"
        monitoring_path.write_text(json.dumps(monitoring_samples, indent=2))
        monitoring_path.chmod(0o600)
        feedback = [e["payload"]["text"] for e in session["events"] if e["type"] == "instructor_feedback"]
        errors = [t for t in session["traces"] if t["status"] == "error"]
        valid = session["status"] == "completed" and session["assessmentStatus"] == "completed" and bool(feedback) and not errors
        valid = valid and all(a["processingStatus"] == "completed" and a.get("modelVersion") != "DEVELOPMENT_FIXTURE" and not a.get("decisionOutput", {}).get("fixture") for a in session["assessments"])
        valid = valid and bool(session.get("bedrockUsage", {}).get("inputTokens"))
        # Verify an actual monitoring result appeared while dialogue was still
        # progressing, rather than accepting a final-only summary as live alerts.
        monitoring_checks = {
            "decisionBeforeEnd": any(s["monitor"]["communication"]["status"] in
                                     {"matches", "mismatch", "unclear"} for s in monitoring_samples),
            "monitorRestored": client.get(f"/api/sessions/{session_id}").raise_for_status().json().get("monitor")
            == session.get("monitor"),
        }
        if scenario in {"incorrect-readback", "missing-evidence"}:
            monitoring_checks["mismatchBeforeEnd"] = any(
                s["monitor"]["communication"]["status"] == "mismatch" for s in monitoring_samples)
        if scenario == "missing-evidence" and preset != "complete":
            monitoring_checks["positionRemainsUnknown"] = session.get("monitor", {}).get("physical", {}).get("status") == "unverified"
        if scenario == "words-versus-actions":
            monitoring_checks["movementBeforeEnd"] = any(
                s["monitor"]["physical"]["status"] in {"moving", "runway_entered"} for s in monitoring_samples)
        valid = valid and all(monitoring_checks.values())
        if not valid:
            failures.append(f"{scenario}: inspect {path.name}")
        print(json.dumps({"scenario": scenario, "passed": bool(valid), "monitoringChecks": monitoring_checks,
                          "feedback": feedback, "bedrockUsage": session.get("bedrockUsage"), "report": str(path)}), flush=True)
if failures:
    raise SystemExit("Live integration checks failed: " + "; ".join(failures))
