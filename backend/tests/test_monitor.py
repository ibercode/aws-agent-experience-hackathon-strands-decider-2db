import asyncio
import copy

import pytest

from clearance_gap.decisions import DecisionClient
from clearance_gap.engine import Engine
from clearance_gap.store import LimitExceeded


async def running(engine, request_body, **changes):
    session = await engine.create("alice", request_body | changes, "monitor-test-create")
    session.meta["status"] = "running"
    return session


async def settle(session):
    await asyncio.gather(*list(session.model_tasks))


async def test_decider_alert_is_visible_before_the_script_ends_without_bedrock(engine, request_body):
    session = await running(engine, request_body)
    await engine.advance(session, 5000)
    await settle(session)
    monitor = engine.view(session)["monitor"]
    assert not session.meta["simulationFinished"]
    assert monitor["communication"]["status"] == "mismatch"
    assert monitor["communication"]["title"] == "Possible readback mismatch"
    assert monitor["communication"]["confidence"] == 1
    assert monitor["communication"]["roundTripMs"] >= 0
    assert monitor["communication"]["alertLatencyMs"] >= 0
    assert monitor["communication"]["readback"]["eventId"] in monitor["communication"]["evidenceEventIds"]
    assert not any(trace["actor"] == "bedrock" for trace in session.traces)
    assert monitor["advisory"] is None


async def test_new_instruction_and_readback_never_reuse_the_previous_verdict(engine, request_body):
    session = await running(engine, request_body)
    await engine.advance(session, 5000)
    await settle(session)
    old = engine.view(session)["monitor"]["communication"]
    assert old["status"] == "mismatch"

    await engine.advance(session, 4000)
    current = engine.view(session)["monitor"]["communication"]
    assert current["status"] == "checking"
    assert current["reason"] == "awaiting_readback"
    assert current["readback"] is None and current["assessmentId"] is None
    assert current["instruction"]["eventId"] != old["instruction"]["eventId"]
    await settle(session)
    # advance() has returned before the new decision task runs.
    await engine.advance(session, 3000)
    current = engine.view(session)["monitor"]["communication"]
    assert current["status"] == "checking"
    assert current["readback"]["eventId"] != old["readback"]["eventId"]
    await settle(session)
    current = engine.view(session)["monitor"]
    assert current["communication"]["status"] == "matches"
    assert current["issues"][0]["status"] == "communication_resolved"


async def test_out_of_order_completion_updates_history_but_not_current_readback(engine, request_body):
    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedOldReadback(DecisionClient):
        async def ask(self, state, questions):
            if "alignment" in questions and "Lining up" in state["readback"]:
                entered.set()
                await release.wait()
            return await super().ask(state, questions)

    engine.decider = DelayedOldReadback(engine.config)
    session = await running(engine, request_body)
    await engine.advance(session, 5000)
    await entered.wait()
    old_task = next(iter(session.model_tasks))
    await engine.advance(session, 7000)
    await asyncio.gather(*(task for task in list(session.model_tasks) if task is not old_task))
    latest_id = engine.view(session)["monitor"]["communication"]["assessmentId"]
    assert engine.view(session)["monitor"]["communication"]["status"] == "matches"
    release.set()
    await settle(session)
    monitor = engine.view(session)["monitor"]
    assert monitor["communication"]["assessmentId"] == latest_id
    assert monitor["communication"]["status"] == "matches"
    assert any(issue["kind"] == "readback_mismatch" and issue["status"] == "communication_resolved"
               for issue in monitor["issues"])


@pytest.mark.parametrize("mode,reason", [("low_confidence", "low_confidence"), ("error", "decision_error"),
                                         ("unclear", "insufficient_evidence")])
async def test_uncertainty_and_errors_never_become_confident_match_labels(engine, request_body, mode, reason):
    class Uncertain(DecisionClient):
        async def ask(self, state, questions):
            if mode == "error":
                raise TimeoutError("provider unavailable")
            result = await super().ask(state, questions)
            result["answers"]["alignment"].update(choice="matches" if mode == "low_confidence" else "unclear",
                                                  confidence=0.69 if mode == "low_confidence" else 0.9)
            return result

    engine.decider = Uncertain(engine.config)
    session = await running(engine, request_body)
    await engine.advance(session, 5000)
    await settle(session)
    communication = engine.view(session)["monitor"]["communication"]
    assert communication["status"] == "unclear"
    assert communication["reason"] == reason


