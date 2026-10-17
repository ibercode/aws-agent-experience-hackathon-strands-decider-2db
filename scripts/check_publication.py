"""Check Git's publication set for private files and common identity/secret leaks.

Reports contain paths, line numbers and categories, never matched values.
Pair this scoped check with Gitleaks and manual review before publication.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PRIVATE_PARTS = {".data", ".aws", ".ssh", ".codex", ".agents", ".venv", ".terraform",
                 "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}
LICENSE_FILES = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "frontend/public/third-party-notices.txt"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "provider_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
    "private_home_path": re.compile(r"/(?:Users|home)/[^/\s]+|[A-Z]:\\Users\\[^\\\s]+"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})", re.I),
    "aws_account_arn": re.compile(r"arn:(?:aws|aws-cn|aws-us-gov):[^:\s]+:[^:\s]*:(\d{12}):"),
    "cognito_pool": re.compile(r"\b(?:eu|us|ap|sa|ca|me|af)-(?:west|east|south|north|central|southeast|northeast)-\d_([A-Za-z0-9]{6,})"),
}


def private_path(name):
    path = Path(name)
    return (bool(set(path.parts) & PRIVATE_PARTS)
            or name == "docs/hackathon-submission-checklist.md"
            or (path.name.startswith(".env") and path.name != ".env.example")
            or path.name == "backend.hcl" or path.name.startswith("credentials")
            or re.search(r"\.(?:tfstate|tfplan)(?:\.|$)", path.name) is not None
            or path.name.endswith((".tfvars", ".tfvars.json", ".pem", ".key", ".p12", ".pfx",
                                   ".keystore", ".db", ".sqlite", ".sqlite3", ".log")))


def scan_text(name, text):
    findings = []
    is_test = name.startswith(("backend/tests/", "scripts/tests/"))
    for category, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            if category == "email":
                domain = match.group(1).lower()
                if (name in LICENSE_FILES or domain.endswith((".test", ".invalid", "users.noreply.github.com"))
                        or domain in {"example.com", "example.org", "example.net"}):
                    continue
            if category == "aws_account_arn" and is_test and match.group(1) == "123456789012":
                continue  # Explicit fictional redaction fixture, not an account in deployment config.
            if category == "cognito_pool" and is_test and match.group(1) == "example":
                continue
            findings.append((name, text.count("\n", 0, match.start()) + 1, category))
    return findings


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)


def check(staged=False):
    args = ["ls-files", "--cached", "-z"]
    if not staged:
        args.extend(["--others", "--exclude-standard"])
    names = sorted(set(name for name in git(*args).decode().split("\0") if name))
    findings = []
    for name in names:
        if private_path(name):
            findings.append((name, 0, "private_file"))
            continue
        if staged:
            mode = git("ls-files", "--stage", "--", name).split(b" ", 1)[0]
            if mode == b"120000":
                findings.append((name, 0, "symlink_requires_review"))
                continue
            raw = git("show", ":" + name)  # Inspect the actual staged blob, not a later working-tree edit.
        else:
            if Path(name).is_symlink():
                findings.append((name, 0, "symlink_requires_review"))
                continue
            raw = Path(name).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # Binary metadata needs separate review; do not silently re-encode assets.
        findings.extend(scan_text(name, text))
    return names, sorted(set(findings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Read exact index blobs before committing")
    args = parser.parse_args()
    try:
        names, findings = check(args.staged)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Publication check could not complete: {type(exc).__name__}", file=sys.stderr)
        return 2
    for name, line, category in findings:
        print(f"{name}:{line}: {category} (value withheld)")
    print(f"Reviewed {len(names)} Git publication files; {len(findings)} potential privacy/secret findings.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
