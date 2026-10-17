"""Read-only deployed access checks; no Cognito user credentials or AWS writes.

Run with the backend virtualenv. --profile additionally verifies Cognito configuration
with AWS read-only calls; omit it to perform HTTPS checks only. This does not sign in,
exercise the MFA enrollment flow, or run a paid model inference.
"""
import argparse
import json
import os
import re
import subprocess
from urllib.parse import urlsplit

import httpx


class CognitoReadError(Exception):
    pass


def read_cognito(operation, profile, region, **parameters):
    """Use the configured AWS CLI credential cache, without exporting credentials."""
    command = ["aws", "--profile", profile, "--region", region, "--output", "json", "--no-cli-pager",
               "cognito-idp", operation, "--cli-input-json", json.dumps(parameters)]
    try:
        response = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False,
                                  env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"})
    except subprocess.TimeoutExpired as exc:
        raise CognitoReadError("CliTimeout") from exc
    except OSError as exc:
        raise CognitoReadError("CliUnavailable") from exc
    if response.returncode:
        match = re.search(r"An error occurred \(([A-Za-z0-9_.-]{1,80})\)", response.stderr)
        raise CognitoReadError(match.group(1) if match else "CliFailure")
    try:
        result = json.loads(response.stdout)
        if not isinstance(result, dict):
            raise TypeError("Expected an object")
        return result
    except (ValueError, TypeError) as exc:
        raise CognitoReadError("InvalidCliResponse") from exc


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError("--url must be an HTTPS origin without a path or credentials")
    return value.rstrip("/")


def check_http(url):
    checks, statuses, errors = {}, {}, {}
    config = {}
    with httpx.Client(base_url=url, timeout=20, follow_redirects=False) as client:
        def get(path, headers=None, label=None):
            name = label or path
            try:
                response = client.get(path, headers=headers)
                statuses[name] = response.status_code
                return response
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                errors[name] = type(exc).__name__
                return None

        root = get("/")
        checks["httpsRoot"] = root is not None and root.status_code == 200
        hsts = root.headers.get("strict-transport-security", "") if root is not None else ""
        hsts_values = dict(part.strip().lower().split("=", 1) for part in hsts.split(";") if "=" in part)
        checks["hsts"] = hsts_values.get("max-age", "").isdigit() and int(hsts_values["max-age"]) >= 31536000
        policy = root.headers.get("content-security-policy", "") if root is not None else ""
        directives = {part.split()[0]: part.split()[1:]
                      for part in policy.lower().split(";") if part.strip()}
        checks["contentSecurityPolicy"] = (
            directives.get("default-src") == ["'self'"]
            and directives.get("object-src") == ["'none'"]
            and directives.get("frame-ancestors") == ["'none'"]
            and "'unsafe-eval'" not in directives.get("script-src", [])
        )

        def json_body(response):
            try:
                value = response.json() if response is not None else {}
                return value if isinstance(value, dict) else {}
            except ValueError:
                return {}

        health = get("/api/health")
        health_body = json_body(health)
        checks["liveCognitoHealth"] = (health is not None and health.status_code == 200
                                       and health_body.get("status") == "ok"
                                       and health_body.get("providerMode") == "live"
                                       and health_body.get("authMode") == "cognito")
        public = get("/api/config")
        config = json_body(public)
        checks["publicCognitoConfiguration"] = (
            public is not None and public.status_code == 200
            and config.get("authMode") == "cognito" and config.get("providerMode") == "live"
            and all(isinstance(config.get(key), str) and config[key]
                    for key in ["issuer", "clientId", "domain", "requiredScope"])
        )
        for path in ["/api/me", "/api/scenarios", "/api/sessions"]:
            response = get(path)
            checks[f"unauthenticated:{path}"] = response is not None and response.status_code == 401
            checks[f"uncached:{path}"] = (
                response is not None and "no-store" in response.headers.get("cache-control", "").lower()
            )
        malformed = get("/api/me", {"Authorization": "Bearer invalid-token"}, "malformedBearer")
        checks["malformedBearerRejected"] = malformed is not None and malformed.status_code == 401
        docs = get("/api/openapi.json")
        checks["apiSchemaUnavailable"] = docs is not None and docs.status_code == 404
    return checks, statuses, errors, config


def check_cognito(url, config, profile, region):
    issuer = urlsplit(config.get("issuer", ""))
    pool_id = issuer.path.lstrip("/")
    if (issuer.scheme != "https" or issuer.netloc != f"cognito-idp.{region}.amazonaws.com"
            or not pool_id.startswith(f"{region}_") or "/" in pool_id or not config.get("clientId")):
        return {"cognitoIdentifiersMatchRegion": False}, {}
    checks, errors = {"cognitoIdentifiersMatchRegion": True}, {}
    try:
        pool = read_cognito("describe-user-pool", profile, region, UserPoolId=pool_id)["UserPool"]
        mfa = read_cognito("get-user-pool-mfa-config", profile, region, UserPoolId=pool_id)
        client = read_cognito("describe-user-pool-client", profile, region,
                              UserPoolId=pool_id, ClientId=config["clientId"])["UserPoolClient"]
        units = client.get("TokenValidityUnits", {})
        minutes_per_unit = {"minutes": 1, "hours": 60, "days": 1440}
        access_minutes = client.get("AccessTokenValidity", 0) * minutes_per_unit.get(units.get("AccessToken", "hours"), 0)
        id_minutes = client.get("IdTokenValidity", 0) * minutes_per_unit.get(units.get("IdToken", "hours"), 0)
        checks.update({
            "invitationOnly": pool.get("AdminCreateUserConfig", {}).get("AllowAdminCreateUserOnly") is True,
            "requiredAuthenticatorMfa": pool.get("MfaConfiguration") == "ON" and mfa.get("MfaConfiguration") == "ON"
            and mfa.get("SoftwareTokenMfaConfiguration", {}).get("Enabled") is True,
            "publicCodeFlowClient": client.get("AllowedOAuthFlowsUserPoolClient") is True
            and set(client.get("AllowedOAuthFlows", [])) == {"code"} and not client.get("ClientSecret"),
            "shortAccessTokens": access_minutes == 15 and id_minutes == 15,
            "exactCallback": set(client.get("CallbackURLs", [])) == {f"{url}/auth/callback"},
            "exactLogout": set(client.get("LogoutURLs", [])) == {url},
            "apiScopeAllowed": config.get("requiredScope") in client.get("AllowedOAuthScopes", []),
            "tokenRevocationEnabled": client.get("EnableTokenRevocation") is True,
            "userExistenceProtected": client.get("PreventUserExistenceErrors") == "ENABLED",
        })
    except (CognitoReadError, KeyError, TypeError, AttributeError) as exc:
        # Never include AWS response bodies, account identifiers or session credentials.
        checks["cognitoReadOnlyInspection"] = False
        errors["cognito"] = str(exc) if isinstance(exc, CognitoReadError) else "InvalidCliResponse"
    return checks, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, type=origin)
    parser.add_argument("--profile", help="Optional configured AWS profile for read-only Cognito inspection")
    parser.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()
    checks, statuses, errors, config = check_http(args.url)
    if args.profile:
        cloud_checks, cloud_errors = check_cognito(args.url, config, args.profile, args.region)
        checks.update(cloud_checks)
        errors.update(cloud_errors)
    passed = all(checks.values()) and not errors
    print(json.dumps({"check": "deployed-access", "passed": passed, "checks": checks,
                      "httpStatus": statuses, "errors": errors, "awsChecksRequested": bool(args.profile),
                      "browserLoginTested": False, "modelInferenceTested": False}, sort_keys=True), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
