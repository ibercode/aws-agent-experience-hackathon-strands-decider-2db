"""Read-only DynamoDB recording through the AWS CLI; never starts model inference.

Private captures deliberately include the original records. They are restricted to
the repository's ignored .data/recordings directory and MUST NOT be published.
Use export_replays.py to create a separately validated public artifact.
"""
import argparse
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {"incorrect-readback", "words-versus-actions", "missing-evidence"}
PRESETS = {"missed", "partial", "complete"}
CONSISTENCY = "meta-before-query-meta-after"


class ReadError(Exception):
    """Contains only a safe error category, never CLI response bodies."""


def stamp():
    return datetime.now(UTC).isoformat()


def aws_read(operation, parameters, profile, region):
    if operation not in {"scan", "query", "get-item"}:
        raise ReadError("OperationNotAllowed")
    command = ["aws", "--profile", profile, "--region", region, "--output", "json",
               "--no-cli-pager", "dynamodb", operation, "--cli-input-json", json.dumps(parameters)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False,
                                env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"})
    except subprocess.TimeoutExpired as exc:
        raise ReadError("CliTimeout") from exc
    except OSError as exc:
        raise ReadError("CliUnavailable") from exc
    if result.returncode:
        match = re.search(r"An error occurred \(([A-Za-z0-9_.-]{1,80})\)", result.stderr)
        raise ReadError(match.group(1) if match else "CliFailure")
    try:
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise TypeError()
        return value
    except (ValueError, TypeError) as exc:
        raise ReadError("InvalidCliResponse") from exc


def decode(value):
    if "S" in value:
        return value["S"]
    if "N" in value:
        number = value["N"]
        return float(number) if any(c in number for c in ".eE") else int(number)
    if "BOOL" in value:
        return value["BOOL"]
    if "NULL" in value:
        return None
    if "M" in value:
        return {key: decode(item) for key, item in value["M"].items()}
    if "L" in value:
        return [decode(item) for item in value["L"]]
    raise ReadError("UnsupportedDynamoType")


def decode_item(item):
    return {key: decode(value) for key, value in item.items()}


def pages(operation, parameters, args):
    records = []
    while True:
        page = aws_read(operation, parameters, args.profile, args.region)
        records.extend(decode_item(row) for row in page.get("Items", []))
        if not page.get("LastEvaluatedKey"):
            return records
        parameters = {**parameters, "ExclusiveStartKey": page["LastEvaluatedKey"]}


def discover(args, since):
    return pages("scan", {
        "TableName": args.table, "ConsistentRead": True,
        "FilterExpression": "SK = :meta AND createdAt >= :since AND scenarioVersion = :version",
        "ProjectionExpression": "PK, SK, sessionId, scenarioId, scenarioVersion, preset, providerMode, createdAt",
        "ExpressionAttributeValues": {":meta": {"S": "META"}, ":since": {"S": since},
                                      ":version": {"S": args.version}},
    }, args)


def partition(args, session_id):
    pk = f"SESSION#{session_id}"
    meta_args = {
        "TableName": args.table, "ConsistentRead": True,
        "Key": {"PK": {"S": pk}, "SK": {"S": "META"}},
        "ProjectionExpression": "revision",
    }
    before = decode_item(aws_read("get-item", meta_args, args.profile, args.region).get("Item", {}))
    records = pages("query", {
        "TableName": args.table, "ConsistentRead": True,
        "KeyConditionExpression": "PK = :pk", "ExpressionAttributeValues": {":pk": {"S": pk}},
    }, args)
    meta = next((row for row in records if row.get("SK") == "META"), None)
    if not meta:
        return None
    # Query is read-committed, not an atomic multi-item snapshot. Checking both
    # boundaries catches changes before Query reaches the META row as well.
    after = aws_read("get-item", meta_args, args.profile, args.region)
    after_meta = decode_item(after.get("Item", {}))
    return records if before.get("revision") == meta.get("revision") == after_meta.get("revision") else None


def private_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def write_json(file, value):
    file.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")
    file.flush()


def resume_capture(output, args):
    """Reopen only unfinished files in append mode; original bytes stay untouched."""
    try:
        metadata = json.loads((output / "capture.json").read_text(encoding="utf-8"))
        if (metadata["schemaVersion"] != "atc-assistant-private-recording/1"
                or metadata["scenarioVersion"] != args.version or metadata["expectedCases"] != args.cases):
            raise ReadError("ResumeConfigurationMismatch")
        started = metadata["startedAt"]
        elapsed_offset = (datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds() * 1000
        active, seen_cases, finished = {}, set(), set()
        for path in sorted(output.glob("*.jsonl")):
            if path.is_symlink():
                raise ReadError("ResumeSymlinkNotAllowed")
            frames = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not frames:
                raise ReadError("CannotResumeEmptyCapture")
            last = frames[-1]
            meta = next(row for row in last["records"] if row.get("SK") == "META")
            case = (meta["scenarioId"], meta["preset"])
            slug = f"{case[0]}-v{args.version}-{case[1]}"
            if (case[0] not in SCENARIOS or case[1] not in PRESETS or meta["providerMode"] != "live"
                    or meta["scenarioVersion"] != args.version or path.stem != slug or case in seen_cases):
                raise ReadError("ResumeCaptureIdentityMismatch")
            seen_cases.add(case)
            if meta["status"] in {"completed", "cancelled", "failed"}:
                finished.add(slug)
                continue
            gap = (datetime.now(UTC) - datetime.fromisoformat(last["observedAt"])).total_seconds() * 1000
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
            active[meta["sessionId"]] = {"slug": slug, "revision": meta["revision"],
                                        "file": os.fdopen(descriptor, "a", encoding="utf-8"),
                                        "frames": len(frames), "started": time.monotonic(),
                                        "elapsedOffset": last.get("captureElapsedMs", 0) + max(0, gap)}
        index = len(list(output.glob("resume-*.json"))) + 1
        with private_file(output / f"resume-{index:04d}.json") as file:
            write_json(file, {"resumedAt": stamp(), "consistencyStrategy": CONSISTENCY,
                              "finishedCases": len(finished), "activeCases": len(active),
                              "pollIntervalMs": round(args.poll * 1000),
                              "elapsedTimeBasis": "Monotonic within each process; wall-clock bridge across restart.",
                              "previousFramesUnchanged": True})
        return started, elapsed_offset, active, seen_cases, finished
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as exc:
        raise ReadError("InvalidResumeCapture") from exc


def run(args):
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / ".data" / "recordings").resolve()):
        raise ReadError("OutputMustBeInsideIgnoredRecordingsDirectory")
    if args.resume:
        started, elapsed_offset, active, seen_cases, finished = resume_capture(output, args)
    else:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(output, 0o700)
        started, elapsed_offset = args.since or stamp(), 0
        active, seen_cases, finished = {}, set(), set()
        with private_file(output / "capture.json") as file:
            write_json(file, {"schemaVersion": "atc-assistant-private-recording/1",
                              "source": "dynamodb-revision-poll", "startedAt": started,
                              "consistencyStrategy": CONSISTENCY,
                              "pollIntervalMs": round(args.poll * 1000),
                              "discoveryIntervalMs": round(args.discover * 1000),
                              "scenarioVersion": args.version, "expectedCases": args.cases,
                              "timingNote": "Observed persisted revisions; transitions between polls may be missed."})
    start_clock = time.monotonic()
    next_discovery, consecutive_errors = 0.0, 0
    print(json.dumps({"status": "ready", "expectedCases": args.cases,
                      "resumed": args.resume, "capturedCases": len(finished),
                      "consistencyStrategy": CONSISTENCY}), flush=True)
    try:
        while len(finished) < args.cases and time.monotonic() - start_clock < args.timeout:
            cycle = time.monotonic()
            try:
                if cycle >= next_discovery:
                    for meta in sorted(discover(args, started), key=lambda item: item["createdAt"]):
                        case = (meta.get("scenarioId"), meta.get("preset"))
                        if (meta.get("providerMode") != "live" or case[0] not in SCENARIOS
                                or case[1] not in PRESETS or case in seen_cases):
                            continue
                        slug = f"{case[0]}-v{args.version}-{case[1]}"
                        active[meta["sessionId"]] = {"slug": slug, "revision": None,
                                                    "file": private_file(output / f"{slug}.jsonl"),
                                                    "frames": 0, "started": time.monotonic()}
                        seen_cases.add(case)
                        print(json.dumps({"status": "recording", "case": slug}), flush=True)
                    next_discovery = time.monotonic() + args.discover
                for session_id, capture in list(active.items()):
                    records = partition(args, session_id)
                    if records is None:
                        continue
                    meta = next(row for row in records if row.get("SK") == "META")
                    if meta["revision"] != capture["revision"]:
                        write_json(capture["file"], {
                            "observedAt": stamp(),
                            "elapsedMs": round(elapsed_offset + (time.monotonic() - start_clock) * 1000),
                            "captureElapsedMs": round(capture.get("elapsedOffset", 0)
                                                      + (time.monotonic() - capture["started"]) * 1000),
                            "consistencyStrategy": CONSISTENCY,
                            "records": records,
                        })
                        capture["revision"] = meta["revision"]
                        capture["frames"] += 1
                    if meta["status"] in {"completed", "cancelled", "failed"}:
                        capture["file"].close()
                        finished.add(capture["slug"])
                        del active[session_id]
                        print(json.dumps({"status": "captured", "case": capture["slug"],
                                          "sessionStatus": meta["status"],
                                          "frames": capture["frames"]}), flush=True)
                consecutive_errors = 0
            except ReadError as exc:
                consecutive_errors += 1
                print(json.dumps({"status": "read-retry", "error": str(exc)}), flush=True)
                if consecutive_errors >= 5:
                    raise
            time.sleep(max(0.05, args.poll - (time.monotonic() - cycle)))
    finally:
        for capture in active.values():
            capture["file"].close()
    complete = len(finished) == args.cases
    print(json.dumps({"status": "complete" if complete else "capture-timeout",
                      "capturedCases": len(finished), "expectedCases": args.cases}), flush=True)
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="3", choices=["1", "2", "3"])
    parser.add_argument("--cases", type=int, default=9)
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--discover", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--since", help="Optional UTC ISO cutoff for already-created sessions")
    parser.add_argument("--resume", action="store_true", help="Append unfinished captures; preserve completed files")
    args = parser.parse_args()
    if not 1 <= args.cases <= 9 or args.poll < 0.1 or args.discover < 0.1 or args.timeout <= 0:
        parser.error("Invalid capture limits")
    try:
        return run(args)
    except (ReadError, FileExistsError, KeyboardInterrupt) as exc:
        print(json.dumps({"status": "stopped", "error": str(exc) if isinstance(exc, ReadError)
                          else type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
