"""Current monitoring view projected from durable evidence, never hidden simulator truth."""
from datetime import datetime

ALIGNMENT_CONFIDENCE = 0.7


def radio_ref(event):
    if event is None:
        return None
    return {"eventId": event["eventId"], "text": event["payload"].get("text", ""),
            "simulationTimeMs": event["simulationTimeMs"]}


def latest_assessment(assessments, kind, event_id):
    candidates = [a for a in assessments if a["assessmentType"] == kind
                  and event_id in a.get("evidenceRefs", {}).get("eventIds", [])]
    return max(candidates, key=lambda a: a.get("startedAt", ""), default=None)


def alignment_status(assessment):
    if not assessment or assessment["processingStatus"] == "pending":
        return "checking", "awaiting_decision"
    if assessment["processingStatus"] != "completed":
        return "unclear", "decision_error"
    answer = assessment.get("decisionOutput", {})
    if answer.get("confidence", 0) < ALIGNMENT_CONFIDENCE:
        return "unclear", "low_confidence"
    return {"matches": ("matches", "aligned_readback"),
            "contradicts": ("mismatch", "conflicting_readback")}.get(answer.get("choice"), ("unclear", "insufficient_evidence"))


def physical_view(observation):
    status = "unverified"
    if observation["status"] == "current":
        if observation["runwayEntered"]:
            status = "runway_entered"
        elif observation["speedMps"] > 0:
            status = "moving"
        else:
            status = "holding"
    title, detail = {
        "unverified": ("Current position unverified", "The last observation is stale. Obtain a fresh observation before verifying the aircraft response."),
        "holding": ("Observed stopped before holding point", "This observation describes the aircraft at the recorded time; readback alignment is a separate check."),
        "moving": ("Movement needs review", "The available observation shows movement toward the holding point. A matching readback alone does not establish the aircraft response."),
        "runway_entered": ("Observed runway entry", "Runway entry is present in the available simulator observation. Review it against the controller instruction."),
    }[status]
    return {"status": status, "title": title, "detail": detail,
            "observedAtMs": observation["observedAtMs"], "ageMs": observation["ageMs"],
            "distanceBeforeHoldM": observation["distanceBeforeHoldM"] if status != "unverified" else None,
            "speedMps": observation["speedMps"] if status != "unverified" else None,
            "runwayEntered": observation["runwayEntered"] if status != "unverified" else None,
            "source": "simulator"}


