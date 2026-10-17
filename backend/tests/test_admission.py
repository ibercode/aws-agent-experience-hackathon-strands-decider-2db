import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient

from clearance_gap.api import create_app
from clearance_gap.catalog import Catalog
from clearance_gap.decisions import DecisionClient
from clearance_gap.engine import Engine
from clearance_gap.store import LimitExceeded, Store


async def test_concurrent_starts_admit_one_exercise(engine, request_body, monkeypatch):
    monkeypatch.setattr(engine, "_launch", lambda _: None)
    sessions = [await engine.create(owner, request_body, "create-session") for owner in ["alice", "bob"]]
    results = await asyncio.gather(*(engine.control(s, "start", "start-session") for s in sessions),
                                   return_exceptions=True)
    assert sum(isinstance(result, LimitExceeded) for result in results) == 1
    assert sorted(s.meta["status"] for s in sessions) == ["ready", "running"]
    await engine.shutdown()


async def test_paused_session_still_occupies_slot_while_models_run(engine, request_body, monkeypatch):
    monkeypatch.setattr(engine, "_launch", lambda _: None)
    first = await engine.create("alice", request_body, "create-one")
    second = await engine.create("bob", request_body, "create-two")
    await engine.control(first, "start", "start-one")
    await engine.control(first, "pause", "pause-one")
    waiting = asyncio.create_task(asyncio.Event().wait())
    first.model_tasks.add(waiting)
    with pytest.raises(LimitExceeded, match="being assessed"):
        await engine.control(second, "start", "start-two")
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    await engine.control(second, "start", "start-two")
    assert second.meta["status"] == "running"
    await engine.shutdown()


async def test_daily_quota_survives_restart_and_retries_are_not_charged(config, request_body, monkeypatch):
    config = config.model_copy(update={"max_daily_runs_per_user": 2})
    store = Store(config)
    engine = Engine(config, store, Catalog(config), DecisionClient(config))
    monkeypatch.setattr(engine, "_launch", lambda _: None)
    first = await engine.create("alice", request_body, "create-one")
    await engine.control(first, "start", "start-one")
    await engine.control(first, "start", "start-one")
    await engine.control(first, "pause", "pause-one")
    await engine.control(first, "resume", "resume-one")
    await engine.control(first, "pause", "pause-two")
    counter = store.get("USER#alice", f"QUOTA#RUNS#{datetime.now(UTC).date()}")
    assert counter["runs"] == 2

    restarted = Engine(config, store, Catalog(config), DecisionClient(config))
    restored = await restarted.get(first.meta["sessionId"], "alice")
    revision, event_count = restored.meta["revision"], len(restored.events)
    with pytest.raises(LimitExceeded, match="Daily exercise limit"):
        await restarted.control(restored, "resume", "resume-two")
    assert restored.meta["status"] == "paused"
    assert restored.meta["revision"] == revision
    assert len(restored.events) == event_count
    assert store.get(f"SESSION#{restored.meta['sessionId']}", "REQUEST#resume-two") is None
    assert store.get("USER#alice", counter["SK"])["runs"] == 2
    await engine.shutdown()
    await restarted.shutdown()


async def test_admission_limit_is_a_friendly_429(config, request_body, monkeypatch):
    app = create_app(config)
    monkeypatch.setattr(app.state.engine, "_launch", lambda _: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://example.invalid") as client:
        ids = []
        for request_id in ["create-one", "create-two"]:
            response = await client.post("/api/sessions", json=request_body,
                                         headers={"Idempotency-Key": request_id})
            ids.append(response.json()["sessionId"])
        assert (await client.post(f"/api/sessions/{ids[0]}/start", json={},
                                  headers={"Idempotency-Key": "start-one"})).status_code == 200
        response = await client.post(f"/api/sessions/{ids[1]}/start", json={},
                                     headers={"Idempotency-Key": "start-two"})
        assert response.status_code == 429
        assert "Another exercise" in response.json()["detail"]
        assert response.headers["retry-after"] == "30"
    await app.state.engine.shutdown()


def test_dynamodb_quota_is_atomic_with_session_commit():
    store = Store.__new__(Store)
    store.config = SimpleNamespace(storage_mode="dynamodb", dynamodb_table="test-sessions")
    store.serializer, store.deserializer = TypeSerializer(), TypeDeserializer()
    calls = []

    def write(**kwargs):
        calls.append(kwargs)
        raise ClientError({"Error": {"Code": "TransactionCanceledException"},
                           "CancellationReasons": [{"Code": "None"}, {"Code": "ConditionalCheckFailed"}]},
                          "TransactWriteItems")

    store.client = SimpleNamespace(transact_write_items=write)
    quota = dict(PK="USER#alice", SK="QUOTA#RUNS#2026-01-01", limit=2, retryAfter=60)
    with pytest.raises(LimitExceeded):
        store.commit(dict(sessionId="test", traineeId="alice", createdAt="2026-01-01", revision=2), [], 1,
                     run_quota=quota)
    transaction = calls[0]["TransactItems"]
    assert "Put" in transaction[0]
    assert transaction[1]["Update"]["ConditionExpression"] == "attribute_not_exists(#runs) OR #runs < :limit"
