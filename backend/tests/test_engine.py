import asyncio

import pytest

from clearance_gap.decisions import DecisionClient
from clearance_gap.engine import Engine
from clearance_gap.store import Conflict


async def start_without_clock(engine, session):
    await engine.control(session, "start", "start-request")
    session.runner.cancel()
    await asyncio.gather(session.runner, return_exceptions=True)


@pytest.mark.parametrize("scenario", ["incorrect-readback", "words-versus-actions", "missing-evidence"])
@pytest.mark.parametrize("preset", ["missed", "partial", "complete"])
async def test_automatic_run_preserves_events_and_physical_truth(engine, request_body, scenario, preset):
    body = {**request_body, "scenarioId": scenario, "preset": preset}
    session = await engine.create("alice", body, f"create-{scenario}-{preset}")
    await start_without_clock(engine, session)
    await engine.advance(session, 30000)
    await asyncio.gather(*list(session.model_tasks))
    await engine.finalize(session)
    assert session.meta["status"] == "completed"
    assert session.world["runwayEntered"] == (scenario == "words-versus-actions" and preset == "missed")
    assert [e["sequence"] for e in session.events] == list(range(1, len(session.events) + 1))
    if scenario != "words-versus-actions":
        assert any("Lining up" in e["payload"].get("text", "") for e in session.events)
    assert any(e["type"] == "instructor_feedback" for e in session.events)
    assert session.meta["assessmentStatus"] == "completed"
    if preset == "partial":
        assert any(a.get("decisionOutput", {}).get("choice") == "insufficient_evidence"
                   for a in session.assessments)
        assert all("completed the recovery" not in e["payload"].get("text", "")
                   for e in session.events if e["type"] == "instructor_feedback")
    if scenario == "missing-evidence" and preset != "complete":
        assert engine.observation(session)["status"] == "stale"
        expected_guard = "insufficient_evidence" if preset == "partial" else "contradicted"
        assert any(a.get("decisionOutput", {}).get("choice") == expected_guard
                   for a in session.assessments)
    records = engine.store.partition(f"SESSION#{session.meta['sessionId']}")
    assert len([r for r in records if r["SK"].startswith("EVENT#")]) == len(session.events)
    # The original and corrected readbacks remain separate append-only evidence.
    if preset != "missed":
        readbacks = [e for e in session.events if e["type"] == "pilot_readback"]
        assert len(readbacks) == 2


async def test_creation_retry_is_owner_scoped_and_payload_checked(engine, request_body):
    first, second = await asyncio.gather(engine.create("alice", request_body, "same-request"),
                                         engine.create("alice", request_body, "same-request"))
    assert first.meta["sessionId"] == second.meta["sessionId"]
    with pytest.raises(Conflict):
        await engine.create("alice", {**request_body, "preset": "missed"}, "same-request")
    other = await engine.create("bob", request_body, "same-request")
    assert other.meta["sessionId"] != first.meta["sessionId"]
    with pytest.raises(PermissionError):
        await engine.get(first.meta["sessionId"], "bob")


async def test_recovery_keeps_pending_actions_and_original_world(engine, request_body):
    session = await engine.create("alice", {**request_body, "scenarioId": "words-versus-actions"}, "recover-request")
    await start_without_clock(engine, session)
    await engine.advance(session, 10000)
    await asyncio.gather(*list(session.model_tasks))
    distance = session.world["distanceBeforeHoldM"]
    # Explicit pause checkpoints the live continuation state.
    await engine.control(session, "pause", "pause-request")
    restarted = Engine(engine.config, engine.store, engine.catalog, engine.decider)
    loaded = await restarted.get(session.meta["sessionId"], "alice")
    assert loaded.meta["status"] == "paused"
    assert loaded.world["distanceBeforeHoldM"] == distance
    assert "movement-fault" in loaded.processed
    await restarted.control(loaded, "resume", "resume-request")
    loaded.runner.cancel()
    await asyncio.gather(loaded.runner, return_exceptions=True)
    await restarted.advance(loaded, 20000)
    await asyncio.gather(*list(loaded.model_tasks))
    assert loaded.world["speedMps"] == 0
    assert loaded.world["distanceBeforeHoldM"] >= 0
    assert len([e for e in loaded.events if e["payload"].get("scriptStepId") == "movement-fault"]) == 1


async def test_new_correction_invalidates_feedback_while_guard_is_running(engine, request_body):
    session = await engine.create("alice", request_body, "stale-request")
    await start_without_clock(engine, session)
    await engine.advance(session, 5000)
    await asyncio.gather(*list(session.model_tasks))
    evidence = await engine.capture(session)
    ready, release = asyncio.Event(), asyncio.Event()

    class DelayedGuard(DecisionClient):
        async def ask(self, state, questions):
            if "grounding" in questions:
                ready.set()
                await release.wait()
            result = await super().ask(state, questions)
            if "grounding" in questions:
                result["answers"]["grounding"].update(choice="supported", confidence=1)
            if "coaching" in questions:
                result["answers"]["coaching"].update(score=2, confidence=1)
            return result

    engine.decider = DelayedGuard(engine.config)
    publishing = asyncio.create_task(engine.publish(session, "The readback requires correction.", evidence))
    await ready.wait()
    await engine.advance(session, 5000)
    release.set()
    result = await publishing
    await asyncio.gather(*list(session.model_tasks))
    assert not result["published"]
    assert "changed" in result["reason"]
    assert not any(e["type"] == "instructor_feedback" for e in session.events)


async def test_model_failure_is_recorded_without_a_fabricated_verdict(engine, request_body):
    class Broken:
        async def ask(self, state, questions):
            raise TimeoutError("model unavailable")

    session = await engine.create("alice", request_body, "failure-request")
    engine.decider = Broken()
    evidence = await engine.capture(session)
    result = await engine.evaluate(session, "grounding", {**evidence, "candidate_feedback": "Recovery complete"}, [])
    assert result["processingStatus"] == "error"
    assert "decisionOutput" not in result
    assert not any(e["type"] == "instructor_feedback" for e in session.events)


async def test_pause_control_retries_do_not_append_another_event(engine, request_body):
    session = await engine.create("alice", request_body, "pause-create-request")
    await start_without_clock(engine, session)
    await engine.control(session, "pause", "pause-idempotency")
    count = len(session.events)
    await engine.control(session, "pause", "pause-idempotency")
    assert len(session.events) == count
    with pytest.raises(Conflict):
        await engine.control(session, "resume", "pause-idempotency")


async def test_provider_modes_cannot_be_mixed_when_starting_a_saved_session(engine, request_body):
    session = await engine.create("alice", request_body, "provider-mode-check")
    engine.config.provider_mode = "live"
    with pytest.raises(Conflict, match="different provider mode"):
        await engine.control(session, "start", "live-start-check")
    assert session.meta["status"] == "ready"
