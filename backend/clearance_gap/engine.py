import asyncio
import copy
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .async_utils import SettledCancellation, settle_before_cancel
from .catalog import scenario_setup
from .decisions import ALIGNMENT, COACHING, CORRECTION, GROUNDING, decision_state, evidence_catalog
from .instructor import run_instructor
from .monitor import monitor_view, physical_view
from .store import Conflict, LimitExceeded, digest


def now():
    return datetime.now(UTC).isoformat()


def identifier(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@dataclass
class Session:
    meta: dict
    scenario: dict
    world: dict
    events: list = field(default_factory=list)
    assessments: list = field(default_factory=list)
    traces: list = field(default_factory=list)
    processed: set = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    model_tasks: set = field(default_factory=set)
    runner: asyncio.Task | None = None
    finalizer: asyncio.Task | None = None
    advisory_task: asyncio.Task | None = None
    scheduled_checks: set = field(default_factory=set)
    advisory_attempted: bool = False


class Engine:
    def __init__(self, config, store, catalog, decider):
        self.config, self.store, self.catalog, self.decider = config, store, catalog, decider
        self.sessions = {}
        self.load_lock = asyncio.Lock()
        # One deployed coordinator owns the simulator clock and admission limit.
        self.admission_lock = asyncio.Lock()

    async def create(self, owner, request, request_id):
        receipt_pk, receipt_sk = f"USER#{owner}", f"REQUEST#CREATE_SESSION#{request_id}"
        fingerprint = digest(request)
        existing = await asyncio.to_thread(self.store.get, receipt_pk, receipt_sk)
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise Conflict("This request ID was already used with different settings")
            return await self.get(existing["sessionId"], owner)
        scenario, ref = await asyncio.to_thread(self.catalog.load, request["scenarioId"], None, request["scenarioVersion"])
        if request["scenarioVersion"] != scenario["version"]:
            raise ValueError("Scenario version is not available")
        session_id, created = identifier("session"), now()
        meta = dict(sessionId=session_id, traineeId=owner, scenarioId=scenario["id"],
                    scenarioVersion=scenario["version"], scenarioRef=ref, preset=request["preset"],
                    playback=request["playback"], status="ready", createdAt=created, updatedAt=created,
                    startedAt=None, endedAt=None, simulationTimeMs=0, simulationFinished=False,
                    revision=1, lastEventSequence=1, latestSnapshotVersion=0,
                    providerMode=self.config.provider_mode, bedrockUsage=None,
                    bedrockUsageIncomplete=False, assessmentStatus="pending")
        world = dict(distanceBeforeHoldM=scenario["initialDistanceM"], speedMps=0.0, runwayEntered=False,
                     motionPlan="hold", observationAvailable=not scenario["observationGap"],
                     lastObservation=dict(distanceBeforeHoldM=scenario["initialDistanceM"], speedMps=0.0,
                                          runwayEntered=False, observedAtMs=0))
        session = Session(meta, scenario, world)
        event = self._event(session, "session_created", "system", {"source": "scripted_demo"}, 1)
        session.events.append(event)
        receipt = dict(PK=receipt_pk, SK=receipt_sk, sessionId=session_id, fingerprint=fingerprint)
        try:
            await asyncio.to_thread(self.store.commit, meta,
                                    [event, self._snapshot(session)], None, receipt)
        except Conflict:
            existing = await asyncio.to_thread(self.store.get, receipt_pk, receipt_sk)
            if not existing or existing["fingerprint"] != fingerprint:
                raise
            return await self.get(existing["sessionId"], owner)
        self.sessions[session_id] = session
        return session

    async def get(self, session_id, owner):
        async with self.load_lock:
            return await self._get(session_id, owner)

    async def _get(self, session_id, owner):
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if session.meta["traineeId"] != owner:
                raise PermissionError("Session belongs to another user")
            return session
        items = await asyncio.to_thread(self.store.partition, f"SESSION#{session_id}")
        header = next((r for r in items if r["SK"] == "META"), None)
        if not header:
            raise KeyError(session_id)
        if header["traineeId"] != owner:
            raise PermissionError("Session belongs to another user")
        scenario, ref = await asyncio.to_thread(self.catalog.load, header["scenarioId"], header["scenarioRef"])
        if ref["sha256"] != header["scenarioRef"]["sha256"]:
            raise Conflict("Pinned scenario content changed; restore its original version before resuming")
        snapshot = next(r for r in items if r["SK"] == f"SNAPSHOT#{int(header['latestSnapshotVersion']):010d}")
        session = Session(header, scenario, snapshot["worldState"],
                          [r for r in items if r["SK"].startswith("EVENT#")],
                          [r for r in items if r["SK"].startswith("ASSESSMENT#")],
                          [r for r in items if r["SK"].startswith("TRACE#")],
                          set(snapshot["continuationState"]["processedScriptSteps"]))
        self.sessions[session_id] = session
        if header["status"] in {"running", "paused"}:
            async with session.lock:
                session.meta["status"] = "paused"
                updates = []
                for item in [*session.assessments, *session.traces]:
                    if item.get("processingStatus", item.get("status")) in {"pending", "running"}:
                        item.update(error="Backend restarted; this execution was interrupted", endedAt=now())
                        item["processingStatus" if "processingStatus" in item else "status"] = "error"
                        updates.append(item)
                event = self._append_event(session, "session_recovered", "system", {"status": "paused"})
                await self._commit(session, [event, *updates], checkpoint=True)
        return session

    def _snapshot(self, session):
        meta = session.meta
        return dict(SK=f"SNAPSHOT#{int(meta['latestSnapshotVersion']):010d}",
                    snapshotVersion=meta["latestSnapshotVersion"], simulationTimeMs=meta["simulationTimeMs"],
                    lastEventSequence=meta["lastEventSequence"], worldState=copy.deepcopy(session.world),
                    continuationState={"processedScriptSteps": sorted(session.processed)},
                    simulatorVersion="0.1.0", savedAt=now())

    def _event(self, session, kind, actor, payload, sequence):
        return dict(SK=f"EVENT#{sequence:010d}", eventId=f"{session.meta['sessionId']}:{sequence}",
                    sequence=sequence, simulationTimeMs=session.meta["simulationTimeMs"], recordedAt=now(),
                    type=kind, actor=actor, payload=copy.deepcopy(payload))

    def _append_event(self, session, kind, actor, payload):
        session.meta["lastEventSequence"] += 1
        event = self._event(session, kind, actor, payload, session.meta["lastEventSequence"])
        session.events.append(event)
        return event

    async def _commit(self, session, updates, checkpoint=False, receipt=None, run_quota=None):
        revision = session.meta["revision"]
        meta = {**session.meta, "revision": revision + 1, "updatedAt": now()}
        if checkpoint:
            meta["latestSnapshotVersion"] += 1
        previous = session.meta
        session.meta = meta
        records = list(updates)
        if checkpoint:
            records.append(self._snapshot(session))
        try:
            await settle_before_cancel(asyncio.to_thread(self.store.commit, meta, records, revision, receipt, run_quota))
        except SettledCancellation:
            # The store committed while cancellation was deferred. Keep its
            # revision in memory so shutdown can persist the next checkpoint.
            raise
        except BaseException:
            session.meta = previous
            raise

    async def control(self, session, operation, request_id):
        async with self.admission_lock:
            await self._control(session, operation, request_id)

    async def _control(self, session, operation, request_id):
        async with session.lock:
            if operation in {"start", "resume"} and session.meta["providerMode"] != self.config.provider_mode:
                raise Conflict("This session uses a different provider mode. Create a new exercise for this runtime.")
            pk = f"SESSION#{session.meta['sessionId']}"
            sk = f"REQUEST#{request_id}"
            existing = await asyncio.to_thread(self.store.get, pk, sk)
            if existing:
                if existing["operation"] != operation:
                    raise Conflict("Request ID was already used for another operation")
                return
            status = session.meta["status"]
            allowed = {"start": {"ready"}, "pause": {"running"}, "resume": {"paused"}}
            if operation not in allowed or status not in allowed[operation]:
                raise Conflict(f"Cannot {operation} a {status} session")
            quota = None
            if operation in {"start", "resume"}:
                active = sum(
                    other is not session and (other.meta["status"] == "running"
                                               or any(not task.done() for task in other.model_tasks)
                                               or (other.finalizer is not None and not other.finalizer.done())
                                               or (other.advisory_task is not None and not other.advisory_task.done()))
                    for other in self.sessions.values()
                )
                if active >= self.config.max_active_sessions:
                    raise LimitExceeded("Another exercise is running or being assessed. Try again shortly.", 30)
                timestamp = datetime.now(UTC)
                tomorrow = (timestamp + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                quota = dict(PK=f"USER#{session.meta['traineeId']}", SK=f"QUOTA#RUNS#{timestamp.date()}",
                             limit=self.config.max_daily_runs_per_user,
                             retryAfter=max(1, int((tomorrow - timestamp).total_seconds())))
            previous_meta, previous_events = copy.deepcopy(session.meta), len(session.events)
            session.meta["status"] = "paused" if operation == "pause" else "running"
            if operation == "start":
                session.meta["startedAt"] = now()
            event = self._append_event(session, f"session_{operation}", "user", {"operation": operation})
            receipt = dict(PK=pk, SK=sk, operation=operation)
            try:
                await self._commit(session, [event], checkpoint=True, receipt=receipt, run_quota=quota)
            except SettledCancellation:
                # The durable start/resume succeeded even if its HTTP caller
                # disconnected. Keep the in-memory clock consistent with it.
                if operation in {"start", "resume"}:
                    self._launch(session)
                    if operation == "resume":
                        self._recover_checks(session)
                raise
            except BaseException:
                session.meta = previous_meta
                del session.events[previous_events:]
                raise
        if operation in {"start", "resume"}:
            self._launch(session)
            if operation == "resume":
                self._recover_checks(session)

    def _launch(self, session):
        if session.runner is None or session.runner.done():
            session.runner = asyncio.create_task(self._clock(session))

    def _recover_checks(self, session):
        for event in session.events:
            if event["type"] == "pilot_readback":
                instruction = next((e for e in reversed(session.events[:session.events.index(event)])
                                    if e["type"] == "trainee_instruction"), None)
                if instruction:
                    self._schedule_check(session, "alignment", event["eventId"],
                                         {"instruction": instruction["payload"]["text"],
                                          "readback": event["payload"]["text"]},
                                         [instruction["eventId"], event["eventId"]])
            elif event["type"] == "trainee_instruction" and event["payload"].get("scriptStepId") in {"correction", "stop"}:
                self._schedule_check(session, "correction", event["eventId"],
                                     {"response": event["payload"]["text"]}, [event["eventId"]])

    def _schedule_check(self, session, kind, job_key, state, event_ids):
        if job_key in session.scheduled_checks or any(a.get("jobKey") == job_key and a["processingStatus"] in {"pending", "completed"}
               for a in session.assessments):
            return
        session.scheduled_checks.add(job_key)

        async def check():
            try:
                result = await self.evaluate(session, kind, state, event_ids, job_key=job_key)
                if kind == "alignment" and result["processingStatus"] == "completed":
                    self._schedule_advisory(session, result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                async with session.lock:
                    event = self._append_event(session, "runtime_error", "system", {"error": type(exc).__name__, "jobKey": job_key})
                    await self._commit(session, [event], checkpoint=True)
            finally:
                session.scheduled_checks.discard(job_key)

        task = asyncio.create_task(check())
        session.model_tasks.add(task)
        task.add_done_callback(session.model_tasks.discard)
        task.add_done_callback(self._observe_task_error)

    @staticmethod
    def _observe_task_error(task):
        if not task.cancelled() and (error := task.exception()) is not None:
            logging.getLogger(__name__).error("Background execution failed: %s", type(error).__name__)

    def _record_observation_change(self, session):
        observation = physical_view(self.observation(session))
        previous = next((event for event in reversed(session.events) if event["type"] == "monitor_observation"), None)
        if previous is None or previous["payload"]["status"] != observation["status"]:
            return self._append_event(session, "monitor_observation", "simulator", observation)
        return None

    def _integrate(self, session, target):
        world = session.world
        seconds = (target - session.meta["simulationTimeMs"]) / 1000
        world["distanceBeforeHoldM"] = round(world["distanceBeforeHoldM"] - world["speedMps"] * seconds, 3)
        crossing = world["distanceBeforeHoldM"] < 0 and not world["runwayEntered"]
        world["runwayEntered"] |= crossing
        if world["distanceBeforeHoldM"] < -15:
            world.update(distanceBeforeHoldM=-15, speedMps=0, motionPlan="stop_on_runway")
        session.meta["simulationTimeMs"] = target
        if world["observationAvailable"]:
            world["lastObservation"] = {key: world[key] for key in
                                        ["distanceBeforeHoldM", "speedMps", "runwayEntered"]}
            world["lastObservation"]["observedAtMs"] = target
        return crossing

    async def advance(self, session, elapsed_ms):
        async with session.lock:
            if session.meta["status"] != "running":
                return
            target = min(session.meta["simulationTimeMs"] + elapsed_ms, session.scenario["durationMs"])
            due = [step for step in session.scenario["script"] if step["id"] not in session.processed
                   and step["atMs"] <= target
                   and session.meta["preset"] in step.get("presets", ["missed", "partial", "complete"])]
            for step in due:
                crossed = self._integrate(session, step["atMs"])
                updates = []
                if crossed:
                    updates.append(self._append_event(session, "runway_entered", "simulator", {"aircraft": "AIR123"}))
                session.processed.add(step["id"])
                action = step.get("action")
                if action == "hold":
                    session.world.update(speedMps=0, motionPlan="hold")
                elif action == "move":
                    session.world.update(speedMps=6, motionPlan="scripted_movement_fault")
                elif action == "restore_observation":
                    session.world["observationAvailable"] = True
                self._integrate(session, step["atMs"])
                payload = {"text": step["text"], "scriptStepId": step["id"], "source": "scripted_demo"}
                if step["type"] == "trainee_observation_check":
                    payload["observation"] = self.observation(session)
                event = self._append_event(session, step["type"], step["actor"], payload)
                updates.append(event)
                if observed := self._record_observation_change(session):
                    updates.append(observed)
                await self._commit(session, updates, checkpoint=True)
                if step["type"] == "pilot_readback":
                    instruction = next(e for e in reversed(session.events[:-1]) if e["type"] == "trainee_instruction")
                    self._schedule_check(session, "alignment", event["eventId"],
                                         {"instruction": instruction["payload"]["text"], "readback": step["text"]},
                                         [instruction["eventId"], event["eventId"]])
                elif step["id"] in {"correction", "stop"}:
                    self._schedule_check(session, "correction", event["eventId"],
                                         {"response": step["text"]}, [event["eventId"]])
            crossed = self._integrate(session, target)
            updates = [self._append_event(session, "runway_entered", "simulator", {"aircraft": "AIR123"})] if crossed else []
            if observed := self._record_observation_change(session):
                updates.append(observed)
            if target >= session.scenario["durationMs"] and not session.meta["simulationFinished"]:
                session.meta["simulationFinished"] = True
                updates.append(self._append_event(session, "script_finished", "system", {"automatic": True}))
            if updates or target // 2000 != (target - elapsed_ms) // 2000:
                await self._commit(session, updates, checkpoint=True)

    async def _clock(self, session):
        previous = time.monotonic()
        try:
            while session.meta["status"] in {"running", "paused"}:
                await asyncio.sleep(0.2)
                current = time.monotonic()
                elapsed = int((current - previous) * 1000)
                previous = current
                if session.meta["status"] == "paused":
                    continue
                if not session.meta["simulationFinished"]:
                    await self.advance(session, elapsed)
                elif session.finalizer is None or session.finalizer.done():
                    session.finalizer = asyncio.create_task(self.finalize(session))
                    session.finalizer.add_done_callback(self._observe_task_error)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with session.lock:
                session.meta["status"] = "paused"
                event = self._append_event(session, "runtime_error", "system", {"error": type(exc).__name__})
                await self._commit(session, [event], checkpoint=True)

    def observation(self, session):
        observed = copy.deepcopy(session.world["lastObservation"])
        observed["ageMs"] = session.meta["simulationTimeMs"] - observed["observedAtMs"]
        observed["status"] = "current" if observed["ageMs"] <= 5000 else "stale"
        return observed

    async def trace_start(self, session, actor, title, inputs):
        async with session.lock:
            trace_id, timestamp = identifier("trace"), now()
            trace = dict(SK=f"TRACE#{timestamp}#{trace_id}", id=trace_id, actor=actor, title=title,
                         status="running", startedAt=timestamp, simulationTimeMs=session.meta["simulationTimeMs"],
                         inputs=copy.deepcopy(inputs), providerMode=self.config.provider_mode)
            session.traces.append(trace)
            await self._commit(session, [trace])
            return trace_id

    async def trace_finish(self, session, trace_id, output, duration, error=False):
        async with session.lock:
            trace = next(t for t in session.traces if t["id"] == trace_id)
            trace.update(status="error" if error else "completed", output=copy.deepcopy(output),
                         roundTripMs=round(duration, 2), endedAt=now())
            await self._commit(session, [trace])

    async def evaluate(self, session, kind, state, event_ids, job_key=None):
        question = {"alignment": ALIGNMENT, "correction": CORRECTION,
                    "grounding": GROUNDING, "coaching": COACHING}[kind]
        model_state = decision_state(kind, state)
        assessment_id = identifier("assessment")
        async with session.lock:
            assessment = dict(SK=f"ASSESSMENT#{assessment_id}", assessmentId=assessment_id,
                              assessmentType=kind, processingStatus="pending", jobKey=job_key,
                              evidenceRefs={"eventIds": event_ids,
                                            "snapshotVersion": state.get("snapshotVersion")},
                              decisionInput={"state": copy.deepcopy(model_state), "questions": {kind: question}},
                              patternVersion="5", startedAt=now(), providerMode=self.config.provider_mode)
            session.assessments.append(assessment)
            await self._commit(session, [assessment])
        trace_id = await self.trace_start(session, "decider", {
            "alignment": "Compare instruction and readback", "correction": "Check explicit correction",
            "grounding": "Guard proposed advisory", "coaching": "Score advisory completeness"}[kind],
            {"assessmentId": assessment_id, "capability": question["type"], "question": question})
        started = time.perf_counter()
        try:
            response = await self.decider.ask(model_state, {kind: question})
            answer = response["answers"][kind]
            async with session.lock:
                assessment.update(processingStatus="completed", decisionOutput=answer, modelVersion=response["model"],
                                  usage=response.get("usage"), roundTripMs=response["roundTripMs"], endedAt=now(),
                                  completedAtSimulationTimeMs=session.meta["simulationTimeMs"])
                await self._commit(session, [assessment])
            await self.trace_finish(session, trace_id, {"answer": answer, "assessmentId": assessment_id},
                                    (time.perf_counter() - started) * 1000)
            return assessment
        except asyncio.CancelledError:
            async with session.lock:
                assessment.update(processingStatus="error", error="Execution interrupted", endedAt=now())
                await self._commit(session, [assessment])
            await self.trace_finish(session, trace_id, {"error": "Execution interrupted"},
                                    (time.perf_counter() - started) * 1000, error=True)
            raise
        except Exception as exc:
            async with session.lock:
                assessment.update(processingStatus="error", error=f"{type(exc).__name__}: {exc}", endedAt=now())
                await self._commit(session, [assessment])
            await self.trace_finish(session, trace_id, {"error": assessment["error"]},
                                    (time.perf_counter() - started) * 1000, error=True)
            return assessment

    async def capture(self, session):
        started = time.perf_counter()
        trace_id = await self.trace_start(session, "tool", "Read scenario-allowed evidence", {})
        async with session.lock:
            radio = [copy.deepcopy(e) for e in session.events if e["type"] in
                     {"trainee_instruction", "pilot_readback", "trainee_observation_check", "runway_entered"}]
            observation = self.observation(session)
            # Observability rules filter simulator events as well as positions.
            if observation["status"] != "current":
                radio = [e for e in radio if e["type"] != "runway_entered"]
            evidence = dict(events=radio, observation=observation,
                            initialSetup=scenario_setup(session.scenario),
                            correctionRecorded=any(e["payload"].get("scriptStepId") in {"correction", "stop"}
                                                   for e in radio),
                            traineeVerificationRecorded=any(e["type"] == "trainee_observation_check" for e in radio),
                            learningObjectives=session.scenario["learningObjectives"],
                            exerciseRubric="Monitor communication and aircraft response separately. An explicit correction with an aligned readback can resolve the communication issue. Verifying physical response requires current confirming evidence. An assistant observation is not a human controller's verification action.",
                            simulationTimeMs=session.meta["simulationTimeMs"],
                            evidenceSequence=session.meta["lastEventSequence"],
                            snapshotVersion=session.meta["latestSnapshotVersion"] + 1)
            await self._commit(session, [], checkpoint=True)
        await self.trace_finish(session, trace_id, evidence, (time.perf_counter() - started) * 1000)
        return evidence

    async def publish(self, session, message, evidence, findings=None, next_action=None, phase="final"):
        async def record_outcome(result):
            started = time.perf_counter()
            title = "Publish assistant advisory" if result["published"] else "Hold advisory for revision"
            trace_id = await self.trace_start(session, "tool", title, {"assessmentId": result.get("assessmentId"), "proposedFindings": findings, "nextAction": next_action})
            await self.trace_finish(session, trace_id, result, (time.perf_counter() - started) * 1000)
            return result

        if not isinstance(message, str) or not 1 <= len(message) <= 2000:
            return {"published": False, "reason": "Feedback must contain 1 to 2000 characters"}
        event_ids = [event["eventId"] for event in evidence["events"]]
        if findings is None:
            checks = [{**evidence, "candidate_feedback": message}]
        else:
            catalog = evidence_catalog(evidence)
            if not 1 <= len(findings) <= 3 or not isinstance(next_action, str) or not 1 <= len(next_action) <= 300 or not next_action.strip():
                return await record_outcome({"published": False, "reason": "Provide one to three findings and one next action."})
            # Advice is a review/check step. Observed distances must not become
            # invented numerical requirements for the controller.
            runway_numbers = set(re.findall(r"runway\s+(\d+)", " ".join(e["payload"].get("text", "") for e in evidence["events"]), re.I))
            numbers = set(re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\b", next_action))
            allowed_starts = {"check", "inspect", "review", "obtain", "record", "compare", "verify", "request", "read", "confirm"}
            # Nova sometimes phrases a valid check as "Instruct the trainee to
            # inspect ...". Validate its inner verb; do not accept arbitrary
            # instructions, pilot-directed commands or movement verbs.
            check_action = re.sub(r"^instruct\s+the\s+(?:controller|trainee)\s+to\s+", "", next_action.strip(), flags=re.I)
            first_word = next(iter(check_action.split()), "").strip(".,:").lower()
            if first_word not in allowed_starts:
                return await record_outcome({"published": False, "reason": "The next action must begin with an observation or debrief verb.", "instruction": "Write the action directly, for example: Inspect AIR123's current position and speed relative to the holding point and record the observation. Avoid introductory wording and new movement clearances."})
            if numbers - runway_numbers - {"0"}:
                return await record_outcome({"published": False, "reason": "The next action contains an unsupported numerical requirement.", "instruction": "Keep the next action qualitative except for the aircraft and runway identifiers. Put observed distances in findings; do not turn them into required buffers."})
            checks = []
            for finding in findings:
                keys, text = finding.get("evidence_keys", []), finding.get("text", "")
                if not isinstance(text, str) or not 1 <= len(text) <= 300 or not text.strip():
                    return await record_outcome({"published": False, "reason": "Each finding needs a text field with 1 to 300 characters.", "failed_finding": finding})
                if not isinstance(keys, list) or not 1 <= len(keys) <= 4 or any(not isinstance(key, str) or key not in catalog for key in keys):
                    return await record_outcome({"published": False, "reason": "Each finding needs evidence_keys: a list of 1 to 4 source KEY NAMES, not source text.", "failed_finding": finding, "allowed_source_keys": list(catalog)})
                checks.append({"evidence": [catalog[key] for key in keys], "statement": text,
                               "snapshotVersion": evidence["snapshotVersion"]})
            message = " ".join([*(finding["text"] for finding in findings), next_action])
        def rejection(check, guard, reused=False):
            answer = guard.get("decisionOutput", {})
            return {"published": False,
                    "reason": "repeated_rejected_finding" if reused else (
                        "low_confidence" if answer.get("choice") == "supported" else answer.get("choice", "model_error")),
                    "failed_finding": check.get("statement", message), "verdict": answer.get("choice"),
                    "confidence": answer.get("confidence"), "requiredConfidence": 0.7,
                    "assessmentId": guard["assessmentId"], "reusedAssessment": reused,
                    "instruction": "Omit this rejected finding; do not resubmit it unchanged. If it combines several facts, split it into separate findings, each stating one directly recorded fact and citing its own source. One simple supported finding is enough. Do not infer intentions or mental state."}

        # An unchanged statement with identical cited evidence cannot gain support
        # by rerunning a deterministic guard. Check all findings before spending
        # inference on an earlier, acceptable part of the same rejected proposal.
        for check in checks:
            previous = next((a for a in reversed(session.assessments)
                             if a["assessmentType"] == "grounding" and a["processingStatus"] == "completed"
                             and a.get("decisionInput", {}).get("state") == decision_state("grounding", check)), None)
            if previous:
                answer = previous.get("decisionOutput", {})
                if answer.get("choice") != "supported" or answer.get("confidence", 0) < 0.7:
                    return await record_outcome(rejection(check, previous, reused=True))
        guards = []
        for check in checks:
            guard = await self.evaluate(session, "grounding", check, event_ids)
            guards.append(guard)
            answer = guard.get("decisionOutput", {})
            if answer.get("choice") != "supported" or answer.get("confidence", 0) < 0.7:
                return await record_outcome(rejection(check, guard))
        state = {**evidence, "candidate_feedback": next_action if next_action is not None else message}
        quality = await self.evaluate(session, "coaching", state, event_ids)
        score = quality.get("decisionOutput", {})
        # Score covers next-check details, not factual confidence. The Choice guard
        # above owns factual publication; retain the score confidence for inspection.
        if quality["processingStatus"] != "completed" or score.get("score", 0) < 1.3:
            return await record_outcome({"published": False, "reason": "Give a more concrete next action", "score": score.get("score"), "requiredScore": 1.3, "confidence": score.get("confidence"), "assessmentId": quality["assessmentId"], "instruction": "Name AIR123, the simulator data to inspect (position/distance and speed), the scenario's runway holding point to compare against, and the observation check to record. Keep the supported findings and revise the next action."})
        async with session.lock:
            # A model call may finish after later radio messages or physical changes.
            newer = any(e["sequence"] > evidence["evidenceSequence"] and e["type"] in
                        {"trainee_instruction", "pilot_readback", "trainee_observation_check", "runway_entered"}
                        for e in session.events)
            current = self.observation(session)
            fields = ["distanceBeforeHoldM", "speedMps", "runwayEntered", "status"]
            if newer or any(current[key] != evidence["observation"][key] for key in fields):
                outcome = {"published": False, "reason": "Relevant evidence changed; read evidence and recheck"}
            else:
                event = self._append_event(session, "instructor_feedback", "instructor",
                                           {"text": message, "guardAssessmentId": guard["assessmentId"],
                                            "guardAssessmentIds": [g["assessmentId"] for g in guards],
                                            "qualityAssessmentId": quality["assessmentId"],
                                            "findings": findings, "nextAction": next_action,
                                            "evidenceSequence": evidence["evidenceSequence"],
                                            "evidenceObservation": copy.deepcopy(evidence["observation"]), "phase": phase})
                await self._commit(session, [event], checkpoint=True)
                outcome = {"published": True, "eventId": event["eventId"], "assessmentId": guard["assessmentId"]}
        return await record_outcome(outcome)

    async def _wait_primary(self, session):
        while pending := [task for task in session.model_tasks if not task.done()]:
            await asyncio.gather(*(asyncio.shield(task) for task in pending), return_exceptions=True)

    def _schedule_advisory(self, session, assessment):
        # One optional live explanation, plus the final summary. The structured
        # monitor is already visible and never waits for this Bedrock path.
        if (self.config.provider_mode != "live" or session.meta["simulationFinished"] or session.advisory_attempted
                or any(event["type"] == "assistant_advisory_started" for event in session.events)
                or (session.advisory_task and not session.advisory_task.done())):
            return
        current = monitor_view(session, self.observation(session))["communication"]
        if current["assessmentId"] != assessment["assessmentId"]:
            return
        session.advisory_task = asyncio.create_task(self._live_advisory(session))
        session.advisory_task.add_done_callback(self._observe_task_error)

    async def _live_advisory(self, session):
        await asyncio.sleep(0.4)  # Coalesce a near-simultaneous correction/readback.
        await self._wait_primary(session)
        async with session.lock:
            current = monitor_view(session, self.observation(session))["communication"]
            if session.meta["simulationFinished"] or current["status"] in {"waiting", "checking"}:
                return
            session.advisory_attempted = True
            event = self._append_event(session, "assistant_advisory_started", "assistant", {"phase": "live"})
            await self._commit(session, [event], checkpoint=True)
        await self._run_assistant(session, "live")

    async def _run_assistant(self, session, phase):
        async def capture():
            await self._wait_primary(session)
            return await self.capture(session)

        async def usage(value, incomplete=False):
            async with session.lock:
                previous = session.meta.get("bedrockUsage") or {}
                session.meta["bedrockUsage"] = {key: previous.get(key, 0) + value.get(key, 0)
                                                for key in set(previous) | set(value)}
                session.meta["bedrockUsageIncomplete"] = session.meta.get("bedrockUsageIncomplete", False) or incomplete
                await self._commit(session, [])

        try:
            await run_instructor(self.config, capture,
                                 lambda message, evidence, **kwargs: self.publish(session, message, evidence, phase=phase, **kwargs),
                                 lambda actor, title, inputs: self.trace_start(session, actor, title, inputs),
                                 lambda trace_id, output, duration, error=False:
                                     self.trace_finish(session, trace_id, output, duration, error), usage, phase=phase)
        except asyncio.CancelledError:
            await usage({}, incomplete=True)
            raise
        except Exception as exc:
            await usage({}, incomplete=True)
            trace_id = await self.trace_start(session, "agent", "Assistant execution failed", {"phase": phase})
            await self.trace_finish(session, trace_id, {"error": f"{type(exc).__name__}: {exc}"}, 0, error=True)

    async def finalize(self, session):
        await self._wait_primary(session)
        if session.advisory_task and not session.advisory_task.done():
            await asyncio.gather(asyncio.shield(session.advisory_task), return_exceptions=True)
        async with session.lock:
            if session.meta["status"] == "completed":
                return
            advisory = monitor_view(session, self.observation(session))["advisory"]
            reuse = bool(advisory and advisory["isCurrent"])
        if not reuse:
            await self._run_assistant(session, "final")
        async with session.lock:
            advisory = monitor_view(session, self.observation(session))["advisory"]
            has_feedback = bool(advisory and advisory["isCurrent"])
            records = []
            if has_feedback:
                # Reference the original checked publication, retaining its phase,
                # evidence and model usage. This is selection, not new inference.
                records.append(self._append_event(session, "assistant_final_advisory", "assistant",
                                                   {"advisoryEventId": advisory["eventId"],
                                                    "sourcePhase": advisory["phase"], "reused": reuse}))
            session.meta.update(status="completed", endedAt=now(),
                                assessmentStatus="completed" if has_feedback else "needs_review")
            records.append(self._append_event(session, "session_completed", "system",
                                               {"feedbackPublished": has_feedback,
                                                "finalAdvisoryEventId": advisory["eventId"] if has_feedback else None}))
            await self._commit(session, records, checkpoint=True)

    def view(self, session):
        meta = {key: value for key, value in session.meta.items() if key not in {"PK", "SK", "GSI1PK", "GSI1SK"}}
        traces = sorted(session.traces, key=lambda t: t["startedAt"])
        return dict(**meta, title=session.scenario["title"], objective=session.scenario["objective"],
                    initialSetup=scenario_setup(session.scenario),
                    durationMs=session.scenario["durationMs"], observation=self.observation(session),
                    events=session.events, assessments=session.assessments, traces=traces,
                    monitor=monitor_view(session, self.observation(session)))

    async def shutdown(self):
        for session in list(self.sessions.values()):
            tasks = [t for t in [session.runner, session.finalizer, session.advisory_task, *session.model_tasks] if t and not t.done()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if session.meta["status"] == "running":
                async with session.lock:
                    session.meta["status"] = "paused"
                    event = self._append_event(session, "backend_suspended", "system", {"status": "paused"})
                    await self._commit(session, [event], checkpoint=True)
