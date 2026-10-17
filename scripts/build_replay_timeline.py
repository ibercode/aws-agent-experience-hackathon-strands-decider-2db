"""Build deterministic offline Session frames from sanitized durable timestamps.

No API, credentials, AWS clients, or model inference are used. Inputs are immutable
public recording bundles; output must be a new directory. --replace-from selects
an explicitly supplied sanitized retake while retaining the original source hash.
See recordings/public/README.md for the frame/provenance contract.
"""
import argparse
import copy
import hashlib
import importlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

export = importlib.import_module("export_replays")
monitor_view = importlib.import_module("clearance_gap.monitor").monitor_view


class TimelineError(Exception):
    """Safe validation category; never includes arbitrary input values."""


def iso(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError, TypeError) as exc:
        raise TimelineError("InvalidTimestamp") from exc


def elapsed(value, start):
    return round((iso(value) - start).total_seconds() * 1000, 3)


def public_records(directory):
    """Validate immutable manifest hashes before using any recording."""
    manifest = export.read_json(directory / "manifest.json")
    if manifest.get("schemaVersion") != "atc-assistant-public-replay-manifest/1":
        raise TimelineError("UnsupportedManifest")
    result = {}
    for entry in manifest["recordings"]:
        filename = entry["file"]
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise TimelineError("InvalidRecordingFilename")
        data = (directory / filename).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != entry["sha256"]:
            raise TimelineError("RecordingHashMismatch")
        recording = json.loads(data)
        identifier = recording.get("recordingId")
        if (recording.get("schemaVersion") != "atc-assistant-public-replay/1"
                or identifier != entry["recordingId"] or identifier in result):
            raise TimelineError("InvalidRecordingIdentity")
        if (recording.get("summary", {}).get("sessionStatus") != "completed"
                or not recording.get("summary", {}).get("verifiedLiveInference")):
            raise TimelineError("IncompleteOrUnverifiedSource")
        result[identifier] = {"recording": recording, "sha256": sha,
                              "source": f"{directory.name}/{filename}", "replacement": False}
    return result


def select_recordings(source, replacements):
    selected = public_records(source)
    for directory in replacements:
        for identifier, item in public_records(directory).items():
            if identifier not in selected or selected[identifier]["replacement"]:
                raise TimelineError("UnknownOrDuplicateReplacement")
            previous = selected[identifier]
            old, new = previous["recording"], item["recording"]
            if old["scenario"] != new["scenario"] or old["preset"] != new["preset"]:
                raise TimelineError("ReplacementScenarioMismatch")
            selected[identifier] = {**item, "replacement": True, "supersedesSha256": previous["sha256"],
                                    "supersedesSource": previous["source"]}
    return selected


def project_started(item, clock, start, kind):
    """A saved interval establishes pending/running status, not its future result."""
    if elapsed(item["startedAt"], start) > clock:
        return None
    value = copy.deepcopy(item)
    ended = item.get("endedAt")
    if ended and elapsed(ended, start) <= clock:
        return value
    if kind == "assessment":
        for key in ("decisionOutput", "modelVersion", "usage", "roundTripMs", "endedAt",
                    "completedAtSimulationTimeMs", "error"):
            value.pop(key, None)
        value["processingStatus"] = "pending"
    else:
        for key in ("output", "roundTripMs", "endedAt", "error"):
            value.pop(key, None)
        value["status"] = "running"
    return value


