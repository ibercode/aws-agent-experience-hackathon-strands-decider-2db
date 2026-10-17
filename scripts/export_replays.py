"""Export private DynamoDB captures as sanitized, offline public Session frames.

Run using backend/.venv/bin/python. No AWS clients are instantiated, no credentials
are read, and no inference or network calls are made. Existing pure Engine.view
and monitor projection logic are reused without calling Engine.get or recovery.

Example: backend/.venv/bin/python scripts/export_replays.py --input
.data/recordings/BATCH --output frontend/public/recordings --require-complete-matrix

Top-level session metadata is allowlisted. Nested evidence and model outputs have
private fields/identifiers redacted; provider error bodies become safe categories.
Original wall-clock timestamps and measured durations remain unchanged. Review the
summary quality/usage flags; exporting a capture does not claim a successful run.
"""
import argparse
import copy
import hashlib
import importlib
import json
import re
import sys
from datetime import datetime
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

engine_module = importlib.import_module("clearance_gap.engine")
Engine, Session = engine_module.Engine, engine_module.Session

SCENARIOS = {"incorrect-readback", "words-versus-actions", "missing-evidence"}
PRESETS = {"missed", "partial", "complete"}
META_FIELDS = {
    "sessionId", "scenarioId", "scenarioVersion", "preset", "playback", "status", "createdAt", "updatedAt",
    "startedAt", "endedAt", "simulationTimeMs", "simulationFinished", "revision", "lastEventSequence",
    "latestSnapshotVersion", "providerMode", "bedrockUsage", "bedrockUsageIncomplete", "assessmentStatus",
}
PRIVATE_KEYS = {
    "pk", "sk", "gsi1pk", "gsi1sk", "traineeid", "owner", "ownerid", "userid", "username", "email",
    "cognitoid", "cognitosub", "sub", "accountid", "awsaccountid", "bucket", "bucketname", "versionid",
    "scenarioref", "requestid", "request_id", "authorization", "accesstoken", "idtoken", "refreshtoken",
    "secret", "password", "credentials", "responsemetadata",
}
SENSITIVE_PATTERNS = [
    re.compile(r"arn:aws(?:-[a-z]+)?:[^\s\"'<>]+"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])\d{12}(?![A-Za-z0-9])"),
    re.compile(r"https?://[^\s\"'<>]+"),
    re.compile(r"\b(?:session|assessment|trace)_[a-f0-9]{16}\b"),
]


class ExportError(Exception):
    """Safe category only; private input contents must not appear in diagnostics."""


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ExportError("InvalidJsonInput") from exc


def header(records):
    metas = [row for row in records if row.get("SK") == "META"]
    if len(metas) != 1:
        raise ExportError("MissingOrDuplicateMeta")
    return metas[0]


