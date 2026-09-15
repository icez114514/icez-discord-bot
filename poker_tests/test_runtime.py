import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import httpx


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class RuntimeTests(unittest.TestCase):
    def test_cli_migrate_two_listeners_and_second_instance_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = free_port(), free_port()
            while first == second:
                second = free_port()
            env = {
                **os.environ,
                "POKER_ENV": "test",
                "POKER_DATA_DIR": directory,
                "POKER_ORIGIN": "http://127.0.0.1:" + str(first),
                "POKER_CLIENT_ID": "123",
                "POKER_GUILD_ID": "456",
                "POKER_CLIENT_SECRET": "s" * 32,
                "POKER_BOT_TOKEN": "b" * 32,
                "POKER_READER_TOKEN": "r" * 32,
                "POKER_FUNDS_TOKEN": "f" * 32,
                "POKER_PUBLIC_PORT": str(first),
                "POKER_INTERNAL_PORT": str(second),
            }
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(
                [sys.executable, "-m", "poker", "migrate"],
                env=env,
                capture_output=True,
                timeout=10,
                creationflags=flags,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            process = subprocess.Popen(
                [sys.executable, "-m", "poker", "serve"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
            try:
                deadline = time.monotonic() + 10
                with httpx.Client(timeout=0.5, trust_env=False) as client:
                    while True:
                        try:
                            public = client.get(
                                "http://127.0.0.1:" + str(first) + "/health"
                            )
                            internal = client.get(
                                "http://127.0.0.1:" + str(second) + "/scans",
                                headers={"Authorization": "Bearer " + "r" * 32},
                            )
                            if (
                                public.status_code == 200
                                and internal.status_code == 200
                            ):
                                break
                        except httpx.HTTPError:
                            pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail("CLI listeners did not become ready")
                        time.sleep(0.05)
                    self.assertEqual(public.json()["schema"], 3)
                    self.assertEqual(
                        client.get("http://127.0.0.1:" + str(first) + "/").status_code,
                        200,
                    )
                    duplicate = subprocess.run(
                        [sys.executable, "-m", "poker", "migrate"],
                        env=env,
                        capture_output=True,
                        timeout=5,
                        creationflags=flags,
                    )
                    self.assertNotEqual(duplicate.returncode, 0)
            finally:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                        creationflags=flags,
                    )
                else:
                    process.terminate()
                process.wait(10)
                process.stdout.close()
                process.stderr.close()
            restart = subprocess.run(
                [sys.executable, "-m", "poker", "migrate"],
                env=env,
                capture_output=True,
                timeout=5,
                creationflags=flags,
            )
            self.assertEqual(restart.returncode, 0)