def build_timeline(recording, selection):
    original_frames = recording["frames"]
    final = original_frames[-1]["view"]
    start = iso(final["startedAt"])
    observations = recording.get("recordedObservations", [])
    if not observations:
        raise TimelineError("PersistedObservationsRequired")
    changes = defaultdict(list)
    anchors = []

    def boundary(value, kind, identifier=None, simulation=None):
        clock = max(0, elapsed(value, start))
        changes[clock].append({"kind": kind, **({"id": identifier} if identifier is not None else {})})
        if simulation is not None:
            anchors.append((clock, simulation))

    changes[0].append({"kind": "replay_start"})
    for event in final["events"]:
        boundary(event["recordedAt"], "event", event["eventId"], event["simulationTimeMs"])
    for item in final["assessments"]:
        boundary(item["startedAt"], "assessment_started", item["assessmentId"])
        if item.get("endedAt"):
            boundary(item["endedAt"], "assessment_ended", item["assessmentId"], item.get("completedAtSimulationTimeMs"))
    for item in final["traces"]:
        boundary(item["startedAt"], "activity_started", item["id"], item["simulationTimeMs"])
        if item.get("endedAt"):
            boundary(item["endedAt"], "activity_ended", item["id"])
    for item in observations:
        boundary(item["savedAt"], "persisted_observation", str(item["snapshotVersion"]), item["simulationTimeMs"])
    for index, frame in enumerate(original_frames):
        boundary(frame["observedAt"], "capture_sample", str(index), frame["view"]["simulationTimeMs"])
    if final.get("endedAt"):
        boundary(final["endedAt"], "session_ended")

    observation_times = sorted([(elapsed(row["savedAt"], start), row) for row in observations],
                               key=lambda pair: (pair[0], pair[1]["snapshotVersion"]))
    sample_times = sorted([(elapsed(row["observedAt"], start), row) for row in original_frames],
                          key=lambda pair: pair[0])
    completed_events = [event for event in final["events"] if event["type"] == "session_completed"]
    completion_time = max([elapsed(final["endedAt"], start),
                           *[elapsed(event["recordedAt"], start) for event in completed_events]])
    frames = []
    for clock in sorted(changes):
        events = [copy.deepcopy(event) for event in final["events"] if elapsed(event["recordedAt"], start) <= clock]
        events.sort(key=lambda event: event["sequence"])
        assessments = [value for item in final["assessments"]
                       if (value := project_started(item, clock, start, "assessment")) is not None]
        traces = [value for item in final["traces"]
                  if (value := project_started(item, clock, start, "trace")) is not None]
        traces.sort(key=lambda trace: trace["startedAt"])
        available_observations = [(time, item) for time, item in observation_times if time <= clock]
        if not available_observations:
            raise TimelineError("InitialObservationUnavailable")
        observation_time, source_observation = available_observations[-1]
        simulation = max([0, *[value for time, value in anchors if time <= clock]])
        if simulation > final["durationMs"]:
            raise TimelineError("SimulationClockExceedsScenario")
        observation = copy.deepcopy(source_observation["observation"])
        observation["ageMs"] = simulation - observation["observedAtMs"]
        if observation["ageMs"] < 0:
            raise TimelineError("ObservationFromFuture")
        observation["status"] = "current" if observation["ageMs"] <= 5000 else "stale"
        samples = [(time, item) for time, item in sample_times if time <= clock]
        sample_time, sample = samples[-1] if samples else (None, None)
        usage = copy.deepcopy(sample["view"].get("bedrockUsage")) if sample else None
        incomplete_usage = sample["view"].get("bedrockUsageIncomplete", False) if sample else False
        complete = clock >= completion_time
        status = "completed" if complete else "running"
        for event in events:
            if not complete and event["type"] in {"session_pause", "session_resume", "session_start"}:
                status = "paused" if event["type"] == "session_pause" else "running"
        view = {key: copy.deepcopy(final[key]) for key in (
            "sessionId", "scenarioId", "scenarioVersion", "title", "objective", "preset", "createdAt",
            "startedAt", "durationMs", "providerMode", "initialSetup",
        )}
        view.update(
            playback="typed", status=status, endedAt=final["endedAt"] if complete else None,
            simulationTimeMs=simulation, simulationFinished=any(event["type"] == "script_finished" for event in events),
            assessmentStatus=final["assessmentStatus"] if complete else "pending", observation=observation,
            events=events, assessments=assessments, traces=traces, bedrockUsage=usage,
            bedrockUsageIncomplete=incomplete_usage,
        )
        view["monitor"] = monitor_view(SimpleNamespace(meta=view, events=events, assessments=assessments), observation)
        export.validate_references(view)
        frames.append({"elapsedMs": clock, "view": view, "provenance": {
            "basis": "recorded-timestamp-derived", "transitions": changes[clock],
            "observationSnapshotVersion": source_observation["snapshotVersion"],
            "observationSavedAtMs": observation_time,
            "usageSampleElapsedMs": sample_time,
            "usageAvailability": "sampled" if sample else "not-yet-sampled",
        }})
    if (frames[-1]["view"]["assessments"] != final["assessments"]
            or frames[-1]["view"]["traces"] != sorted(final["traces"], key=lambda trace: trace["startedAt"])
            or frames[-1]["view"]["events"] != sorted(final["events"], key=lambda event: event["sequence"])
            or frames[-1]["view"]["bedrockUsage"] != final["bedrockUsage"]
            or frames[-1]["view"]["monitor"] != final["monitor"]):
        raise TimelineError("FinalEvidenceChanged")
    result = {key: copy.deepcopy(recording[key]) for key in
              ("schemaVersion", "recordingId", "scenario", "preset", "recordedObservations", "summary")}
    result["timelineVersion"] = "durable-timestamps/1"
    result["frames"] = frames
    result["provenance"] = {
        **copy.deepcopy(recording["provenance"]),
        "captureProvenance": copy.deepcopy(recording["provenance"]),
        "timing": "derived-from-original-durable-timestamps",
        "timelineNote": "Offline replay reconstructed from the actual event, assessment, activity and allowed-observation timestamps. Pending/running intervals are derived from recorded start/end times; recorded outputs appear only at their end time. This is not a frame-exact browser recording. No new inference runs.",
        "metricsNote": "Decider and activity durations are the original measured results. Cumulative Bedrock token totals and incomplete-usage flags change only at original capture samples; no intermediate token counts are estimated.",
        "observationNote": "Positions are held from the latest saved allowed observation. Simulation time advances only at recorded time anchors; neither hidden aircraft state nor interpolated movement is used.",
        "sourceRecordingSha256": selection["sha256"], "sourceRecording": selection["source"],
        "selectedRetake": selection["replacement"],
        **({key: selection[key] for key in ("supersedesSha256", "supersedesSource")} if selection["replacement"] else {}),
    }
    result["summary"].update(sourceFrameCount=len(original_frames), frameCount=len(frames),
                             recordingDurationMs=frames[-1]["elapsedMs"],
                             sourceQuality=recording["summary"]["quality"],
                             sampledTokenUsage=True, timelineDerived=True)
    return result


