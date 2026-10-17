import asyncio
import threading
from types import SimpleNamespace

import pytest

from clearance_gap.instructor import _invoke_with_usage


async def test_cancelled_control_settles_store_transaction_before_shutdown(engine, request_body, monkeypatch):
    session = await engine.create("alice", request_body, "transaction-create")
    entered, release = threading.Event(), threading.Event()
    original = engine.store.commit

    def commit(*args):
        entered.set()
        assert release.wait(2)
        return original(*args)

    monkeypatch.setattr(engine.store, "commit", commit)
    task = asyncio.create_task(engine.control(session, "start", "transaction-start"))
    await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    persisted = engine.store.get(f"SESSION#{session.meta['sessionId']}", "META")
    assert session.meta["revision"] == persisted["revision"]
    assert session.meta["status"] == persisted["status"] == "running"
    assert session.runner is not None and not session.runner.done()
    await engine.control(session, "start", "transaction-start")  # The committed receipt is idempotent.
    await engine.shutdown()
    assert session.meta["status"] == "paused"


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
async def test_usage_survives_later_invocation_failure_and_marks_unknown_work(outcome):
    captured = []

    class Agent:
        event_loop_metrics = SimpleNamespace(accumulated_usage={"inputTokens": 40, "outputTokens": 12, "totalTokens": 52})

        async def invoke_async(self, prompt, limits):
            if outcome == "failure":
                raise RuntimeError("Later provider call failed")
            if outcome == "timeout":
                await asyncio.Event().wait()
            return "done"

    async def usage(value, incomplete=False):
        captured.append((value, incomplete))

    if outcome == "success":
        assert await _invoke_with_usage(Agent(), "prompt", {}, 0.01, usage) == "done"
    else:
        with pytest.raises(RuntimeError if outcome == "failure" else TimeoutError):
            await _invoke_with_usage(Agent(), "prompt", {}, 0.01, usage)
    assert captured == [({"inputTokens": 40, "outputTokens": 12, "totalTokens": 52}, outcome != "success")]
