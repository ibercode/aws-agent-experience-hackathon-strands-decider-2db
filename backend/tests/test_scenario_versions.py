import asyncio
import copy
import hashlib
import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from clearance_gap.api import CreateSession
from clearance_gap.catalog import CURRENT_SCENARIO_VERSION, Catalog, scenario_setup
from clearance_gap.decisions import evidence_catalog
from clearance_gap.engine import Engine

SCENARIOS = ["incorrect-readback", "words-versus-actions", "missing-evidence"]


@pytest.mark.parametrize("scenario_id", SCENARIOS)
@pytest.mark.parametrize("version,runway,reciprocal", [("1", "27", "09"), ("2", "27", "09"), ("3", "36", "18")])
def test_runway_metadata_matches_each_version_without_rewriting_definition(config, scenario_id, version, runway, reciprocal):
    catalog = Catalog(config)
    scenario, ref = catalog.load(scenario_id, version=version)
    original = copy.deepcopy(scenario)
    setup = scenario_setup(scenario)
    assert (setup["runway"], setup["reciprocalRunway"]) == (runway, reciprocal)
    assert scenario == original
    assert all(f"runway {runway}" in step["text"] for step in scenario["script"] if "runway" in step.get("text", ""))
    data = (Path(config.scenarios_path) / scenario_id / f"v{version}" / "scenario.json").read_bytes()
    assert ref["sha256"] == hashlib.sha256(data).hexdigest()


def test_current_catalog_and_new_api_requests_choose_version_three(config):
    listed = Catalog(config).list()
    assert {item["version"] for item in listed} == {CURRENT_SCENARIO_VERSION} == {"3"}
    assert all(item["initialSetup"]["runway"] == "36" and item["initialSetup"]["reciprocalRunway"] == "18"
               for item in listed)
    request = CreateSession(scenarioId="incorrect-readback")
    assert request.scenarioVersion == "3"
    with pytest.raises(ValidationError):
        CreateSession(scenarioId="incorrect-readback", scenarioVersion="4")


def test_s3_pinned_version_two_uses_its_original_key_and_object_version(config):
    data = (Path(config.scenarios_path) / "incorrect-readback/v2/scenario.json").read_bytes()
    calls = []

    class S3:
        def get_object(self, **kwargs):
            calls.append(kwargs)
            return {"Body": io.BytesIO(data), "VersionId": "saved-version"}

    catalog = Catalog(config)
    catalog.config = config.model_copy(update={"scenario_bucket": "scenario-test-bucket"})
    catalog.s3 = S3()
    pinned = {"key": "scenarios/incorrect-readback/v2/scenario.json", "versionId": "saved-version"}
    scenario, ref = catalog.load("incorrect-readback", pinned)
    assert calls == [{"Bucket": "scenario-test-bucket", "Key": pinned["key"], "VersionId": "saved-version"}]
    assert scenario["version"] == "2" and scenario_setup(scenario)["runway"] == "27"
    assert ref["versionId"] == pinned["versionId"]


@pytest.mark.parametrize("version,runway,reciprocal", [("1", "27", "09"), ("2", "27", "09"), ("3", "36", "18")])
async def test_saved_sessions_restore_their_runway_after_catalog_default_changes(engine, request_body, version, runway, reciprocal):
    session = await engine.create("alice", request_body | {"scenarioVersion": version}, f"create-version-{version}")
    restarted = Engine(engine.config, engine.store, engine.catalog, engine.decider)
    restored = await restarted.get(session.meta["sessionId"], "alice")
    view = restarted.view(restored)
    assert view["scenarioVersion"] == version
    assert view["initialSetup"]["runway"] == runway
    assert view["initialSetup"]["reciprocalRunway"] == reciprocal
    assert view["scenarioRef"] == session.meta["scenarioRef"]


async def test_version_three_exchange_and_assistant_evidence_use_runway_36(engine, request_body):
    session = await engine.create("alice", request_body | {"scenarioVersion": "3"}, "runway-36-exchange")
    session.meta["status"] = "running"
    await engine.advance(session, 5000)
    await asyncio.gather(*list(session.model_tasks))
    assert engine.view(session)["monitor"]["communication"]["status"] == "mismatch"
    await engine.advance(session, 13000)
    await asyncio.gather(*list(session.model_tasks))
    assert engine.view(session)["monitor"]["communication"]["status"] == "matches"
    evidence = await engine.capture(session)
    assert evidence["initialSetup"]["runway"] == "36"
    sources = evidence_catalog(evidence)
    assert "runway 36" in sources["scenario_layout"] and "reciprocal runway 18" in sources["scenario_layout"]
    assert "runway 27" not in " ".join(sources.values())
    assert all("runway 36" in event["payload"]["text"] for event in evidence["events"])
