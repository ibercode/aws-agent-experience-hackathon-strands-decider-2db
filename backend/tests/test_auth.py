from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from clearance_gap.api import create_app
from clearance_gap.auth import Auth
from clearance_gap.config import Settings


def test_production_cannot_start_with_local_identity_or_fixture_models():
    with pytest.raises(ValueError, match="Production requires"):
        Settings(_env_file=None, app_env="production")


@pytest.mark.parametrize("change,status", [({"client_id": "other-client"}, 401),
                                         ({"token_use": "id"}, 401),
                                         ({"iss": "https://wrong-issuer.invalid"}, 401),
                                         ({"exp": 1}, 401), ({"scope": "openid"}, 403),
                                         ({"scope": ["training/read"]}, 401), ({}, 200)])
async def test_cognito_checks_signature_claims_and_scope(config, monkeypatch, change, status):
    config = config.model_copy(update={"auth_mode": "cognito", "cognito_user_pool_id": "eu-west-1_example",
                                       "cognito_client_id": "example-client", "cognito_required_scope": "training/read"})
    auth = Auth(config)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth.jwks, "get_signing_key_from_jwt", lambda _: SimpleNamespace(key=key.public_key()))
    claims = {"sub": "trainee-a", "iss": config.issuer, "client_id": "example-client",
              "token_use": "access", "scope": "openid training/read", "exp": 4102444800, **change}
    token = jwt.encode(claims, key, algorithm="RS256")
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    if status == 200:
        assert (await auth.identity(request)).sub == "trainee-a"
    else:
        with pytest.raises(HTTPException) as exc:
            await auth.identity(request)
        assert exc.value.status_code == status


@pytest.mark.parametrize("change, message", [
    ({"cognito_required_scope": ""}, "Cognito API scope"),
    ({"cognito_domain": "http://login.invalid"}, "HTTPS Cognito"),
    ({"cognito_domain": "https://login.invalid/unexpected-path"}, "HTTPS Cognito"),
    ({"aws_profile": "local-profile"}, "ECS task role"),
    ({"cognito_user_pool_id": "us-east-1_example"}, "must match AWS_REGION"),
    ({"scenario_bucket": ""}, "scenario bucket"),
])
def test_production_rejects_incomplete_or_insecure_configuration(change, message):
    values = dict(app_env="production", auth_mode="cognito", provider_mode="live", storage_mode="dynamodb",
                  bedrock_model_id="test-model", cognito_user_pool_id="eu-west-1_example",
                  cognito_client_id="example-client", cognito_domain="https://example.auth.eu-west-1.amazoncognito.com",
                  cognito_required_scope="training/read", scenario_bucket="example-scenarios")
    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **(values | change))


async def test_api_requires_valid_cognito_token_and_keeps_sessions_private(config, monkeypatch, request_body):
    config = config.model_copy(update={"auth_mode": "cognito", "cognito_user_pool_id": "eu-west-1_example",
                                       "cognito_client_id": "example-client", "cognito_required_scope": "training/read"})
    app = create_app(config)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(app.state.auth.jwks, "get_signing_key_from_jwt",
                        lambda _: SimpleNamespace(key=key.public_key()))

    def headers(owner, signing_key=key):
        token = jwt.encode({"sub": owner, "iss": config.issuer, "client_id": "example-client",
                            "token_use": "access", "scope": "openid training/read", "exp": 4102444800},
                           signing_key, algorithm="RS256")
        return {"Authorization": f"Bearer {token}", "Idempotency-Key": "create-test-session"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://example.invalid") as client:
        for path in ["/api/me", "/api/scenarios", "/api/sessions", "/api/sessions/unknown"]:
            response = await client.get(path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
            assert response.headers["cache-control"] == "no-store, private"
        assert (await client.get("/api/me", headers=headers("alice", attacker_key))).status_code == 401
        assert (await client.get("/api/health")).status_code == 200
        assert (await client.get("/api/config")).status_code == 200
        created = await client.post("/api/sessions", json=request_body, headers=headers("alice"))
        assert created.status_code == 201
        session_id = created.json()["sessionId"]
        assert (await client.get(f"/api/sessions/{session_id}", headers=headers("alice"))).status_code == 200
        assert (await client.get(f"/api/sessions/{session_id}", headers=headers("bob"))).status_code == 404
        assert (await client.post(f"/api/sessions/{session_id}/start", json={}, headers=headers("bob"))).status_code == 404
        assert (await client.get("/api/sessions", headers=headers("bob"))).json() == []
    await app.state.engine.shutdown()