async def test_corrected_communication_does_not_verify_stale_physical_state(engine, request_body):
    session = await running(engine, request_body, scenarioId="missing-evidence")
    await engine.advance(session, 12000)
    await settle(session)
    monitor = engine.view(session)["monitor"]
    assert monitor["communication"]["status"] == "matches"
    assert any(issue["status"] == "communication_resolved" for issue in monitor["issues"])
    assert monitor["physical"]["status"] == "unverified"
    assert all(monitor["physical"][key] is None for key in ["distanceBeforeHoldM", "speedMps", "runwayEntered"])
    assert any(issue["kind"] == "observation_gap" and issue["status"] == "open" for issue in monitor["issues"])


async def test_matching_words_do_not_hide_movement_and_observed_entry(engine, request_body):
    session = await running(engine, request_body, scenarioId="words-versus-actions", preset="missed")
    await engine.advance(session, 9000)
    await settle(session)
    monitor = engine.view(session)["monitor"]
    assert monitor["communication"]["status"] == "matches"
    assert monitor["physical"]["status"] == "moving"
    assert monitor["physical"]["speedMps"] == 6
    await engine.advance(session, 10000)
    monitor = engine.view(session)["monitor"]
    assert monitor["communication"]["status"] == "matches"
    assert monitor["physical"]["status"] == "runway_entered"
    movement = [issue for issue in monitor["issues"] if issue["kind"] == "movement"]
    assert [issue["status"] for issue in movement] == ["historical", "open"]


async def test_hidden_simulator_truth_cannot_leak_into_monitor_issues(engine, request_body):
    session = await running(engine, request_body, scenarioId="missing-evidence")
    # Deliberately diverge hidden truth from the last permitted observation.
    session.world.update(distanceBeforeHoldM=-10, speedMps=6, runwayEntered=True)
    await engine.advance(session, 7000)
    await settle(session)
    monitor = engine.view(session)["monitor"]
    assert monitor["physical"]["status"] == "unverified"
    assert monitor["physical"]["runwayEntered"] is None
    assert not any(issue["kind"] == "movement" for issue in monitor["issues"])
    observed = [event["payload"] for event in session.events if event["type"] == "monitor_observation"]
    assert all(item["status"] != "runway_entered" for item in observed)


async def test_observation_change_history_is_bounded_and_survives_reload(engine, request_body):
    session = await running(engine, request_body, scenarioId="missing-evidence", preset="complete")
    for _ in range(125):
        await engine.advance(session, 200)
    await settle(session)
    changes = [event for event in session.events if event["type"] == "monitor_observation"]
    assert [event["payload"]["status"] for event in changes] == ["holding", "unverified", "holding"]
    before = copy.deepcopy(engine.view(session)["monitor"])
    await engine.control(session, "pause", "monitor-pause")
    restarted = Engine(engine.config, engine.store, engine.catalog, DecisionClient(engine.config))
    restored = await restarted.get(session.meta["sessionId"], "alice")
    assert engine.view(restored)["monitor"] == before
    assert restored.scenario["version"] == "1"


async def test_restart_reschedules_interrupted_correction_once(engine, request_body, monkeypatch):
    entered = asyncio.Event()

    class InterruptedCorrection(DecisionClient):
        async def ask(self, state, questions):
            if "correction" in questions:
                entered.set()
                await asyncio.Event().wait()
            return await super().ask(state, questions)

    engine.decider = InterruptedCorrection(engine.config)
    session = await running(engine, request_body)
    await engine.advance(session, 9000)
    await entered.wait()
    await engine.shutdown()
    restarted = Engine(engine.config, engine.store, engine.catalog, DecisionClient(engine.config))
    restored = await restarted.get(session.meta["sessionId"], "alice")
    monkeypatch.setattr(restarted, "_launch", lambda _: None)
    await restarted.control(restored, "resume", "resume-monitor")
    restarted._recover_checks(restored)  # Same turn: no pending row has been written yet.
    await settle(restored)
    corrections = [a for a in restored.assessments if a["assessmentType"] == "correction"]
    assert [a["processingStatus"] for a in corrections].count("completed") == 1
    assert [a["processingStatus"] for a in corrections].count("error") == 1
    await restarted.advance(restored, 3000)
    await settle(restored)
    assert restarted.view(restored)["monitor"]["issues"][0]["status"] == "communication_resolved"