def stamp_ms(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp() * 1000
    except (ValueError, TypeError) as exc:
        raise ExportError("InvalidTimestamp") from exc


def load_capture(path):
    frames = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                frames.append(json.loads(line))
    except (ValueError, OSError) as exc:
        raise ExportError("InvalidCaptureJsonLines") from exc
    if not frames or any(not isinstance(frame.get("records"), list) for frame in frames):
        raise ExportError("EmptyOrInvalidCapture")
    previous, session_id = -1, header(frames[0]["records"])["sessionId"]
    for frame in frames:
        meta = header(frame["records"])
        observed = stamp_ms(frame["observedAt"])
        if observed < previous or meta["sessionId"] != session_id:
            raise ExportError("CaptureOrderingOrSessionMismatch")
        previous = observed
        if meta.get("providerMode") != "live":
            raise ExportError("FixtureCaptureNotPublishableAsLive")
    return frames


def scenario_for(meta, scenario_root):
    scenario_id, version = meta.get("scenarioId"), meta.get("scenarioVersion")
    if scenario_id not in SCENARIOS or version not in {"1", "2", "3"} or meta.get("preset") not in PRESETS:
        raise ExportError("UnsupportedScenarioOrPreset")
    path = scenario_root / scenario_id / f"v{version}" / "scenario.json"
    try:
        data = path.read_bytes()
        scenario = json.loads(data)
    except (ValueError, OSError) as exc:
        raise ExportError("ScenarioUnavailable") from exc
    sha = hashlib.sha256(data).hexdigest()
    if meta.get("scenarioRef", {}).get("sha256") != sha:
        raise ExportError("PinnedScenarioHashMismatch")
    if scenario.get("id") != scenario_id or scenario.get("version") != version:
        raise ExportError("ScenarioIdentityMismatch")
    return scenario, sha


def project(records, scenario):
    """Project only scenario-allowed observation, never export hidden worldState."""
    meta = header(records)
    snapshot_key = f"SNAPSHOT#{int(meta['latestSnapshotVersion']):010d}"
    snapshot = next((row for row in records if row.get("SK") == snapshot_key), None)
    if snapshot is None:
        raise ExportError("ReferencedSnapshotMissing")
    session = Session(
        meta={key: copy.deepcopy(value) for key, value in meta.items() if key in META_FIELDS},
        scenario=scenario, world=copy.deepcopy(snapshot["worldState"]),
        events=sorted([copy.deepcopy(row) for row in records if row.get("SK", "").startswith("EVENT#")],
                      key=lambda event: event["sequence"]),
        assessments=[copy.deepcopy(row) for row in records if row.get("SK", "").startswith("ASSESSMENT#")],
        traces=[copy.deepcopy(row) for row in records if row.get("SK", "").startswith("TRACE#")],
    )
    if any(event["sequence"] > meta["lastEventSequence"] for event in session.events):
        raise ExportError("InconsistentRecordRevision")
    # Deliberately bypass __init__: view/observation are pure projections and no
    # Store, Catalog, DecisionClient, cloud session, or background task is created.
    return Engine.view(object.__new__(Engine), session)


def collect_ids(frames, recording_id):
    all_records = {}
    for frame in frames:
        for row in frame["records"]:
            all_records[row["SK"]] = row
    mapping = {header(frames[0]["records"])["sessionId"]: f"replay_{recording_id}"}
    for row in all_records.values():
        if row.get("SK", "").startswith("EVENT#"):
            mapping[row["eventId"]] = f"{recording_id}:event:{row['sequence']:04d}"
    for prefix, field, public in [("ASSESSMENT#", "assessmentId", "assessment"), ("TRACE#", "id", "trace")]:
        rows = sorted([row for key, row in all_records.items() if key.startswith(prefix)],
                      key=lambda row: (row["startedAt"], row[field]))
        for index, row in enumerate(rows, 1):
            mapping[row[field]] = f"{recording_id}:{public}:{index:04d}"
    return mapping


class Sanitizer:
    def __init__(self, frames, recording_id):
        self.mapping = collect_ids(frames, recording_id)
        self.replacements = sorted(self.mapping, key=len, reverse=True)
        self.private_values = set()
        self.redactions = 0
        for frame in frames:
            meta = header(frame["records"])
            for key in ("traineeId", "GSI1PK", "GSI1SK"):
                if isinstance(meta.get(key), str) and meta[key]:
                    self.private_values.add(meta[key])
            ref = meta.get("scenarioRef", {})
            self.private_values.update(value for key, value in ref.items()
                                       if key != "sha256" and isinstance(value, str) and value)

    def string(self, value):
        for private in self.replacements:
            value = value.replace(private, self.mapping[private])
        for private in sorted(self.private_values, key=len, reverse=True):
            if private in value:
                self.redactions += 1
                value = value.replace(private, "[private reference removed]")
        for pattern in SENSITIVE_PATTERNS:
            value, count = pattern.subn("[private reference removed]", value)
            self.redactions += count
        return value

    def clean(self, value):
        if isinstance(value, dict):
            if value.get("fixture") is True:
                raise ExportError("FixtureResultNotPublishableAsLive")
            cleaned = {}
            for key, item in value.items():
                if key.lower() in PRIVATE_KEYS:
                    continue
                if key == "error":
                    # Provider exceptions can contain hosts, request IDs, or other
                    # arbitrary service metadata. Preserve their category only.
                    category = re.match(r"^([A-Za-z_][A-Za-z0-9_.]{0,70}(?:Error|Exception))(?::|\b)",
                                        item if isinstance(item, str) else "")
                    if item == "Execution interrupted":
                        cleaned[key] = "Execution interrupted"
                    elif category:
                        cleaned[key] = category.group(1)
                    else:
                        cleaned[key] = "Provider or tool error (private details removed)"
                    self.redactions += 1
                else:
                    cleaned[self.string(key)] = self.clean(item)
            return cleaned
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if isinstance(value, str):
            if "DEVELOPMENT_FIXTURE" in value:
                raise ExportError("FixtureResultNotPublishableAsLive")
            return self.string(value)
        return value

    def validate(self, value):
        serialized = json.dumps(value, ensure_ascii=False)
        if any(private in serialized for private in self.mapping):
            raise ExportError("PrivateIdentifierSurvivedSanitization")
        if any(private in serialized for private in self.private_values):
            raise ExportError("PrivateReferenceSurvivedSanitization")
        if any(pattern.search(serialized) for pattern in SENSITIVE_PATTERNS):
            raise ExportError("SensitivePatternSurvivedSanitization")
        def check(node):
            if isinstance(node, dict):
                if any(key.lower() in PRIVATE_KEYS for key in node):
                    raise ExportError("PrivateFieldSurvivedSanitization")
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(value)


def validate_references(view):
    events = {event["eventId"] for event in view["events"]}
    assessments = {item["assessmentId"] for item in view["assessments"]}
    singular_events = {"eventId", "resolvedByEventId", "advisoryEventId", "finalAdvisoryEventId", "jobKey"}
    singular_assessments = {"assessmentId", "guardAssessmentId", "qualityAssessmentId"}
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if value and key in singular_events and value not in events:
                    raise ExportError("UnresolvedPublicEventReference")
                if value and key in singular_assessments and value not in assessments:
                    raise ExportError("UnresolvedPublicAssessmentReference")
                if key in {"eventIds", "evidenceEventIds"} and any(item not in events for item in value):
                    raise ExportError("UnresolvedPublicEventReference")
                if key == "guardAssessmentIds" and any(item not in assessments for item in value):
                    raise ExportError("UnresolvedPublicAssessmentReference")
                walk(value)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(view)


def recorded_observations(records, start):
    """Export persisted allowed observations independently of sampled UI frames."""
    result = []
    rows = sorted([row for row in records if row.get("SK", "").startswith("SNAPSHOT#")],
                  key=lambda row: row["snapshotVersion"])
    versions = set()
    for row in rows:
        version = row["snapshotVersion"]
        if version in versions or version > header(records)["latestSnapshotVersion"]:
            raise ExportError("InvalidObservationSnapshotVersion")
        versions.add(version)
        # Deliberately allowlist lastObservation. Actual world position, motion
        # plans, observationAvailable and continuationState never enter output.
        allowed = row["worldState"]["lastObservation"]
        observation = {key: copy.deepcopy(allowed[key]) for key in
                       ("distanceBeforeHoldM", "speedMps", "runwayEntered", "observedAtMs")}
        age = row["simulationTimeMs"] - observation["observedAtMs"]
        if age < 0:
            raise ExportError("ObservationTimestampAfterSnapshot")
        observation.update(ageMs=age, status="current" if age <= 5000 else "stale")
        result.append({"snapshotVersion": version, "simulationTimeMs": row["simulationTimeMs"],
                       "savedAt": row["savedAt"], "elapsedMs": round(stamp_ms(row["savedAt"]) - start, 2),
                       "observation": observation})
    return result


def export_capture(frames, capture, scenario_root):
    final_meta = header(frames[-1]["records"])
    scenario, sha = scenario_for(final_meta, scenario_root)
    recording_id = f"{scenario['id']}-v{scenario['version']}-{final_meta['preset']}"
    cleaner = Sanitizer(frames, recording_id)
    start = stamp_ms(final_meta.get("startedAt") or final_meta["createdAt"])
    observations = cleaner.clean(recorded_observations(frames[-1]["records"], start))
    exported_frames = []
    for frame in frames:
        meta = header(frame["records"])
        if meta.get("providerMode") != "live":
            raise ExportError("FixtureCaptureNotPublishableAsLive")
        if any(meta.get(key) != final_meta.get(key) for key in
               ("sessionId", "scenarioId", "scenarioVersion", "preset")):
            raise ExportError("CaptureIdentityChanged")
        if meta.get("scenarioRef", {}).get("sha256") != sha:
            raise ExportError("ScenarioChangedDuringCapture")
        view = cleaner.clean(project(frame["records"], scenario))
        validate_references(view)
        exported_frames.append({"elapsedMs": round(max(0, stamp_ms(frame["observedAt"]) - start), 2),
                                "observedAt": frame["observedAt"], "view": view})
    final = exported_frames[-1]["view"]
    decider = [item for item in final["assessments"] if item.get("processingStatus") == "completed"]
    bedrock = [item for item in final["traces"] if item["actor"] == "bedrock" and item["status"] == "completed"]
    usage = final.get("bedrockUsage") or {}
    runtime_errors = [event for event in final["events"] if event["type"] == "runtime_error"]
    error_traces = [item for item in final["traces"] if item["status"] == "error"]
    published = [event for event in final["events"] if event["type"] == "instructor_feedback"]
    gaps = [b["elapsedMs"] - a["elapsedMs"] for a, b in pairwise(exported_frames)]
    observed_pending = {item["assessmentId"] for frame in exported_frames for item in frame["view"]["assessments"]
                        if item["processingStatus"] == "pending"}
    observed_running = {item["id"] for frame in exported_frames for item in frame["view"]["traces"]
                        if item["status"] == "running"}
    summary = {
        "sessionStatus": final["status"], "assessmentStatus": final["assessmentStatus"],
        "frameCount": len(exported_frames), "elapsedMs": exported_frames[-1]["elapsedMs"],
        "recordedObservationCount": len(observations),
        "firstObservedAtMs": exported_frames[0]["elapsedMs"], "maxObservedFrameGapMs": round(max(gaps, default=0), 2),
        "completedDecisions": len(decider), "completedBedrockCalls": len(bedrock),
        "publishedAdvisories": len(published), "runtimeErrors": len(runtime_errors), "errorTraces": len(error_traces),
        "bedrockUsage": usage, "bedrockUsageIncomplete": final.get("bedrockUsageIncomplete", False),
        "observedPendingAssessments": len(observed_pending), "observedRunningTraces": len(observed_running),
        "allDeciderStartsObserved": len(observed_pending) == len(final["assessments"]),
        "allActivityStartsObserved": len(observed_running) == len(final["traces"]),
        "verifiedLiveInference": bool(decider and bedrock and usage.get("inputTokens", 0) > 0),
    }
    summary["quality"] = (
        "incomplete" if final["status"] != "completed" else
        "degraded" if runtime_errors or error_traces or final.get("bedrockUsageIncomplete", False)
        or final["assessmentStatus"] != "completed" or not summary["verifiedLiveInference"] else "complete"
    )
    result = {
        "schemaVersion": "atc-assistant-public-replay/1", "recordingId": recording_id,
        "provenance": {
            "inference": "recorded-live", "scenario": "fictional-scripted", "replayInvokesModels": False,
            "captureMethod": "dynamodb-revision-poll", "pollIntervalMs": capture.get("pollIntervalMs"),
            "consistencyStrategies": sorted({frame.get("consistencyStrategy", capture.get("consistencyStrategy", "query-meta-after"))
                                             for frame in frames}),
            "timing": "observed-wall-clock", "originalTimestampsPreserved": True,
            "timelineNote": "Recorded real Decider and Bedrock inference on a fictional scripted ATC scenario. Frames are observed persisted revisions, not a continuous browser recording. Short transitions between polls may be absent. Aircraft display uses the latest persisted scenario-allowed observation.",
            "recordedObservationsSource": "All persisted SNAPSHOT records in the final captured partition, restricted to their allowed lastObservation. This independent timeline does not add or alter sampled frames, model decisions, or cumulative metrics.",
            "observationTimeOrigin": "Elapsed milliseconds from the original session start; a negative value identifies an observation saved before the replay started.",
            "eventAndDecisionTimeline": "The final frame contains the complete captured events, assessments and activity records with original timestamps. Their timestamps can support a future derived replay; unsampled intermediate model decisions and cumulative metric totals have not been invented.",
            "modelOutputs": "Recorded structured decisions, proposed findings and published advisory text; no private chain of thought or unpersisted model responses.",
        },
        "scenario": {key: copy.deepcopy(scenario[key]) for key in
                     ("id", "version", "title", "description", "objective", "initialSetup", "durationMs")}
                    | {"sha256": sha},
        "preset": final["preset"], "frames": exported_frames,
        "recordedObservations": observations, "summary": summary,
    }
    result["provenance"]["redactedStringOccurrences"] = cleaner.redactions
    cleaner.validate(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Private batch directory")
    parser.add_argument("--output", type=Path, required=True, help="New sanitized public artifact directory")
    parser.add_argument("--scenarios", type=Path, default=ROOT / "scenarios")
    parser.add_argument("--require-complete-matrix", action="store_true")
    args = parser.parse_args()
    try:
        capture = read_json(args.input / "capture.json")
        if capture.get("schemaVersion") != "atc-assistant-private-recording/1":
            raise ExportError("UnsupportedCaptureSchema")
        results = [export_capture(load_capture(path), capture, args.scenarios)
                   for path in sorted(args.input.glob("*.jsonl"))]
        if not results:
            raise ExportError("NoCapturesFound")
        matrix = {(item["scenario"]["id"], item["preset"]) for item in results}
        if len(matrix) != len(results):
            raise ExportError("DuplicateScenarioPreset")
        if args.require_complete_matrix and matrix != {(scenario, preset) for scenario in SCENARIOS for preset in PRESETS}:
            raise ExportError("IncompleteScenarioPresetMatrix")
        args.output.mkdir(parents=True, exist_ok=False)
        entries = []
        for result in results:
            filename = result["recordingId"] + ".json"
            data = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
            (args.output / filename).write_bytes(data)
            entries.append({"recordingId": result["recordingId"], "file": filename,
                            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                            "scenarioId": result["scenario"]["id"], "scenarioVersion": result["scenario"]["version"],
                            "preset": result["preset"], "summary": result["summary"]})
        manifest = {"schemaVersion": "atc-assistant-public-replay-manifest/1",
                    "inference": "recorded-live", "scenario": "fictional-scripted", "replayInvokesModels": False,
                    "recordings": entries}
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "exported", "recordings": len(results),
                          "verifiedLiveInference": sum(item["summary"]["verifiedLiveInference"] for item in results),
                          "allCompleted": all(item["summary"]["sessionStatus"] == "completed" for item in results)}))
        return 0
    except (ExportError, FileExistsError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc) if isinstance(exc, ExportError)
                          else "OutputAlreadyExists"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
