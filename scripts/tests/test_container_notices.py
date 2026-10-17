"""Check license download selection and staging integrity without model downloads."""
import hashlib
import json
import runpy
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class ContainerNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = self.root / "services/decider"
        self.service.mkdir(parents=True)
        for name in ("prepare.py", "prepare_image.py"):
            shutil.copyfile(ROOT / "services/decider" / name, self.service / name)
        self.model = json.loads((ROOT / "services/decider/model.json").read_text())
        self.checkpoint = self.root / ".data/models/decider-2b"
        self.checkpoint.mkdir(parents=True)
        provenance = json.dumps({"base_model_revision": self.model["base_revision"]})
        (self.checkpoint / "provenance.json").write_text(provenance)
        checkpoint_license = (ROOT / "LICENSE").read_bytes()
        (self.checkpoint / "LICENSE.md").write_bytes(checkpoint_license)
        digest = hashlib.sha256(checkpoint_license).hexdigest()
        (self.checkpoint / "MANIFEST.sha256").write_text(f"{digest} LICENSE.md\n")
        cache_name = "models--" + self.model["base_repository"].replace("/", "--")
        self.relative_base = Path("huggingface/hub") / cache_name / "snapshots" / self.model["base_revision"]
        self.base = self.root / ".data" / self.relative_base
        self.base.mkdir(parents=True)
        # Small fixtures replace weights; the actual upstream LICENSE is checked
        # separately against its pinned digest during the release verification.
        self.license = b"Example upstream license retained byte for byte.\n"
        contents = {
            "LICENSE": self.license,
            "config.json": b"{}",
            "model.safetensors.index.json": b'{"weight_map":{"weight":"weights.safetensors"}}',
            "weights.safetensors": b"fixture weights",
        }
        self.model["base_file_sha256"] = {}
        for name, content in contents.items():
            (self.base / name).write_bytes(content)
            self.model["base_file_sha256"][name] = hashlib.sha256(content).hexdigest()
        (self.service / "model.json").write_text(json.dumps(self.model))

    def test_pinned_download_includes_every_manifested_base_artifact(self):
        calls = []

        def snapshot(repository, **kwargs):
            calls.append((repository, kwargs))
            return str(self.base if repository == self.model["base_repository"] else self.checkpoint)

        hub = types.ModuleType("huggingface_hub")
        hub.snapshot_download = snapshot
        with (
            patch.dict(sys.modules, {"huggingface_hub": hub}),
            patch.dict("os.environ"),
            patch.object(sys, "argv", ["prepare.py", "--include-base"]),
        ):
            runpy.run_path(str(self.service / "prepare.py"), run_name="__main__")
        repository, options = calls[-1]
        self.assertEqual(repository, self.model["base_repository"])
        self.assertEqual(options["revision"], self.model["base_revision"])
        self.assertFalse(options["token"])
        self.assertEqual(set(options["allow_patterns"]), set(self.model["base_file_sha256"]))
        self.assertIn("LICENSE", options["allow_patterns"])

    def test_base_license_is_staged_unmodified_and_read_only(self):
        runpy.run_path(str(self.service / "prepare_image.py"), run_name="__main__")
        staged = self.root / ".data/container-models" / self.relative_base / "LICENSE"
        self.assertEqual(staged.read_bytes(), self.license)
        self.assertEqual(staged.stat().st_mode & 0o777, 0o444)
        self.assertTrue((self.root / ".data/container-models/decider-2b/LICENSE.md").is_file())

    def test_changed_base_license_fails_integrity_check(self):
        (self.base / "LICENSE").write_bytes(b"Altered license")
        with self.assertRaisesRegex(ValueError, "checksum mismatch: LICENSE"):
            runpy.run_path(str(self.service / "prepare_image.py"), run_name="__main__")


if __name__ == "__main__":
    unittest.main()
