"""One-off ECS runtime validation: python -m clearance_gap.cloud_smoke.

Uses the production task role, versioned scenario catalog, DynamoDB and live models.
This internal check never creates a Cognito user or authenticates through the HTTP API;
test public access controls and the browser login flow separately. Run during deployment
before admitting interactive users, because its coordinator has a separate admission lock.
The synthetic session remains in DynamoDB as deployment evidence.
"""
import argparse
import asyncio
import json
import logging
import re
import time
import uuid

from .catalog import CURRENT_SCENARIO_VERSION, Catalog
from .config import Settings
from .decisions import DecisionClient
from .engine import Engine
from .store import Store

SCENARIO = dict(scenarioId="incorrect-readback", scenarioVersion=CURRENT_SCENARIO_VERSION, preset="partial", playback="typed")


def validate_result(view, expected_model):
    """Return fixed failure labels; never serialize provider exceptions or credentials."""
    assessments = view.get("assessments", [])
    events, traces = view.get("events", []), view.get("traces", [])
    usage = view.get("bedrockUsage") or {}
    monitor = view.get("monitor") or {}
    communication = monitor.get("communication") or {}
    setup = view.get("initialSetup") or {}
    radio = [event for event in events if event.get("type") in {"trainee_instruction", "pilot_readback"}]
    feedback = [event for event in events if event.get("type") == "instructor_feedback"]

    def runway_mentions(records):
        return re.findall(r"runway\s+(\d+)", " ".join(event.get("payload", {}).get("text", "") for event in records), re.I)

    checks = {
        "completed": view.get("status") == "completed" and view.get("assessmentStatus") == "completed",
        "liveProviders": view.get("providerMode") == "live",
        "feedbackPublished": any(e.get("type") == "instructor_feedback" for e in events),
        "noRuntimeErrors": all(t.get("status") == "completed" for t in traces)
        and not any(e.get("type") == "runtime_error" for e in events),
        "realDeciderResults": bool(assessments) and all(
            a.get("processingStatus") == "completed"
            and a.get("providerMode") == "live"
            and isinstance(a.get("modelVersion"), str)
            and a["modelVersion"].split("@", 1)[0] == expected_model.split("@", 1)[0]
            and not a.get("decisionOutput", {}).get("fixture") for a in assessments
        ),
        "allThreeCapabilities": {"choice", "noul", "score"}.issubset(
            {a.get("decisionOutput", {}).get("type") for a in assessments}
        ),
        "bedrockTokenUsage": usage.get("inputTokens", 0) > 0 and usage.get("outputTokens", 0) > 0,
        "bedrockUsageComplete": not view.get("bedrockUsageIncomplete", False),
        "versionedScenario": bool(view.get("scenarioRef", {}).get("versionId")),
        "currentRunwayLayout": setup.get("runway") == "36" and setup.get("reciprocalRunway") == "18",
        "radioRunways": bool(radio) and set(runway_mentions(radio)) == {setup.get("runway")},
        "advisoryRunways": set(runway_mentions(feedback)).issubset({setup.get("runway"), setup.get("reciprocalRunway")}),
        "correctedReadback": communication.get("status") == "matches" and bool(communication.get("assessmentId")),
        "separatePhysicalObservation": monitor.get("physical", {}).get("source") == "simulator",
        "originalIssueRetained": any(issue.get("kind") == "readback_mismatch"
                                     and issue.get("status") == "communication_resolved"
                                     for issue in monitor.get("issues", [])),
    }
    return checks


async def run(config, timeout_seconds):
    if config.app_env != "production":
        raise ValueError("This check requires production configuration")
    store, catalog = Store(config), Catalog(config)
    engine = Engine(config, store, catalog, DecisionClient(config))
    reload_engine = None
    started = time.monotonic()
    owner = f"deployment-smoke-{uuid.uuid4().hex}"
    try:
        async with asyncio.timeout(timeout_seconds):
            session = await engine.create(owner, SCENARIO, f"create-{uuid.uuid4().hex}")
            await engine.control(session, "start", f"start-{uuid.uuid4().hex}")
            samples = []
            while session.meta["status"] == "running":
                async with session.lock:
                    view = engine.view(session)
                    communication = view["monitor"]["communication"]
                    sample = {"simulationTimeMs": view["simulationTimeMs"],
                              "simulationFinished": view["simulationFinished"],
                              "status": communication["status"], "assessmentId": communication["assessmentId"],
                              "physicalStatus": view["monitor"]["physical"]["status"],
                              "roundTripMs": communication["roundTripMs"], "alertLatencyMs": communication["alertLatencyMs"]}
                    if not samples or any(sample[key] != samples[-1][key] for key in
                                          ["simulationFinished", "status", "assessmentId", "physicalStatus"]):
                        samples.append(sample)
                await asyncio.sleep(1)
            async with session.lock:
                original = engine.view(session)
            checks = validate_result(original, config.decider_model_id)
            checks["mismatchBeforeEnd"] = any(sample["status"] == "mismatch" and not sample["simulationFinished"]
                                               for sample in samples)

            # A separate Store/Engine must recover the persisted result, not the original in-memory object.
            reload_engine = Engine(config, Store(config), Catalog(config), DecisionClient(config))
            restored = await reload_engine.get(session.meta["sessionId"], owner)
            restored_view = reload_engine.view(restored)
            checks["persistenceReload"] = (
                restored_view["status"] == original["status"] == "completed"
                and restored_view["revision"] == original["revision"]
                and restored_view["scenarioRef"] == original["scenarioRef"]
                and restored_view["initialSetup"] == original["initialSetup"]
                and restored_view["bedrockUsage"] == original["bedrockUsage"]
                and restored_view["monitor"] == original["monitor"]
                and all(len(restored_view[key]) == len(original[key])
                        for key in ["events", "assessments", "traces"])
                and all(validate_result(restored_view, config.decider_model_id).values())
            )
            usage = original.get("bedrockUsage") or {}
            return {
                "check": "cloud-runtime-smoke", "passed": all(checks.values()),
                "scope": "runtime-persistence-providers", "httpAuthenticationTested": False,
                "scenario": SCENARIO["scenarioId"], "preset": SCENARIO["preset"],
                "scenarioVersion": original["scenarioVersion"], "initialSetup": original["initialSetup"],
                "sessionId": original["sessionId"], "checks": checks,
                "decisions": len(original["assessments"]), "actions": len(original["traces"]),
                "monitorSamples": samples,
                "bedrockUsage": {key: usage.get(key, 0) for key in ["inputTokens", "outputTokens", "totalTokens"]},
                "elapsedSeconds": round(time.monotonic() - started, 1),
            }
    finally:
        if reload_engine is not None:
            await reload_engine.shutdown()
        await engine.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600, help="Total runtime timeout in seconds (30–1800)")
    args = parser.parse_args()
    if not 30 <= args.timeout <= 1800:
        parser.error("--timeout must be between 30 and 1800 seconds")
    logging.basicConfig(level=logging.CRITICAL)
    try:
        result = asyncio.run(run(Settings(_env_file=None), args.timeout))
    except Exception as exc:
        result = {"check": "cloud-runtime-smoke", "passed": False,
                  "scope": "runtime-persistence-providers", "httpAuthenticationTested": False,
                  "errorType": type(exc).__name__}
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
