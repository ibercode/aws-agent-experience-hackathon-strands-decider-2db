from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    auth_mode: str = "local"
    provider_mode: str = "fixture"
    storage_mode: str = "sqlite"
    aws_region: str = "eu-west-1"
    aws_profile: str | None = None
    database_path: str = "../.data/clearance-gap.db"
    scenarios_path: str = str(Path(__file__).resolve().parents[2] / "scenarios")
    decider_url: str = "http://127.0.0.1:8099"
    decider_model_id: str = "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"
    bedrock_model_id: str = ""
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_domain: str = ""
    cognito_required_scope: str = ""
    dynamodb_table: str = "clearance-gap-sessions"
    scenario_bucket: str = ""
    model_timeout_seconds: float = 90
    fixture_delay_seconds: float = 0.65
    max_active_sessions: int = Field(default=1, ge=1, le=10)
    max_daily_runs_per_user: int = Field(default=20, ge=1, le=100)

    @field_validator("aws_profile", mode="before")
    @classmethod
    def empty_profile(cls, value):
        return value or None

    @model_validator(mode="after")
    def validate_modes(self):
        for value, allowed in [(self.auth_mode, {"local", "cognito"}),
                               (self.provider_mode, {"fixture", "live"}),
                               (self.storage_mode, {"sqlite", "dynamodb"})]:
            if value not in allowed:
                raise ValueError(f"Invalid runtime mode: {value}")
        if self.auth_mode == "cognito" and not (self.cognito_user_pool_id and self.cognito_client_id):
            raise ValueError("Cognito requires user pool and app client identifiers")
        if self.provider_mode == "live" and not self.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required; live mode never falls back to fixtures")
        if self.app_env == "production" and (
            self.auth_mode != "cognito" or self.provider_mode != "live" or self.storage_mode != "dynamodb"
        ):
            raise ValueError("Production requires Cognito, live providers and DynamoDB")
        if self.app_env == "production":
            domain = urlsplit(self.cognito_domain)
            if (domain.scheme != "https" or not domain.hostname or domain.username or domain.password
                    or domain.path not in {"", "/"} or domain.query or domain.fragment):
                raise ValueError("Production requires an HTTPS Cognito login domain")
            if not self.cognito_required_scope:
                raise ValueError("Production requires a Cognito API scope")
            if not self.cognito_user_pool_id.startswith(f"{self.aws_region}_"):
                raise ValueError("The Cognito user pool must match AWS_REGION")
            if self.aws_profile:
                raise ValueError("Production uses the ECS task role; do not set AWS_PROFILE")
            if not self.scenario_bucket or not self.dynamodb_table:
                raise ValueError("Production requires a scenario bucket and DynamoDB table")
        return self

    @property
    def issuer(self):
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}"


@lru_cache
def settings():
    return Settings()
