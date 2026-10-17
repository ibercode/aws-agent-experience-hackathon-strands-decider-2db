import asyncio
import copy
from types import SimpleNamespace

import pytest

from clearance_gap.engine import Engine
from clearance_gap.instructor import run_instructor


class Supported:
    async def ask(self, state, questions):
        name = next(iter(questions))
        answer = {"type": "score", "score": 2, "confidence": 0.5} if name == "coaching" else {
            "type": "choice", "choice": "supported", "confidence": 0.9}
        return {"model": "test-double", "answers": {name: answer}, "roundTripMs": 1}


async def publish_live(engine, request_body):
    session = await engine.create("alice", request_body, "final-selection")
    session.meta["status"] = "running"
    await engine.advance(session, session.scenario["durationMs"])
    await asyncio.gather(*list(session.model_tasks))
    engine.decider = Supported()
    await engine.publish(session, "ignored", await engine.capture(session), phase="live",
                         findings=[{"text": "No controller verification check was recorded.",
                                    "evidence_keys": ["trainee_check_record"]}],
                         next_action="Inspect AIR123's position and speed relative to the holding point and record the observation.")
    return session


async def test_current_guarded_live_advisory_is_selected_without_new_inference_and_survives_reload(engine, request_body, monkeypatch):
    session = await publish_live(engine, request_body)
    original = copy.deepcopy(next(e for e in session.events if e["type"] == "instructor_feedback"))
    assessments, traces, usage = len(session.assessments), len(session.traces), session.meta["bedrockUsage"]

    async def unexpected(*args, **kwargs):
        pytest.fail("A current guarded advisory must not trigger another model invocation")

    monkeypatch.setattr(engine, "_run_assistant", unexpected)
    await engine.finalize(session)
    await engine.finalize(session)  # Selecting a completed result is idempotent.
    assert session.meta["assessmentStatus"] == "completed"
    assert len(session.assessments) == assessments and len(session.traces) == traces
    assert session.meta["bedrockUsage"] == usage
    assert [e for e in session.events if e["type"] == "instructor_feedback"] == [original]
    selection = [e for e in session.events if e["type"] == "assistant_final_advisory"]
    assert len(selection) == 1
    assert selection[0]["payload"] == {"advisoryEventId": original["eventId"], "sourcePhase": "live", "reused": True}
    restarted = Engine(engine.config, engine.store, engine.catalog, engine.decider)
    restored = await restarted.get(session.meta["sessionId"], "alice")
    assert engine.view(restored)["monitor"] == engine.view(session)["monitor"]
    restored_selection = next(e for e in restored.events if e["type"] == "assistant_final_advisory")
    assert restored_selection["eventId"] == selection[0]["eventId"]
    assert restored_selection["payload"] == selection[0]["payload"]


@pytest.mark.parametrize("change", ["radio", "movement", "stale_observation", "legacy_without_evidence"])
async def test_outdated_advisory_requires_final_generation_and_cannot_mark_success(engine, request_body, monkeypatch, change):
    session = await publish_live(engine, request_body)
    if change == "radio":
        engine._append_event(session, "trainee_instruction", "trainee", {"text": "AIR123, stop immediately."})
    elif change == "movement":
        session.world["lastObservation"]["speedMps"] = 6
    elif change == "stale_observation":
        session.world["lastObservation"]["observedAtMs"] = 0
    else:
        next(e for e in session.events if e["type"] == "instructor_feedback")["payload"].pop("evidenceObservation")
    calls = []

    async def withheld(current, phase):
        calls.append(phase)

    monkeypatch.setattr(engine, "_run_assistant", withheld)
    await engine.finalize(session)
    assert calls == ["final"]
    assert session.meta["assessmentStatus"] == "needs_review"
    assert not any(e["type"] == "assistant_final_advisory" for e in session.events)
    assert not session.events[-1]["payload"]["feedbackPublished"]


async def test_agent_stops_after_two_repeated_rejections_without_publishing(config, monkeypatch):
    attempts, traces = [], []

    class Agent:
        def __init__(self, **kwargs):
            self.tool = next(t for t in kwargs["tools"] if t.tool_name == "present_feedback")
            self.hook = kwargs["hooks"][0]
            self.event_loop_metrics = SimpleNamespace(accumulated_usage={})

        async def invoke_async(self, prompt, limits):
            for _ in range(limits["turns"]):
                await self.tool(findings=[{"text": "Rejected compound fact.", "evidence_keys": ["source"]}],
                                next_action="Inspect AIR123's position.")
                event = SimpleNamespace(end_turn=False)
                await self.hook.end_after_publication(event)
                if event.end_turn:
                    return
            pytest.fail("Duplicate rejected proposals did not terminate the invocation")

    async def capture():
        return {}

    async def publish(*args, **kwargs):
        attempts.append(kwargs)
        return {"published": False, "reusedAssessment": len(attempts) > 1}

    async def start(actor, title, inputs):
        traces.append(title)
        return "trace"

    async def finish(*args, **kwargs):
        pass

    async def usage(*args, **kwargs):
        pass

    monkeypatch.setattr("strands.Agent", Agent)
    monkeypatch.setattr("strands.models.BedrockModel", lambda **kwargs: object())
    monkeypatch.setattr("clearance_gap.instructor.boto3.Session", lambda **kwargs: object())
    config.provider_mode = "live"
    await run_instructor(config, capture, publish, start, finish, usage)
    assert len(attempts) == 3
    assert "Advisory withheld" in traces
