import asyncio
import copy
import math

import httpx
import pytest

from clearance_gap.config import Settings
from clearance_gap.decisions import ALIGNMENT, DecisionClient, validate_answer


def valid_choice():
    return {"type": "choice", "choice": "contradicts", "confidence": 0.85,
            "probabilities": {"matches": 0.05, "contradicts": 0.9, "unclear": 0.05}}


@pytest.mark.parametrize("mutation", [
    {"type": "score"}, {"choice": "invented_option"}, {"confidence": math.nan},
    {"probabilities": {"matches": 1}},
    {"probabilities": {"matches": 0.5, "contradicts": 0.9, "unclear": 0.5}},
    {"probabilities": {"matches": -0.1, "contradicts": 1.0, "unclear": 0.1}},
])
def test_rejects_invalid_decider_answers(mutation):
    with pytest.raises(ValueError):
        validate_answer(ALIGNMENT, {**valid_choice(), **mutation})


async def test_live_client_uses_real_wire_contract(monkeypatch):
    async def endpoint(request):
        import json
        body = json.loads(request.content)
        assert request.url.path == "/v1/systemone"
        assert body["questions"]["alignment"]["type"] == "choice"
        return httpx.Response(200, json={"model": "pinned-model", "answers": {"alignment": valid_choice()},
                                        "usage": {"input_tokens": 57, "output_tokens": 0}, "latency_ms": 24})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(endpoint), **kwargs))
    config = Settings(provider_mode="live", bedrock_model_id="test-model")
    response = await DecisionClient(config).ask({"instruction": "Hold short", "readback": "Lining up"},
                                               {"alignment": copy.deepcopy(ALIGNMENT)})
    assert response["model"] == "pinned-model"
    assert response["usage"]["input_tokens"] == 57
    assert "fixture" not in response["answers"]["alignment"]


async def test_live_error_is_not_replaced_by_a_fixture(monkeypatch):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(422, json={"detail": "context window exceeded"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(ValueError, match="context window exceeded"):
        await DecisionClient(Settings(provider_mode="live", bedrock_model_id="test-model")).ask({}, {"alignment": ALIGNMENT})


def test_accepts_the_upstreams_four_decimal_rounding():
    answer = valid_choice()
    answer["probabilities"] = {"matches": 0.05, "contradicts": 0.9001, "unclear": 0.05}
    assert validate_answer(ALIGNMENT, answer) is answer


async def test_cancelling_active_advisory_retains_slot_until_server_response(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def endpoint(request):
        requests.append(request)
        if len(requests) == 1:
            entered.set()
            await release.wait()
        return httpx.Response(200, json={"model": "test", "answers": {"alignment": valid_choice()}})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(endpoint), **kwargs))
    client = DecisionClient(Settings(provider_mode="live", bedrock_model_id="test-model"))
    first = asyncio.create_task(client.ask({}, {"alignment": ALIGNMENT}))
    await entered.wait()
    first.cancel()
    queued = asyncio.create_task(client.ask({}, {"alignment": ALIGNMENT}))
    await asyncio.sleep(0)
    first.cancel()  # Shutdown can overlap an invocation timeout.
    await asyncio.sleep(0)
    assert len(requests) == 1 and client.busy and not first.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert (await queued)["answers"]["alignment"]["choice"] == "contradicts"
    assert len(requests) == 2 and not client.busy
