#!/usr/bin/env python3
"""Run Terraform with short-lived AWS CLI profile credentials, held only in memory.

AWS CLI and Terraform can refresh SSO caches differently. This keeps the chosen
profile authoritative without writing credentials into Terraform configuration.
Run from the Terraform directory: python ../../scripts/terraform_with_profile.py
--profile YOUR_PROFILE plan -out=... . Do not set provider/backend profile fields
when using this wrapper, since they override the supplied credential chain.
"""
import argparse
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("terraform_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.terraform_args:
        parser.error("Pass a Terraform command")
    result = subprocess.run(
        ["aws", "--profile", args.profile, "configure", "export-credentials", "--format", "process"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        print("AWS profile credentials are unavailable. Refresh your AWS CLI SSO login.", file=sys.stderr)
        return result.returncode
    credentials = json.loads(result.stdout)
    env = os.environ.copy()
    env.pop("AWS_PROFILE", None)
    env.pop("AWS_DEFAULT_PROFILE", None)
    env.update(AWS_ACCESS_KEY_ID=credentials["AccessKeyId"],
               AWS_SECRET_ACCESS_KEY=credentials["SecretAccessKey"],
               AWS_SESSION_TOKEN=credentials.get("SessionToken", ""))
    return subprocess.call(["terraform", *args.terraform_args], env=env)


if __name__ == "__main__":
    sys.exit(main())
