"""Focused privacy, evidence, timing, and read-only recorder checks; no inference."""
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
export = importlib.import_module("export_replays")
record = importlib.import_module("record_replays")


@pytest.fixture
def frames():
    scenario_data = (ROOT / "scenarios/incorrect-readback/v3/scenario.json").read_bytes()
    session = "session_1111111111111111"
    assessment = "assessment_2222222222222222"
    trace = "trace_3333333333333333"
    meta = {
        "PK": f"SESSION#{session}", "SK": "META", "sessionId": session, "traineeId": "private-owner-example",
        "GSI1PK": "USER#private-owner-example", "GSI1SK": f"SESSION#date#{session}",
        "scenarioId": "incorrect-readback", "scenarioVersion": "3", "preset": "partial", "playback": "typed",
        "scenarioRef": {"sha256": hashlib.sha256(scenario_data).hexdigest(), "bucket": "private-bucket-example",
                        "versionId": "private-version-example", "key": "scenarios/incorrect-readback/v3/scenario.json"},
        "status": "running", "createdAt": "2026-01-01T10:00:00+00:00", "startedAt": "2026-01-01T10:00:00+00:00",
        "endedAt": None, "simulationTimeMs": 5000, "simulationFinished": False, "revision": 8,
        "latestSnapshotVersion": 2, "lastEventSequence": 2, "providerMode": "live", "bedrockUsage": None,
        "assessmentStatus": "pending", "bedrockUsageIncomplete": False,
    }
    snapshot = {"SK": "SNAPSHOT#0000000002", "snapshotVersion": 2, "simulationTimeMs": 5000,
                "savedAt": "2026-01-01T10:00:05+00:00", "worldState": {
        "distanceBeforeHoldM": -99, "speedMps": 42, "runwayEntered": True,
        "motionPlan": "private-hidden-world", "observationAvailable": False,
        "lastObservation": {"distanceBeforeHoldM": 50, "speedMps": 0, "runwayEntered": False, "observedAtMs": 0},
    }}
    events = [{"SK": f"EVENT#{i:010d}", "PK": f"SESSION#{session}", "eventId": f"{session}:{i}",
               "sequence": i, "simulationTimeMs": ms, "recordedAt": timestamp,
               "type": kind, "actor": actor, "payload": {"text": text}}
              for i, ms, timestamp, kind, actor, text in [
                  (1, 2000, "2026-01-01T10:00:02+00:00", "trainee_instruction", "trainee", "AIR123, hold short of runway 36."),
                  (2, 5000, "2026-01-01T10:00:05+00:00", "pilot_readback", "pilot", "Lining up runway 36, AIR123."),
              ]]
    decision = {
        "SK": f"ASSESSMENT#{assessment}", "assessmentId": assessment, "assessmentType": "alignment",
        "processingStatus": "pending", "jobKey": f"{session}:2", "startedAt": "2026-01-01T10:00:05+00:00",
        "evidenceRefs": {"eventIds": [f"{session}:1", f"{session}:2"], "snapshotVersion": 2},
        "decisionInput": {"state": "AIR123 readback", "questions": {}}, "providerMode": "live",
    }
    activity = {"SK": f"TRACE#time#{trace}", "id": trace, "actor": "decider", "title": "Compare readback",
                "status": "running", "startedAt": "2026-01-01T10:00:05+00:00", "simulationTimeMs": 5000,
                "inputs": {"assessmentId": assessment, "capability": "choice"}}
    first = {"observedAt": "2026-01-01T10:00:05.200000+00:00", "records": [meta, snapshot, *events, decision, activity]}
    second = copy.deepcopy(first)
    second["observedAt"] = "2026-01-01T10:00:07.300000+00:00"
    second["records"][0].update(status="completed", simulationTimeMs=7000, revision=12,
                                 endedAt="2026-01-01T10:00:07+00:00", bedrockUsage={"inputTokens": 500, "outputTokens": 50})
    completed = second["records"][-2]
    completed.update(processingStatus="completed", endedAt="2026-01-01T10:00:07+00:00", roundTripMs=1990.25,
                     modelVersion="strands-decider-2b", decisionOutput={"type": "choice", "choice": "contradicts",
                     "confidence": 0.97, "probabilities": {"matches": 0.01, "contradicts": 0.97, "unclear": 0.02}})
    second["records"][-1].update(status="completed", endedAt="2026-01-01T10:00:07+00:00", roundTripMs=1995,
                                  output={"assessmentId": assessment, "answer": completed["decisionOutput"]})
    second["records"].append({"SK": "TRACE#time#bedrock", "id": "trace_4444444444444444", "actor": "bedrock",
                               "title": "Assistant model call", "status": "completed", "simulationTimeMs": 6000,
                               "startedAt": "2026-01-01T10:00:06+00:00", "endedAt": "2026-01-01T10:00:07+00:00",
                               "inputs": {"model": "eu.amazon.nova-lite-v1:0"},
                               "output": {"tools": ["present_feedback"], "stopReason": "tool_use"}, "roundTripMs": 1000})
    return [first, second]


