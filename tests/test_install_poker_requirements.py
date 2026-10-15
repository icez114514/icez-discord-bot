"""Resolve Android requirements with real pip and an offline wheel index."""

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
    def test_android_resolution_uses_core_wheel_without_desktop_native_pins(self):
        source = Path(__file__).resolve().parents[1] / "poker"
        files = {}

        def collect(name):
            text = (source / name).read_text("utf-8")
            files[name] = text
            for line in text.splitlines():
                if line.startswith("-r "):
                    collect(line[3:].strip())

        collect("requirements-termux.txt")
        requirements = files["requirements-termux.txt"]
        direct = next(
            line for line in requirements.splitlines()
            if line.startswith("pydantic-core @ ")
        )
        core_pin = next(
            line for text in files.values() for line in text.splitlines()
            if re.match(r"pydantic[_-]core==", line)
        )
        version = core_pin.split("==", 1)[1]
        filename = direct.split(" @ ", 1)[1].split("#", 1)[0].rsplit("/", 1)[1]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            wheel = fixture / "artifacts" / filename
            wheel.parent.mkdir()
            self.make_wheel(wheel, "pydantic_core", version, "cp314-cp314-android_24_arm64_v8a")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            # Mirror the full include graph and order, replacing only the URL.
            local = "pydantic-core @ " + wheel.as_uri() + "#sha256=" + digest
            for name, text in files.items():
                (fixture / name).write_text(text.replace(direct, local), encoding="utf-8")
            index = fixture / "index"
            index.mkdir()
            # Termux owns these packages. No Android wheels are provided here;
            # a desktop pin leaking into this graph must fail real resolution.
            system_packages = {"numpy", "cryptography", "cffi", "pycparser"}
            for text in files.values():
                for name, pinned in re.findall(r"^([\w-]+)==([^;\s]+)", text, re.MULTILINE):
                    canonical = name.lower().replace("_", "-")
                    if canonical in system_packages or canonical == "pydantic-core":
                        continue
                    normalized = name.replace("-", "_")
                    target = index / f"{normalized}-{pinned}-py3-none-any.whl"
                    self.make_wheel(target, normalized, pinned, "py3-none-any")
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip", "--isolated", "download",
                    "--disable-pip-version-check", "--no-index", "--no-cache-dir",
                    "--find-links", str(index),
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

    @staticmethod
    def make_wheel(path, name, version, tag):
        info = f"{name}-{version}.dist-info"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                info + "/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            )
            archive.writestr(
                info + "/WHEEL",
                f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n",
            )
            archive.writestr(info + "/RECORD", "")


if __name__ == "__main__":
    unittest.main()
