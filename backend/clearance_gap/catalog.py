import hashlib
import json
import re
from pathlib import Path

import boto3

CURRENT_SCENARIO_VERSION = "3"


def scenario_setup(scenario):
    """Presentation metadata from the pinned definition, without rewriting it."""
    setup = dict(scenario["initialSetup"])
    runway = setup["runway"]
    if not re.fullmatch(r"(?:0[1-9]|[12][0-9]|3[0-6])", runway):
        raise ValueError("Scenario runway designator is not available")
    reciprocal = f"{(int(runway) + 17) % 36 + 1:02d}"
    if setup.get("reciprocalRunway", reciprocal) != reciprocal:
        raise ValueError("Scenario reciprocal runway does not match its runway")
    setup["reciprocalRunway"] = reciprocal
    return setup


class Catalog:
    def __init__(self, config):
        self.config = config
        if config.scenario_bucket:
            self.s3 = boto3.Session(profile_name=config.aws_profile, region_name=config.aws_region).client("s3")

    def load(self, scenario_id, pinned_ref=None, version=CURRENT_SCENARIO_VERSION):
        if scenario_id not in {"incorrect-readback", "words-versus-actions", "missing-evidence"}:
            raise KeyError(scenario_id)
        if pinned_ref:
            key = pinned_ref["key"]
            match = re.fullmatch(rf"scenarios/{re.escape(scenario_id)}/v([123])/scenario\.json", key)
            if not match:
                raise ValueError("Pinned scenario path is not available")
            version = match.group(1)
        if version not in {"1", "2", "3"}:
            raise ValueError("Scenario version is not available")
        key = f"scenarios/{scenario_id}/v{version}/scenario.json"
        if self.config.scenario_bucket:
            args = {"Bucket": self.config.scenario_bucket, "Key": key}
            if pinned_ref and pinned_ref.get("versionId"):
                args["VersionId"] = pinned_ref["versionId"]
            response = self.s3.get_object(**args)
            data = response["Body"].read()
            ref = {"bucket": self.config.scenario_bucket, "key": key, "versionId": response.get("VersionId")}
        else:
            data = (Path(self.config.scenarios_path) / scenario_id / f"v{version}" / "scenario.json").read_bytes()
            ref = {"key": key, "versionId": None}
        ref["sha256"] = hashlib.sha256(data).hexdigest()
        return json.loads(data), ref

    def list(self):
        return [{**{key: item[key] for key in ("id", "version", "title", "description", "objective")},
                 "initialSetup": scenario_setup(item)}
                for item, _ in [self.load(name) for name in
                                 ["incorrect-readback", "words-versus-actions", "missing-evidence"]]]