def export_frames(frames):
    return export.export_capture(frames, {"pollIntervalMs": 500}, ROOT / "scenarios")


def test_preserves_pending_completed_decision_and_measured_time(frames):
    result = export_frames(frames)
    before, after = [frame["view"] for frame in result["frames"]]
    assert before["monitor"]["communication"]["status"] == "checking"
    assert after["monitor"]["communication"]["status"] == "mismatch"
    assert before["traces"][0]["status"] == "running"
    assert after["traces"][0]["status"] == "completed"
    assert [frame["elapsedMs"] for frame in result["frames"]] == [5200, 7300]
    assert after["assessments"][0]["roundTripMs"] == 1990.25
    assert after["assessments"][0]["decisionOutput"]["confidence"] == .97
    assert after["monitor"]["communication"]["alertLatencyMs"] == 2000
    assert after["events"][1]["recordedAt"] == "2026-01-01T10:00:05+00:00"
    assert result["summary"]["verifiedLiveInference"] is True
    assert result["summary"]["allActivityStartsObserved"] is False
    assert after["bedrockUsage"] == {"inputTokens": 500, "outputTokens": 50}


def test_ids_are_deterministic_and_cross_references_survive(frames):
    first = export_frames(frames)
    second = export_frames(copy.deepcopy(frames))
    assert first == second
    view = first["frames"][-1]["view"]
    event_id = view["events"][1]["eventId"]
    assessment_id = view["assessments"][0]["assessmentId"]
    assert view["assessments"][0]["jobKey"] == event_id
    assert view["traces"][0]["inputs"]["assessmentId"] == assessment_id
    assert view["monitor"]["issues"][0]["id"] == f"readback:{event_id}"
    assert view["monitor"]["communication"]["assessmentId"] == assessment_id


def test_does_not_export_hidden_world_or_private_records(frames):
    result = export_frames(frames)
    text = json.dumps(result)
    for private in ["private-owner-example", "private-bucket-example", "private-version-example", "scenarioRef",
                    "private-hidden-world", "worldState", "session_1111111111111111", '"PK"', '"SK"']:
        assert private not in text
    assert result["frames"][-1]["view"]["observation"]["distanceBeforeHoldM"] == 50
    assert result["frames"][-1]["view"]["monitor"]["physical"]["distanceBeforeHoldM"] is None


def test_observation_timeline_preserves_persisted_time_without_fabricating_frames(frames):
    snapshot = frames[-1]["records"][1]
    snapshot.update(simulationTimeMs=7000, savedAt="2026-01-01T10:00:07.010000+00:00")
    before = export_frames(frames)
    initial = copy.deepcopy(snapshot)
    initial.update(SK="SNAPSHOT#0000000001", snapshotVersion=1, simulationTimeMs=0,
                   savedAt="2026-01-01T09:59:59.800000+00:00",
                   continuationState={"private": "never-export-this"})
    initial["worldState"]["lastObservation"]["unexpectedPrivateField"] = "never-export-this-either"
    frames[-1]["records"].append(initial)
    result = export_frames(frames)
    assert result["frames"] == before["frames"]
    assert result["summary"]["recordedObservationCount"] == 2
    first, last = result["recordedObservations"]
    assert [first["snapshotVersion"], last["snapshotVersion"]] == [1, 2]
    assert [first["elapsedMs"], last["elapsedMs"]] == [-200, 7010]
    assert first["savedAt"] == "2026-01-01T09:59:59.800000+00:00"
    assert first["observation"]["ageMs"] == 0
    assert first["observation"]["status"] == "current"
    assert last["observation"]["ageMs"] == 7000
    assert last["observation"]["status"] == "stale"
    assert last["observation"]["distanceBeforeHoldM"] == 50
    assert last["observation"]["speedMps"] == 0
    assert last["observation"]["runwayEntered"] is False
    text = json.dumps(result)
    assert "never-export-this" not in text
    assert "private-hidden-world" not in text
    assert "continuationState" not in text


def test_redacts_nested_error_details_without_erasing_error_status(frames):
    frames[-1]["records"][-1].update(status="error", output={
        "error": "provider failed for example@example.test arn:aws:bedrock:eu-west-1:123456789012:model/private at https://private.internal/path and private-owner-example",
        "ResponseMetadata": {"RequestId": "private-request"}, "accountId": "123456789012",
    })
    result = export_frames(frames)
    text = json.dumps(result)
    assert result["summary"]["errorTraces"] == 1
    assert result["summary"]["verifiedLiveInference"] is False
    for private in ["example@example.test", "123456789012", "private.internal", "private-request"]:
        assert private not in text
    assert "Provider or tool error (private details removed)" in text
    assert result["summary"]["quality"] == "degraded"


