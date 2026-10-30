"""Installer regression tests; no host Docker configuration is modified."""
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def bash(self, command, env=None):
        return subprocess.run(["bash", "-c", 'source "$1"; ' + command, "test", str(ROOT / "install.sh")], env={**os.environ, **(env or {})}, text=True, capture_output=True)

    def test_port_boundaries(self):
        for value in ("1", "80", "080", "65535"):
            self.assertEqual(self.bash('validate_port "$VALUE"', {"VALUE": value}).returncode, 0)
        for value in ("0", "65536", "-1", "1;true", "80/tcp", "999999"):
            self.assertNotEqual(self.bash('validate_port "$VALUE"', {"VALUE": value}).returncode, 0)

    def test_paths_do_not_allow_system_targets_or_traversal(self):
        for value in ("/", "/etc/heli", "/usr/local/monitor", "/tmp/../etc", "/tmp/a b", "relative", "/tmp/a$HOME"):
            self.assertNotEqual(self.bash('normalize_dir "$VALUE"', {"VALUE": value}).returncode, 0, value)
        result = self.bash('normalize_dir /opt/monitor/')
        self.assertEqual(result.stdout, "/opt/monitor")

    def test_defaults_and_password_not_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.bash('ENGINE_PRESENT=0; INTERACTIVE=0; collect_settings; printf "RESULT:%s:%s:%s" "$DOCKER_DATA_ROOT" "$NGINX_PORT" "$ADMIN_USERNAME"', {"ADMIN_PASSWORD": "Synthetic-Only!2026", "DATA_DIR": tmp + "/data"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RESULT:/var/lib/docker:80:admin", result.stdout)
            self.assertNotIn("Synthetic-Only!2026", result.stdout + result.stderr)

    def test_existing_install_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"; app.mkdir(); (app / ".env").write_text("preserved=yes")
            result = self.bash('ENGINE_PRESENT=1; INTERACTIVE=0; collect_settings', {"DATA_DIR": tmp, "ADMIN_PASSWORD": "Synthetic-Only!2026"})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((app / ".env").read_text(), "preserved=yes")

    def test_environment_is_private_and_never_contains_login_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            result = subprocess.run([sys.executable, str(ROOT / "write-env.py"), str(env_file), tmp, "18083", "v1.0.3"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = env_file.read_text()
            self.assertIn("DATA_DIR=" + tmp, text)
            self.assertNotIn("ADMIN_PASSWORD", text)
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
            again = subprocess.run([sys.executable, str(ROOT / "write-env.py"), str(env_file), tmp, "18083", "v1.0.3"], capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(env_file.read_text(), text)

    def test_docker_json_preserves_other_options_and_refuses_old_data_relocation(self):
        original_path = Path
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "daemon.json"
            old = Path(tmp) / "old"; old.mkdir()
            new = Path(tmp) / "new"; new.mkdir()
            config.write_text(json.dumps({"data-root": str(old), "log-driver": "json-file", "log-opts": {"max-size": "10m"}}))
            def route_path(value):
                return config if str(value) == "/etc/docker/daemon.json" else original_path(value)
            with patch("pathlib.Path", side_effect=route_path), patch.object(sys, "argv", ["configure-docker.py", str(new)]):
                runpy.run_path(str(ROOT / "configure-docker.py"), run_name="__main__")
            values = json.loads(config.read_text())
            self.assertEqual(values["data-root"], str(new))
            self.assertEqual(values["log-opts"]["max-size"], "10m")
            (new / "existing").write_text("keep")
            with patch("pathlib.Path", side_effect=route_path), patch.object(sys, "argv", ["configure-docker.py", str(old)]):
                with self.assertRaises(SystemExit):
                    runpy.run_path(str(ROOT / "configure-docker.py"), run_name="__main__")
            self.assertEqual(json.loads(config.read_text()), values)

    def test_existing_docker_branch_does_not_install_or_reconfigure(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"; bin_dir.mkdir()
            for name, body in {"docker": '#!/bin/sh\nif [ "$1" = info ] && [ "$2" = --format ]; then echo /var/lib/existing-docker; fi\nexit 0\n', "systemctl": '#!/bin/sh\nexit 0\n', "dnf": '#!/bin/sh\necho unexpected-install >&2\nexit 77\n'}.items():
                path = bin_dir / name; path.write_text(body); path.chmod(0o755)
            result = self.bash('ENGINE_PRESENT=1; DATA_DIR=/opt/monitor-test; install_docker', {"PATH": str(bin_dir) + ":" + os.environ["PATH"]})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("/var/lib/existing-docker", result.stdout)
            self.assertNotIn("unexpected-install", result.stderr)

    def test_missing_docker_branch_installs_before_setting_data_root_and_starting(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"; bin_dir.mkdir()
            events = Path(tmp) / "events"
            commands = {
                "mkdir": '#!/bin/sh\necho mkdir >> "$MOCK_EVENTS"\n',
                "cp": '#!/bin/sh\necho backup >> "$MOCK_EVENTS"\n',
                "tar": '#!/bin/sh\ntouch "$MOCK_ROOT/fake.rpm"\n',
                "dnf": '#!/bin/sh\nprintf "dnf %s\\n" "$*" >> "$MOCK_EVENTS"\n',
                "systemctl": '#!/bin/sh\nprintf "systemctl %s\\n" "$*" >> "$MOCK_EVENTS"\n',
                "configure-test-python": '#!/bin/sh\nprintf "configure %s\\n" "$2" >> "$MOCK_EVENTS"\n',
                "docker": '#!/bin/sh\nif [ "$1" = info ] && [ "$2" = --format ]; then echo /var/lib/mock-docker; fi\nexit 0\n',
            }
            for name, body in commands.items():
                path = bin_dir / name; path.write_text(body); path.chmod(0o755)
            result = self.bash('check_el9(){ :; }; ENGINE_PRESENT=0; TEMP_DIR="$MOCK_ROOT"; DOCKER_DATA_ROOT=/var/lib/mock-docker; DATA_DIR=/opt/monitor-test; PYTHON=configure-test-python; install_docker', {"PATH": str(bin_dir) + ":" + os.environ["PATH"], "MOCK_ROOT": tmp, "MOCK_EVENTS": str(events)})
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = events.read_text().splitlines()
            install = next(i for i, line in enumerate(lines) if line.startswith("dnf "))
            configure = lines.index("configure /var/lib/mock-docker")
            start = lines.index("systemctl enable --now docker")
            self.assertLess(install, configure)
            self.assertLess(configure, start)
            self.assertIn("--disablerepo=*", lines[install])
            self.assertIn("--disableplugin=*", lines[install])



if __name__ == "__main__":
    unittest.main(verbosity=2)
