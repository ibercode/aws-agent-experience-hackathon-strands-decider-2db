"""Download the pinned public checkpoint into ignored project-local storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--include-base", action="store_true", help="Cache the pinned base weights for an offline container")
args = parser.parse_args()

root = Path(__file__).resolve().parents[2]
os.environ.setdefault("HF_HOME", str(root / ".data" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from huggingface_hub import snapshot_download

model = json.loads(Path(__file__).with_name("model.json").read_text())
path = snapshot_download(model["repository"], revision=model["revision"], token=False,
                         local_dir=root / ".data" / "models" / "decider-2b")
checkpoint = Path(path)
for line in (checkpoint / "MANIFEST.sha256").read_text().splitlines():
    expected, name = line.split(maxsplit=1)
    target = checkpoint / name.strip().lstrip("*")
    if not target.resolve().is_relative_to(checkpoint.resolve()):
        raise ValueError("Checkpoint manifest references a path outside the checkpoint")
    with target.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"Checkpoint checksum mismatch: {target.name}")
provenance = json.loads((checkpoint / "provenance.json").read_text())
if provenance["base_model_revision"] != model["base_revision"]:
    raise ValueError("Checkpoint base revision does not match model.json")
print(f"Pinned Decider checkpoint verified: {path}")

if args.include_base:
    snapshot_download(model["base_repository"], revision=model["base_revision"], token=False,
                      allow_patterns=list(model["base_file_sha256"]))
    print("Pinned base model cached for offline container preparation")