def test_timeout_category_and_partial_usage_are_preserved(frames):
    frames[-1]["records"][-1].update(status="error", output={"error": "TimeoutError: private.internal request private-id"})
    frames[-1]["records"][0]["bedrockUsageIncomplete"] = True
    result = export_frames(frames)
    assert result["frames"][-1]["view"]["traces"][-1]["output"]["error"] == "TimeoutError"
    assert result["summary"]["bedrockUsageIncomplete"] is True
    assert result["summary"]["quality"] == "degraded"


@pytest.mark.parametrize("mutation,category", [
    (lambda f: f[-1]["records"][0]["scenarioRef"].update(sha256="bad"), "PinnedScenarioHashMismatch"),
    (lambda f: f[-1]["records"][-3]["decisionOutput"].update(fixture=True), "FixtureResultNotPublishableAsLive"),
    (lambda f: f[-1]["records"][-3]["evidenceRefs"]["eventIds"].append("unknown-reference"), "UnresolvedPublicEventReference"),
])
def test_rejects_false_provenance_and_broken_references(frames, mutation, category):
    mutation(frames)
    with pytest.raises(export.ExportError, match=category):
        export_frames(frames)


def test_recorder_rejects_writes_and_never_exposes_cli_error_body(monkeypatch):
    with pytest.raises(record.ReadError, match="OperationNotAllowed"):
        record.aws_read("put-item", {}, "test-profile", "eu-west-1")
    monkeypatch.setattr(record.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout="secret-output", stderr="An error occurred (AccessDeniedException): private-account-and-token"))
    with pytest.raises(record.ReadError) as error:
        record.aws_read("scan", {}, "test-profile", "eu-west-1")
    assert str(error.value) == "AccessDeniedException"


def test_recorder_rejects_partition_spanning_commit(monkeypatch):
    monkeypatch.setattr(record, "pages", lambda *args: [{"SK": "META", "revision": 3}])
    monkeypatch.setattr(record, "aws_read", lambda *args: {"Item": {"revision": {"N": "4"}}})
    args = SimpleNamespace(table="test", profile="test", region="eu-west-1")
    assert record.partition(args, "private-session") is None


def test_recorder_rejects_commit_before_query_reaches_meta(monkeypatch):
    monkeypatch.setattr(record, "pages", lambda *args: [{"SK": "ASSESSMENT#old", "processingStatus": "pending"},
                                                      {"SK": "META", "revision": 4}])
    reads = iter([{"Item": {"revision": {"N": "3"}}}, {"Item": {"revision": {"N": "4"}}}])
    monkeypatch.setattr(record, "aws_read", lambda *args: next(reads))
    args = SimpleNamespace(table="test", profile="test", region="eu-west-1")
    assert record.partition(args, "private-session") is None


def test_resume_preserves_completed_files_and_appends_active(frames, tmp_path):
    metadata = {"schemaVersion": "atc-assistant-private-recording/1", "scenarioVersion": "3",
                "expectedCases": 9, "startedAt": "2026-01-01T10:00:00+00:00"}
    meta_path = tmp_path / "capture.json"
    meta_path.write_text(json.dumps(metadata))
    completed_path = tmp_path / "incorrect-readback-v3-partial.jsonl"
    completed_path.write_text(json.dumps(frames[-1]) + "\n")
    active_frame = copy.deepcopy(frames[0])
    active_frame["records"][0]["preset"] = "missed"
    active_frame["captureElapsedMs"] = 5200
    active_path = tmp_path / "incorrect-readback-v3-missed.jsonl"
    active_path.write_text(json.dumps(active_frame) + "\n")
    originals = {path: path.read_bytes() for path in [meta_path, completed_path, active_path]}
    args = SimpleNamespace(version="3", cases=9, poll=.5)
    started, offset, active, seen, finished = record.resume_capture(tmp_path, args)
    assert started == metadata["startedAt"] and offset > 0
    assert finished == {"incorrect-readback-v3-partial"}
    assert len(seen) == 2 and len(active) == 1
    assert all(path.read_bytes() == data for path, data in originals.items())
    capture = next(iter(active.values()))
    assert capture["elapsedOffset"] >= 5200
    record.write_json(capture["file"], {"resumeTest": True})
    capture["file"].close()
    assert active_path.read_bytes().startswith(originals[active_path])
    resume = json.loads((tmp_path / "resume-0001.json").read_text())
    assert resume["consistencyStrategy"] == "meta-before-query-meta-after"


def test_decoder_preserves_numbers_null_and_nested_values():
    assert record.decode_item({"x": {"M": {"a": {"N": "1.25"}, "b": {"NULL": True},
                                          "c": {"L": [{"BOOL": True}, {"N": "4"}]}}}}) == {
        "x": {"a": 1.25, "b": None, "c": [True, 4]}}
