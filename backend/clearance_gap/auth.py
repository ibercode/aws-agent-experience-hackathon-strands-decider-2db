import asyncio
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Identity:
    sub: str
    name: str


class Auth:
    def __init__(self, config):
        self.config = config
        self.jwks = jwt.PyJWKClient(f"{config.issuer}/.well-known/jwks.json", cache_keys=True, timeout=5)

    async def identity(self, request: Request):
        if self.config.auth_mode == "local":
            return Identity("local-developer", "Local developer")
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "A Cognito access token is required", headers={"WWW-Authenticate": "Bearer"})
        token = authorization[7:]
        try:
            signing_key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=self.config.issuer,
                                options={"verify_aud": False, "require": ["exp", "iss", "sub", "token_use", "client_id"]})
            if claims["token_use"] != "access" or claims["client_id"] != self.config.cognito_client_id:
                raise jwt.InvalidTokenError("Wrong token use or app client")
            required = self.config.cognito_required_scope
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                raise jwt.InvalidTokenError("Invalid scope claim")
            if required and required not in scope.split():
                raise HTTPException(403, "Required API scope is missing")
            return Identity(claims["sub"], claims.get("username", "Controller"))
        except (jwt.PyJWTError, jwt.PyJWKClientError, ValueError) as exc:
            raise HTTPException(401, "Invalid or expired Cognito access token",
                                headers={"WWW-Authenticate": "Bearer"}) from exc
