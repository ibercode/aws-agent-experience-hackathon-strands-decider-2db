"""Run the official server; containers bind only inside their private task network."""
import json
import os
import platform
from pathlib import Path

root = Path(__file__).resolve().parents[2]
os.environ.setdefault("HF_HOME", str(root / ".data" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from strands_decider.server import serve

checkpoint = Path(os.environ.get("DECIDER_CHECKPOINT", root / ".data" / "models" / "decider-2b"))
if not (checkpoint / "strands_decider_config.json").is_file():
    raise SystemExit("Download the pinned checkpoint first: python services/decider/prepare.py")
model = json.loads(Path(__file__).with_name("model.json").read_text())
device = os.environ.get("DECIDER_DEVICE", "mps" if platform.system() == "Darwin" and platform.machine() == "arm64" else "cpu")
serve(str(checkpoint), host=os.environ.get("DECIDER_HOST", "127.0.0.1"), port=8099, device=device,
      model_name=f"{model['repository']}@{model['revision'][:12]}", strict_window=True, max_batch=1)
