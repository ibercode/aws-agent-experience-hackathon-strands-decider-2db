"""Delivery-status example: prewritten candidate drafts, real Decider decisions."""
import argparse
import json
from types import MappingProxyType

from guard import DeciderClient, check_finding, request_for

SOURCES = MappingProxyType({"dispatch_record": "Parcel BOX42 was dispatched."})
CANDIDATES = [
    {"text": "Parcel BOX42 was delivered to the customer.", "evidence_keys": ["dispatch_record"]},
    {"text": "Parcel BOX42 was dispatched.", "evidence_keys": ["dispatch_record"]},
]


def run_candidates(candidates, sources, decide, max_attempts=2):
    """Bounded single-finding flow. Print-only publication from immutable sources."""
    if not 1 <= max_attempts <= 2:
        raise ValueError("This small example allows one or two attempts")
    sources = MappingProxyType(dict(sources))
    attempts, seen = [], set()
    for finding in candidates:
        if len(attempts) >= max_attempts:
            break
        fingerprint = json.dumps(finding, sort_keys=True)
        if fingerprint in seen:
            return {"action": "withhold", "reason": "unchanged_rejected_finding", "attempts": attempts}
        seen.add(fingerprint)
        result = check_finding(finding, sources, decide)
        attempts.append({"proposed_finding": finding, **result.to_dict()})
        if result.action == "allow":
            return {"action": "publish", "published_text": result.checked_text, "attempts": attempts}
        if result.action == "withhold":
            return {"action": "withhold", "reason": result.reason, "attempts": attempts}
        # In an agent, ask Bedrock to revise using result.reason and fresh sources.
        # Here the next candidate is prewritten, so no generative model is needed.
    return {"action": "withhold", "reason": "revision_limit_reached", "attempts": attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show requests only; no inference or network")
    mode.add_argument("--live", action="store_true", help="Call your running Decider service (at most twice)")
    parser.add_argument("--url", default="http://127.0.0.1:8099", help="Your local/private service base URL")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "inference": False,
                          "note": "Prewritten candidate drafts; no model answers or timings are fabricated.",
                          "requests": [request_for(finding, SOURCES) for finding in CANDIDATES]}, indent=2))
        return 0
    try:
        client = DeciderClient(args.url, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    result = run_candidates(CANDIDATES, SOURCES, client)
    print(json.dumps({"mode": "live-decider", "drafts": "prewritten; no Bedrock call",
                      "publication": "stdout only; no message is sent", **result}, indent=2))
    return 0 if result["action"] == "publish" else 2


if __name__ == "__main__":
    raise SystemExit(main())