def monitor_view(session, observation):
    events = sorted(session.events, key=lambda event: event["sequence"])
    radio = [event for event in events if event["type"] in {"trainee_instruction", "pilot_readback"}]
    instruction = next((e for e in reversed(radio) if e["type"] == "trainee_instruction"), None)
    readback = next((e for e in reversed(radio) if e["type"] == "pilot_readback"
                     and instruction and e["sequence"] > instruction["sequence"]), None)
    assessment = latest_assessment(session.assessments, "alignment", readback["eventId"]) if readback else None
    status, reason = alignment_status(assessment) if readback else (
        ("checking", "awaiting_readback") if instruction else ("waiting", "awaiting_exchange"))
    title, detail = {
        "waiting": ("Waiting for the exchange", "The controller and pilot messages will appear automatically."),
        "checking": ("Checking the latest exchange", "A current comparison is not available yet."),
        "matches": ("Readback matches", "The latest readback matches the controller instruction. Aircraft response is assessed separately."),
        "mismatch": ("Possible readback mismatch", "The readback changes the instructed action or runway. Awaiting controller review and correction."),
        "unclear": ("Readback needs review", "The available decision does not support a confident comparison. Review the two messages."),
    }[status]
    if reason == "awaiting_readback":
        title, detail = "Awaiting pilot readback", "A new controller instruction supersedes the previous comparison."
    if reason == "decision_error":
        detail = "The decision could not be completed. No match or mismatch is confirmed."
    latency = None
    if readback and assessment and assessment.get("endedAt"):
        try:
            latency = round(max(0, (datetime.fromisoformat(assessment["endedAt"]) -
                                    datetime.fromisoformat(readback["recordedAt"])).total_seconds() * 1000), 2)
        except (ValueError, TypeError):
            pass
    communication = {
        "status": status, "title": title, "detail": detail, "reason": reason,
        "instruction": radio_ref(instruction), "readback": radio_ref(readback),
        "assessmentId": assessment.get("assessmentId") if assessment else None,
        "confidence": assessment.get("decisionOutput", {}).get("confidence") if assessment else None,
        "roundTripMs": assessment.get("roundTripMs") if assessment else None,
        "alertLatencyMs": latency,
        "evidenceEventIds": [event["eventId"] for event in [instruction, readback] if event],
    }
    issues = []
    for event in radio:
        if event["type"] != "pilot_readback":
            continue
        result = latest_assessment(session.assessments, "alignment", event["eventId"])
        result_status, _ = alignment_status(result)
        if result_status not in {"mismatch", "unclear"}:
            continue
        resolution = None
        for later in radio:
            if later["type"] != "pilot_readback" or later["sequence"] <= event["sequence"]:
                continue
            later_result = latest_assessment(session.assessments, "alignment", later["eventId"])
            correction = next((e for e in reversed(radio) if e["type"] == "trainee_instruction"
                               and event["sequence"] < e["sequence"] < later["sequence"]), None)
            correction_result = latest_assessment(session.assessments, "correction", correction["eventId"]) if correction else None
            if (alignment_status(later_result)[0] == "matches" and correction_result
                    and correction_result["processingStatus"] == "completed"
                    and correction_result.get("decisionOutput", {}).get("noul", 0) >= ALIGNMENT_CONFIDENCE):
                resolution = later
                break
        issues.append({"id": f"readback:{event['eventId']}",
                       "kind": "readback_mismatch" if result_status == "mismatch" else "readback_unclear",
                       "status": "communication_resolved" if resolution else "open",
                       "title": "Possible readback mismatch" if result_status == "mismatch" else "Uncertain readback comparison",
                       "detail": "A later explicit correction has a matching readback. Physical response remains a separate check." if resolution else "This comparison remains in the recorded issue history for controller review.",
                       "detectedAtMs": result.get("completedAtSimulationTimeMs", event["simulationTimeMs"]),
                       "evidenceEventIds": result.get("evidenceRefs", {}).get("eventIds", []),
                       "assessmentId": result["assessmentId"],
                       "resolvedByEventId": resolution["eventId"] if resolution else None})
    physical = physical_view(observation)
    observed_events = [e for e in events if e["type"] == "monitor_observation"]
    for event in observed_events:
        observed = event["payload"]
        if observed["status"] == "holding":
            continue
        latest = event is observed_events[-1] and observed["status"] == physical["status"]
        issues.append({"id": f"observation:{event['eventId']}",
                       "kind": "observation_gap" if observed["status"] == "unverified" else "movement",
                       "status": "open" if latest else "historical", "title": observed["title"], "detail": observed["detail"],
                       "detectedAtMs": event["simulationTimeMs"], "evidenceEventIds": [event["eventId"]],
                       "assessmentId": None, "resolvedByEventId": None})
    if not observed_events and physical["status"] != "holding":
        # Older saved sessions have no observation-category events. Their current
        # allowed observation is enough for a current issue, not invented history.
        issues.append({"id": "current-observation", "kind": "observation_gap" if physical["status"] == "unverified" else "movement",
                       "status": "open", "title": physical["title"], "detail": physical["detail"],
                       "detectedAtMs": session.meta["simulationTimeMs"], "evidenceEventIds": [],
                       "assessmentId": None, "resolvedByEventId": None})
    advisory = None
    feedback = next((e for e in reversed(events) if e["type"] == "instructor_feedback"), None)
    if feedback:
        payload = feedback["payload"]
        newer = any(e["sequence"] > payload.get("evidenceSequence", 0) and e["type"] in
                    {"trainee_instruction", "pilot_readback", "trainee_observation_check", "runway_entered"} for e in events)
        previous = payload.get("evidenceObservation", {})
        current = bool(previous) and not newer and all(previous.get(key) == observation[key] for key in
                                                       ["status", "distanceBeforeHoldM", "speedMps", "runwayEntered"])
        advisory = {"eventId": feedback["eventId"], "text": payload["text"], "phase": payload.get("phase", "final"),
                    "isCurrent": current, "evidenceSequence": payload.get("evidenceSequence", 0),
                    "simulationTimeMs": feedback["simulationTimeMs"]}
    return {"communication": communication, "physical": physical, "issues": issues, "advisory": advisory}
