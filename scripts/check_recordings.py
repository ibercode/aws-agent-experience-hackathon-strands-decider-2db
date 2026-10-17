"""Summarize private deployed recordings without making network or model calls.

Runtime errors, model outcomes and guard withholding remain distinct. Output is
aggregate test evidence; raw session records must remain under ignored .data/.
"""
import argparse
import copy
import json
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from clearance_gap.monitor import monitor_view


def project(frame):
    rows = frame["records"]
    meta = next(row for row in rows if row.get("SK") == "META")
    snapshot = next(row for row in rows if row.get("SK") == f"SNAPSHOT#{int(meta['latestSnapshotVersion']):010d}")
    observation = copy.deepcopy(snapshot["worldState"]["lastObservation"])
    observation["ageMs"] = meta["simulationTimeMs"] - observation["observedAtMs"]
    observation["status"] = "current" if observation["ageMs"] <= 5000 else "stale"
    session = SimpleNamespace(meta=meta,
        events=sorted([r for r in rows if r.get("SK", "").startswith("EVENT#")], key=lambda r: r["sequence"]),
        assessments=[r for r in rows if r.get("SK", "").startswith("ASSESSMENT#")],
        traces=sorted([r for r in rows if r.get("SK", "").startswith("TRACE#")], key=lambda r: r["startedAt"]))
    return session, monitor_view(session, observation)


def summarize(path):
    frames = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not frames:
        return {"case": path.stem, "recordingComplete": False}
    projected = [project(frame) for frame in frames]
    final, monitor = projected[-1]
    meta, assessments, traces = final.meta, final.assessments, final.traces
    early = [(s, m) for s, m in projected if not s.meta.get("simulationFinished")]
    decider_rtts = [a["roundTripMs"] for a in assessments if a.get("roundTripMs") is not None]
    trace_rtts = [t["roundTripMs"] for t in traces if t.get("roundTripMs") is not None and t["actor"] == "decider"]
    errors = [{"actor": t["actor"], "step": t["title"], "phase": t.get("inputs", {}).get("phase")}
              for t in traces if t.get("status") == "error"]
    status_changes = []
    for s, m in projected:
        pair = (m["communication"]["status"], m["physical"]["status"])
        if not status_changes or tuple(status_changes[-1][key] for key in ["communication", "physical"]) != pair:
            status_changes.append({"simulationTimeMs": s.meta["simulationTimeMs"], "communication": pair[0], "physical": pair[1]})
    known_events = {e["eventId"] for e in final.events}
    checks = {
        "sessionCompleted": meta["status"] == "completed",
        "realProviders": meta["providerMode"] == "live" and all(a.get("providerMode") == "live" and
            not a.get("decisionOutput", {}).get("fixture") and
            (a.get("processingStatus") != "completed" or a.get("modelVersion", "").startswith("StrandsAgents/"))
            for a in assessments),
        "bedrockUsageRecorded": (meta.get("bedrockUsage") or {}).get("inputTokens", 0) > 0,
        "noUnfinishedActivity": all(t["status"] in {"completed", "error"} for t in traces),
        "noUnfinishedDecisions": all(a["processingStatus"] in {"completed", "error"} for a in assessments),
        "decisionVisibleBeforeScriptEnded": any(m["communication"]["status"] in {"matches", "mismatch", "unclear"} for _, m in early),
        "pendingActivityCaptured": any(any(t["status"] == "running" for t in s.traces) for s, _ in projected),
        "activityCountsProgressed": len({len(s.traces) for s, _ in projected}) > 1,
        "decisionCountsProgressed": len({len(s.assessments) for s, _ in projected}) > 1,
        "evidenceReferencesResolve": all(set(a.get("evidenceRefs", {}).get("eventIds", [])).issubset(known_events) for a in assessments),
    }
    if meta["scenarioId"] in {"incorrect-readback", "missing-evidence"}:
        checks["initialMismatchRecordedBeforeScriptEnded"] = any(
            a["assessmentType"] == "alignment" and a.get("decisionOutput", {}).get("choice") == "contradicts"
            and a.get("decisionOutput", {}).get("confidence", 0) >= 0.7
            and a.get("completedAtSimulationTimeMs", float("inf")) < meta["simulationTimeMs"]
            for a in assessments)
    if meta["scenarioId"] == "words-versus-actions":
        checks["movementCaptured"] = any(m["physical"]["status"] in {"moving", "runway_entered"} for _, m in early)
    if meta["scenarioId"] == "missing-evidence":
        checks["unknownPositionCaptured"] = any(m["physical"]["status"] == "unverified" for _, m in projected)
        checks["finalPhysicalEvidenceMatchesAvailability"] = monitor["physical"]["status"] == ("holding" if meta["preset"] == "complete" else "unverified")
    return {
        "case": path.stem, "scenario": meta["scenarioId"], "preset": meta["preset"], "recordedFrames": len(frames),
        "recordingComplete": meta["status"] == "completed", "checks": checks,
        "captureCoverage": {"mismatchVisibleInSampledFrames": any(m["communication"]["status"] == "mismatch" for _, m in early)},
        "executionClean": not errors and checks["noUnfinishedActivity"] and checks["noUnfinishedDecisions"],
        "advisoryOutcome": "published-current" if (monitor.get("advisory") or {}).get("isCurrent") else "withheld-or-outdated",
        "assessmentStatus": meta["assessmentStatus"], "finalCommunication": monitor["communication"]["status"],
        "finalPhysicalEvidence": monitor["physical"]["status"], "statusChanges": status_changes,
        "deciderCalls": len(assessments), "bedrockCalls": sum(t["actor"] == "bedrock" for t in traces),
        "activities": len(traces), "runtimeErrors": errors, "bedrockUsage": meta.get("bedrockUsage"),
        "bedrockUsageIncomplete": meta.get("bedrockUsageIncomplete", False),
        "deciderServiceMedianMs": round(statistics.median(decider_rtts), 2) if decider_rtts else None,
        "deciderRequestMedianMs": round(statistics.median(trace_rtts), 2) if trace_rtts else None,
        "recordedAlertLatenciesMs": [a for a in sorted({m["communication"].get("alertLatencyMs") for _, m in projected} - {None})],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [summarize(path) for path in sorted(args.directory.glob("*.jsonl"))]
    result = {"source": "deployed-live-recordings", "cases": cases,
              "completedCases": sum(case.get("recordingComplete", False) for case in cases),
              "expectedCases": 9,
              "limitations": ["Recorded model outputs from fictional scripted scenarios, not real ATC incident recordings.",
                              "DynamoDB polling captures observed persisted revisions; transitions between polls may be missed.",
                              "A guard rejection or withheld advisory is distinct from a runtime failure."]}
    value = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(value + "\n")
    print(value)


if __name__ == "__main__":
    main()
