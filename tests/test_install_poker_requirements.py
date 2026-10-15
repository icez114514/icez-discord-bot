"""Resolve the Termux core wheel with real pip, without network or installation."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


class TermuxRequirementsTests(unittest.TestCase):
    def test_direct_android_wheel_resolves_before_shared_version_pin(self):
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "poker/requirements-termux.txt").read_text("utf-8")
        direct = next(
            line for line in requirements.splitlines()
            if line.startswith("pydantic-core @ ")
        )
        core_pin = next(
            line for line in (root / "poker/requirements.txt").read_text("utf-8").splitlines()
            if re.match(r"pydantic[_-]core==", line)
        )
        version = core_pin.split("==", 1)[1]
        filename = direct.split(" @ ", 1)[1].split("#", 1)[0].rsplit("/", 1)[1]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            wheel = fixture / "artifacts" / filename
            wheel.parent.mkdir()
            info = f"pydantic_core-{version}.dist-info"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    info + "/METADATA",
                    f"Metadata-Version: 2.1\nName: pydantic_core\nVersion: {version}\n",
                )
                archive.writestr(
                    info + "/WHEEL",
                    "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
                    "Tag: cp314-cp314-android_24_arm64_v8a\n",
                )
                archive.writestr(info + "/RECORD", "")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            # Preserve the repository's include order, replacing only its URL.
            local = "pydantic-core @ " + wheel.as_uri() + "#sha256=" + digest
            (fixture / "requirements-termux.txt").write_text(
                requirements.replace(direct, local), encoding="utf-8"
            )
            (fixture / "requirements.txt").write_text(core_pin + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip", "--isolated", "download",
                    "--disable-pip-version-check", "--no-index", "--no-cache-dir",
                    "--no-deps", "--only-binary=:all:",
                    "--platform", "android_24_arm64_v8a",
                    "--python-version", "3.14", "--implementation", "cp", "--abi", "cp314",
                    "--dest", str(fixture / "downloads"),
                    "-r", str(fixture / "requirements-termux.txt"),
                ],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-4000:])
            self.assertTrue((fixture / "downloads" / filename).is_file())


if __name__ == "__main__":
    unittest.main()