async def test_primary_radio_checks_overtake_queued_advisory_checks_without_parallel_inference(config):
    client = DecisionClient(config)
    entered, release, order = asyncio.Event(), asyncio.Event(), []
    active = 0

    async def request(label, primary, blocked=False):
        nonlocal active
        async with client._turn(primary):
            active += 1
            assert active == 1
            order.append(label)
            if blocked:
                entered.set()
                await release.wait()
            active -= 1

    first = asyncio.create_task(request("active", False, True))
    await entered.wait()
    advisory = asyncio.create_task(request("advisory", False))
    primary = asyncio.create_task(request("radio", True))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, advisory, primary)
    assert order == ["active", "radio", "advisory"]


async def test_live_advisory_is_bounded_does_not_finish_session_and_usage_accumulates(engine, request_body, monkeypatch):
    phases = []

    async def assistant(config, capture, publish, trace_start, trace_finish, usage, phase):
        phases.append(phase)
        await capture()
        await usage({"inputTokens": 10, "outputTokens": 2, "totalTokens": 12})

    monkeypatch.setattr("clearance_gap.engine.run_instructor", assistant)
    # Use explicit fixture decisions with a live-mode coordinator; no AWS calls.
    engine.decider = DecisionClient(engine.config.model_copy())
    engine.config.provider_mode = "live"
    session = await running(engine, request_body)
    await engine.advance(session, 5000)
    await settle(session)
    await session.advisory_task
    assert phases == ["live"]
    assert session.meta["status"] == "running" and not session.meta["simulationFinished"]
    await engine.advance(session, 25000)
    await settle(session)
    await engine.finalize(session)
    assert phases == ["live", "final"]
    assert session.meta["bedrockUsage"] == {"inputTokens": 20, "outputTokens": 4, "totalTokens": 24}
    assert session.meta["assessmentStatus"] == "needs_review"  # Neither invocation published a checked advisory.


async def test_advisory_failures_are_recorded_and_paused_advisory_holds_admission(engine, request_body, monkeypatch):
    async def failing(*args, **kwargs):
        raise RuntimeError("test provider error")

    monkeypatch.setattr("clearance_gap.engine.run_instructor", failing)
    session = await running(engine, request_body)
    await engine._run_assistant(session, "live")
    assert session.meta["status"] == "running"
    assert engine.view(session)["bedrockUsageIncomplete"] is True
    assert any(trace["status"] == "error" and trace["title"] == "Assistant execution failed" for trace in session.traces)
    session.meta["status"] = "paused"
    session.advisory_task = asyncio.create_task(asyncio.Event().wait())
    other = await engine.create("bob", request_body, "second-monitor-session")
    with pytest.raises(LimitExceeded):
        await engine.control(other, "start", "second-start")
    await engine.shutdown()
    assert session.advisory_task.cancelled()


async def test_version_two_creation_and_version_one_pinned_reload_are_independent(engine, request_body):
    new = await engine.create("alice", request_body | {"scenarioVersion": "2"}, "version-two")
    assert new.meta["scenarioRef"]["key"].endswith("/v2/scenario.json")
    old = await engine.create("alice", request_body, "version-one")
    restarted = Engine(engine.config, engine.store, engine.catalog, engine.decider)
    restored = await restarted.get(old.meta["sessionId"], "alice")
    assert restored.scenario["version"] == "1"
    assert restored.scenario["durationMs"] != new.scenario["durationMs"]