def generate(source, replacements, output, asset_base):
    directories = [source.resolve(), *[path.resolve() for path in replacements]]
    if any(output.resolve().is_relative_to(path) for path in directories):
        raise TimelineError("OutputMustNotModifySourceDirectory")
    if not asset_base.startswith("/") or asset_base.startswith("//") or ".." in asset_base or ":" in asset_base:
        raise TimelineError("AssetBaseMustBeSameOriginPath")
    selected = select_recordings(source, replacements)
    results = [build_timeline(item["recording"], item) for _, item in sorted(selected.items())]
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for result in results:
        filename = result["recordingId"] + ".json"
        data = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        (output / filename).write_bytes(data)
        scenario = result["scenario"]
        entries.append({
            "id": result["recordingId"], "recordingId": result["recordingId"], "file": filename,
            "src": asset_base.rstrip("/") + "/" + filename,
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "scenarioId": scenario["id"], "scenarioVersion": scenario["version"], "preset": result["preset"],
            **{key: scenario[key] for key in ("title", "description", "objective", "initialSetup", "durationMs")},
            "recordingDurationMs": result["summary"]["recordingDurationMs"], "summary": result["summary"],
            "selectedRetake": result["provenance"]["selectedRetake"],
        })
    manifest = {"schemaVersion": "atc-assistant-public-replay-manifest/1", "timelineVersion": "durable-timestamps/1",
                "inference": "recorded-live", "scenario": "fictional-scripted", "replayInvokesModels": False,
                "providers": ["Strands Decider 2B", "Amazon Bedrock"], "recordings": entries}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--replace-from", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-base", default="/recordings/v3")
    args = parser.parse_args()
    try:
        manifest = generate(args.input, args.replace_from, args.output, args.asset_base)
        print(json.dumps({"status": "generated", "recordings": len(manifest["recordings"]),
                          "retakes": sum(item["selectedRetake"] for item in manifest["recordings"]),
                          "frames": sum(item["summary"]["frameCount"] for item in manifest["recordings"])}))
        return 0
    except (TimelineError, export.ExportError, FileExistsError) as exc:
        print(json.dumps({"status": "rejected", "error": "OutputAlreadyExists" if isinstance(exc, FileExistsError)
                          else str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
