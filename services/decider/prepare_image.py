"""Stage only pinned public model files for Docker's separate model context.

No user configuration, local API data, tokens or Hugging Face metadata is copied.
Run prepare.py --include-base first when the public weights are not cached yet.
"""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[2]
model = json.loads(Path(__file__).with_name("model.json").read_text())
checkpoint = root / ".data/models/decider-2b"
cache_name = "models--" + model["base_repository"].replace("/", "--")
base = root / ".data/huggingface/hub" / cache_name / "snapshots" / model["base_revision"]
destination = root / ".data/container-models"

if not checkpoint.is_dir() or not base.is_dir():
    raise SystemExit("Run services/decider/prepare.py --include-base before building the image")
provenance = json.loads((checkpoint / "provenance.json").read_text())
if provenance["base_model_revision"] != model["base_revision"]:
    raise ValueError("Checkpoint provenance does not match the pinned base revision")
if destination.exists():
    shutil.rmtree(destination)

def stage(source: Path, target: Path, expected: str | None = None) -> None:
    if expected:
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Checkpoint checksum mismatch: {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Copy dereferences HF cache symlinks; the output is self-contained.
    shutil.copyfile(source, target)
    target.chmod(0o444)

for line in (checkpoint / "MANIFEST.sha256").read_text().splitlines():
    expected, relative = line.split(maxsplit=1)
    relative = relative.strip().lstrip("*")
    source = checkpoint / relative
    if not source.resolve().is_relative_to(checkpoint.resolve()):
        raise ValueError("Checkpoint manifest contains an unsafe path")
    stage(source, destination / "decider-2b" / relative, expected)
stage(checkpoint / "MANIFEST.sha256", destination / "decider-2b/MANIFEST.sha256")

index = json.loads((base / "model.safetensors.index.json").read_text())
names = {"LICENSE", "config.json", "model.safetensors.index.json", *index["weight_map"].values()}
for name in sorted(names):
    if "/" in name or name.startswith("."):
        raise ValueError("Base model index contains an unsafe path")
    source = base / name
    # Pins also cover cache files reached through nested Hub CAS symlinks.
    digest = model["base_file_sha256"][name]
    stage(source, destination / "huggingface/hub" / cache_name / "snapshots" / model["base_revision"] / name, digest)

print("Staged verified public checkpoint and pinned base weights in .data/container-models")
