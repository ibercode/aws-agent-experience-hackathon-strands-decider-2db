"""Time-travel prevention against the immutable sanitized recordings; no inference."""
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
timeline = importlib.import_module("build_replay_timeline")


@pytest.fixture(scope="module")
def selected():
    return timeline.select_recordings(ROOT / "recordings/v3", [ROOT / "recordings/retake-partial-20261017"])


@pytest.fixture(scope="module")
def sparse(selected):
    source = selected["missing-evidence-v3-partial"]
    return source["recording"], timeline.build_timeline(source["recording"], source)


def test_sparse_capture_regains_real_early_mismatch_without_changing_results(sparse):
    source, result = sparse
    assert len(source["frames"]) == 4
    assert not any(frame["view"]["monitor"]["communication"]["status"] == "mismatch" for frame in source["frames"])
    final = source["frames"][-1]["view"]
    start = timeline.iso(final["startedAt"])
    original = next(item for item in final["assessments"] if item["assessmentType"] == "alignment"
                    and item.get("decisionOutput", {}).get("choice") == "contradicts")
    correction = next(event for event in final["events"] if event["payload"].get("scriptStepId") == "correction")
    alerts = [frame for frame in result["frames"] if frame["view"]["monitor"]["communication"]["status"] == "mismatch"]
    assert alerts
    assert alerts[0]["elapsedMs"] == timeline.elapsed(original["endedAt"], start)
    assert alerts[0]["elapsedMs"] < timeline.elapsed(correction["recordedAt"], start)
    corrected = next(frame for frame in result["frames"]
                     if frame["elapsedMs"] == timeline.elapsed(correction["recordedAt"], start))
    assert corrected["view"]["monitor"]["communication"]["status"] == "checking"
    assert corrected["view"]["monitor"]["communication"]["readback"] is None
    assert result["frames"][-1]["view"]["assessments"] == final["assessments"]
    assert result["frames"][-1]["view"]["monitor"] == final["monitor"]


def test_results_and_feedback_never_appear_before_recorded_timestamps(sparse):
    source, result = sparse
    final = source["frames"][-1]["view"]
    start = timeline.iso(final["startedAt"])
    for frame in result["frames"]:
        clock, view = frame["elapsedMs"], frame["view"]
        for event in view["events"]:
            assert timeline.elapsed(event["recordedAt"], start) <= clock
        for item in view["assessments"]:
            assert timeline.elapsed(item["startedAt"], start) <= clock
            if item["processingStatus"] == "pending":
                assert not set(item).intersection({"endedAt", "decisionOutput", "error", "roundTripMs", "usage",
                                                   "modelVersion", "completedAtSimulationTimeMs"})
            else:
                assert timeline.elapsed(item["endedAt"], start) <= clock
        for item in view["traces"]:
            assert timeline.elapsed(item["startedAt"], start) <= clock
            if item["status"] == "running":
                assert not set(item).intersection({"endedAt", "output", "error", "roundTripMs"})
            else:
                assert timeline.elapsed(item["endedAt"], start) <= clock
        advisory = view["monitor"]["advisory"]
        if advisory:
            event = next(event for event in final["events"] if event["eventId"] == advisory["eventId"])
            assert timeline.elapsed(event["recordedAt"], start) <= clock
        if view["status"] == "completed":
            assert timeline.elapsed(final["endedAt"], start) <= clock
            assert any(event["type"] == "session_completed" for event in view["events"])
        else:
            assert view["endedAt"] is None and view["assessmentStatus"] == "pending"


def test_usage_changes_only_at_original_samples_and_observations_do_not_look_ahead(sparse):
    source, result = sparse
    start = timeline.iso(source["frames"][-1]["view"]["startedAt"])
    for frame in result["frames"]:
        clock = frame["elapsedMs"]
        samples = [item for item in source["frames"] if timeline.elapsed(item["observedAt"], start) <= clock]
        expected = samples[-1]["view"] if samples else {}
        assert frame["view"]["bedrockUsage"] == expected.get("bedrockUsage")
        assert frame["view"]["bedrockUsageIncomplete"] == expected.get("bedrockUsageIncomplete", False)
        available = [item for item in source["recordedObservations"] if timeline.elapsed(item["savedAt"], start) <= clock]
        latest = max(available, key=lambda item: (item["savedAt"], item["snapshotVersion"]))
        assert frame["provenance"]["observationSnapshotVersion"] == latest["snapshotVersion"]
        for key in ["distanceBeforeHoldM", "speedMps", "runwayEntered", "observedAtMs"]:
            assert frame["view"]["observation"][key] == latest["observation"][key]
        if frame["view"]["observation"]["status"] == "stale":
            assert frame["view"]["monitor"]["physical"]["distanceBeforeHoldM"] is None
            assert frame["view"]["monitor"]["physical"]["speedMps"] is None
    assert result["frames"][0]["view"]["bedrockUsage"] is None
    assert result["frames"][0]["provenance"]["usageAvailability"] == "not-yet-sampled"


def test_clean_retake_is_explicit_and_original_failure_remains_immutable(selected):
    original_path = ROOT / "recordings/v3/incorrect-readback-v3-partial.json"
    original_bytes = original_path.read_bytes()
    original = json.loads(original_bytes)
    assert original["summary"]["quality"] == "degraded"
    active = selected["incorrect-readback-v3-partial"]
    result = timeline.build_timeline(active["recording"], active)
    assert result["summary"]["quality"] == "complete"
    assert result["summary"]["errorTraces"] == 0
    assert result["provenance"]["selectedRetake"] is True
    assert result["provenance"]["supersedesSha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert original_path.read_bytes() == original_bytes


def test_builder_is_deterministic_and_has_no_cloud_side_effects(selected, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Cloud or recovery call attempted")
    boto = importlib.import_module("boto3")
    monkeypatch.setattr(boto, "Session", forbidden)
    monkeypatch.setattr(timeline.export.Engine, "get", forbidden)
    item = selected["incorrect-readback-v3-partial"]
    before = copy.deepcopy(item)
    assert timeline.build_timeline(item["recording"], item) == timeline.build_timeline(item["recording"], item)
    assert item == before


def test_modified_source_hash_is_rejected(tmp_path):
    filename = "case.json"
    (tmp_path / filename).write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schemaVersion": "atc-assistant-public-replay-manifest/1",
        "recordings": [{"file": filename, "sha256": "wrong", "recordingId": "case"}],
    }))
    with pytest.raises(timeline.TimelineError, match="RecordingHashMismatch"):
        timeline.public_records(tmp_path)
