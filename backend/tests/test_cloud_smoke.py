import copy

import pytest

from clearance_gap.cloud_smoke import run, validate_result

MODEL = "StrandsAgents/example-decider"


def completed_view():
    return dict(status="completed", assessmentStatus="completed", providerMode="live",
                scenarioRef={"versionId": "version-1"},
                initialSetup={"runway": "36", "reciprocalRunway": "18"},
                bedrockUsage={"inputTokens": 100, "outputTokens": 20},
                monitor={"communication": {"status": "matches", "assessmentId": "alignment-corrected"},
                         "physical": {"source": "simulator"},
                         "issues": [{"kind": "readback_mismatch", "status": "communication_resolved"}]},
                events=[{"type": "instructor_feedback", "payload": {"text": "Inspect the runway 36 holding point."}},
                        {"type": "trainee_instruction", "payload": {"text": "AIR123, hold short of runway 36."}},
                        {"type": "pilot_readback", "payload": {"text": "Holding short of runway 36, AIR123."}}],
                traces=[{"status": "completed"}],
                assessments=[dict(processingStatus="completed", providerMode="live", modelVersion=f"{MODEL}@revision",
                                  decisionOutput={"type": kind}) for kind in ["choice", "noul", "score"]])


def test_live_smoke_requires_real_model_usage_and_versioned_evidence():
    valid = completed_view()
    assert all(validate_result(valid, MODEL).values())
    for field, value in [("providerMode", "fixture"), ("events", []), ("bedrockUsage", {}),
                         ("scenarioRef", {}), ("assessments", []), ("traces", [{"status": "error"}]),
                         ("monitor", {}), ("bedrockUsageIncomplete", True), ("initialSetup", {})]:
        invalid = copy.deepcopy(valid)
        invalid[field] = value
        assert not all(validate_result(invalid, MODEL).values())
    invalid = copy.deepcopy(valid)
    invalid["assessments"][0]["decisionOutput"]["fixture"] = True
    assert not validate_result(invalid, MODEL)["realDeciderResults"]
    invalid["assessments"][0]["modelVersion"] = "DEVELOPMENT_FIXTURE"
    assert not validate_result(invalid, MODEL)["realDeciderResults"]


def test_live_smoke_rejects_old_runway_mentions_in_new_version_dialogue_and_advisory():
    invalid = completed_view()
    invalid["events"][0]["payload"]["text"] = "Inspect the runway 27 holding point."
    assert not validate_result(invalid, MODEL)["advisoryRunways"]
    invalid = completed_view()
    invalid["events"][1]["payload"]["text"] = "AIR123, hold short of runway 27."
    assert not validate_result(invalid, MODEL)["radioRunways"]


async def test_cloud_smoke_rejects_development_before_any_provider_call(config):
    with pytest.raises(ValueError, match="requires production"):
        await run(config, 30)
