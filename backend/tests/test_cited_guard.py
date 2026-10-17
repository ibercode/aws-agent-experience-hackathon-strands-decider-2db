import pytest

from clearance_gap.decisions import evidence_catalog


class DecisionStub:
    def __init__(self, verdict="supported", confidence=0.95):
        self.calls = []
        self.verdict = verdict
        self.confidence = confidence

    async def ask(self, state, questions):
        self.calls.append((state, questions))
        name = next(iter(questions))
        answer = {"type": "score", "score": 1.6, "confidence": 0.25} if name == "coaching" else {
            "type": "choice", "choice": self.verdict, "confidence": self.confidence}
        return {"model": "unit-test-double", "answers": {name: answer}, "roundTripMs": 0.1}


async def test_only_cited_real_sources_reach_the_guard_and_only_checked_findings_are_published(engine, request_body):
    session = await engine.create("alice", request_body, "cited-source-test")
    evidence = await engine.capture(session)
    decider = DecisionStub()
    engine.decider = decider
    finding = {"text": "No controller verification check was recorded.", "evidence_keys": ["trainee_check_record"]}
    action = "Check the current aircraft position and record the observation."
    result = await engine.publish(session, "Unchecked caller text must not be displayed.", evidence,
                                  findings=[finding], next_action=action)
    assert result["published"]
    assert decider.calls[0][0] == {"evidence": "No controller verification check was recorded.", "statement": finding["text"]}
    assert decider.calls[1][0] == action
    feedback = next(e for e in session.events if e["type"] == "instructor_feedback")
    assert feedback["payload"]["text"] == finding["text"] + " " + action
    assert feedback["payload"]["guardAssessmentIds"]


@pytest.mark.parametrize("verdict,confidence", [("supported", 0.3), ("contradicted", 0.99)])
async def test_uncertain_or_contradicted_findings_are_blocked_before_quality_scoring(engine, request_body, verdict, confidence):
    session = await engine.create("alice", request_body, "blocked-cited-source")
    evidence = await engine.capture(session)
    engine.decider = DecisionStub(verdict, confidence)
    result = await engine.publish(session, "A check was recorded.", evidence,
                                  findings=[{"text": "A check was recorded.", "evidence_keys": ["trainee_check_record"]}],
                                  next_action="Check the aircraft position.")
    assert not result["published"]
    assert len(engine.decider.calls) == 1
    assert not any(e["type"] == "instructor_feedback" for e in session.events)
    assert any(t.get("output", {}).get("published") is False for t in session.traces)


async def test_identical_rejected_finding_does_not_rerun_guards_for_the_proposal(engine, request_body):
    session = await engine.create("alice", request_body, "repeated-rejection")
    engine.decider = DecisionStub(confidence=0.63)
    finding = {"text": "The controller issued a correction and the pilot read back holding short.",
               "evidence_keys": ["correction_record"]}
    first = await engine.publish(session, "ignored", await engine.capture(session),
                                 findings=[finding], next_action="Check AIR123's position.")
    assert first["reason"] == "low_confidence"
    prior_calls = len(engine.decider.calls)
    # A new capture/snapshot and changed advice do not change this finding's sources.
    repeated = await engine.publish(session, "ignored", await engine.capture(session),
                                    findings=[{"text": "No check was recorded.", "evidence_keys": ["trainee_check_record"]}, finding],
                                    next_action="Inspect AIR123's position and record the observation.")
    assert repeated["reason"] == "repeated_rejected_finding" and repeated["reusedAssessment"]
    assert repeated["assessmentId"] == first["assessmentId"]
    assert len(engine.decider.calls) == prior_calls
    assert "split" in repeated["instruction"] and "Omit" in repeated["instruction"]
    assert not any(event["type"] == "instructor_feedback" for event in session.events)
    # Identical wording with different cited evidence still gets a real decision.
    await engine.publish(session, "ignored", await engine.capture(session),
                         findings=[{**finding, "evidence_keys": ["aircraft_observation"]}],
                         next_action="Check AIR123's position.")
    assert len(engine.decider.calls) == prior_calls + 1


async def test_invented_source_key_cannot_be_used_as_evidence(engine, request_body):
    session = await engine.create("alice", request_body, "invented-cited-source")
    engine.decider = DecisionStub()
    result = await engine.publish(session, "A check was recorded.", await engine.capture(session),
                                  findings=[{"text": "A check was recorded.", "evidence_keys": ["invented_source"]}],
                                  next_action="Check the aircraft position.")
    assert not result["published"]
    assert engine.decider.calls == []


def test_stale_source_card_does_not_present_historical_coordinates_as_current():
    state = {"events": [], "observation": {"status": "stale", "distanceBeforeHoldM": 50, "speedMps": 0},
             "correctionRecorded": True, "traineeVerificationRecorded": False}
    source = evidence_catalog(state)["aircraft_observation"]
    assert "unknown" in source
    assert "50" not in source
    assert "stopped" not in source


async def test_observed_distance_cannot_become_an_advice_requirement(engine, request_body):
    session = await engine.create("alice", request_body, "distance-is-not-rule")
    engine.decider = DecisionStub()
    result = await engine.publish(session, "No check was recorded.", await engine.capture(session),
                                  findings=[{"text": "No controller verification check was recorded.", "evidence_keys": ["trainee_check_record"]}],
                                  next_action="Check that AIR123 is at least 50 metres before the holding point.")
    assert not result["published"]
    assert engine.decider.calls == []


async def test_observation_advice_addressed_to_the_trainee_still_reaches_decider(engine, request_body):
    session = await engine.create("alice", request_body, "delegated-observation-check")
    session.meta["status"] = "running"
    await engine.advance(session, 2000)  # Record the scenario's runway identifier.
    engine.decider = DecisionStub()
    # Actual Nova wording that previously exhausted every retry before Decider ran.
    action = "Instruct the trainee to inspect AIR123’s current position and speed relative to runway 27’s holding point and record the observation."
    finding = {"text": "No controller verification check was recorded.", "evidence_keys": ["trainee_check_record"]}
    result = await engine.publish(session, finding["text"] + " " + action, await engine.capture(session),
                                  findings=[finding], next_action=action)
    assert result["published"]
    assert [next(iter(questions)) for _, questions in engine.decider.calls] == ["grounding", "coaching"]
    assert engine.decider.calls[1][0] == action
    feedback = next(event for event in session.events if event["type"] == "instructor_feedback")
    assert feedback["payload"]["nextAction"] == action


@pytest.mark.parametrize("action,reason", [
    ("Instruct the trainee to ", "observation or debrief verb"),
    ("Instruct the pilot to line up on the runway.", "observation or debrief verb"),
    ("Instruct the trainee to line up AIR123 on the runway.", "observation or debrief verb"),
    ("Instruct the trainee to clear AIR123 to enter the runway.", "observation or debrief verb"),
    ("Instruct the trainee to inspect that AIR123 stays at least 50 metres before the holding point.",
     "unsupported numerical requirement"),
])
async def test_trainee_wrapper_does_not_allow_movement_advice_or_invented_buffers(engine, request_body, action, reason):
    session = await engine.create("alice", request_body, "blocked-delegated-action")
    engine.decider = DecisionStub()
    finding = {"text": "No controller verification check was recorded.", "evidence_keys": ["trainee_check_record"]}
    result = await engine.publish(session, finding["text"] + " " + action, await engine.capture(session),
                                  findings=[finding], next_action=action)
    assert not result["published"]
    assert reason in result["reason"]
    assert engine.decider.calls == []
    assert not any(event["type"] == "instructor_feedback" for event in session.events)
