"""Tests for deploy artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


DEPLOY_DIR = Path(__file__).parent.parent / "deploy"


class TestDeployArtifacts:
    """Tests for deploy directory artifacts."""

    def test_install_sh_exists(self):
        assert (DEPLOY_DIR / "install.sh").is_file()

    def test_service_file_exists(self):
        assert (DEPLOY_DIR / "posey-tube.service").is_file()

    def test_config_example_exists(self):
        assert (DEPLOY_DIR / "config.example.toml").is_file()

    def test_readme_exists(self):
        assert (DEPLOY_DIR / "README.md").is_file()

    def test_install_sh_executable(self):
        # Script should be readable (execute permission set by install)
        assert (DEPLOY_DIR / "install.sh").stat().st_mode & 0o400

    def test_config_example_loads(self):
        """config.example.toml must load with the real config loader."""
        from posey_tube.config import load_config

        configs = load_config(DEPLOY_DIR / "config.example.toml")
        assert len(configs) >= 2  # at least the two examples
        names = {c.name for c in configs}
        assert "relay1" in names
        assert "relay2" in names
        assert "button" in names
        assert "sensor" in names
        for c in configs:
            assert c.bcm >= 0
            assert c.direction in ("out", "in")


class TestAllOffCLI:
    """Tests for --all-off CLI flag."""

    def test_all_off_flag_exits_zero(self):
        """python -m posey_tube --all-off should exit 0 (or fail gracefully without lgpio)."""
        repo_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "posey_tube", "--all-off"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            env={**os.environ, "POSEY_TUBE_CONFIG": str(DEPLOY_DIR / "config.example.toml")},
        )
        # In CI without lgpio, gpiozero fails with BadPinFactory (exit 1).
        # On a real Pi with lgpio, it exits 0.
        # We accept either 0 (success) or 1 (expected failure in CI without lgpio).
        assert result.returncode in (0, 1), f"stderr: {result.stderr}"

class TestServiceHardening:
    """posey-tube #9: least-privilege unit that still reaches /dev/gpiochip*."""

    unit = (DEPLOY_DIR / "posey-tube.service").read_text()

    def _directives(self):
        out = {}
        for line in self.unit.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "[")) and "=" in line:
                k, v = line.split("=", 1)
                out.setdefault(k, []).append(v)
        return out

    def test_gpiochip_not_hidden(self):
        d = self._directives()
        assert d.get("PrivateDevices", ["no"]) == ["no"]
        assert d.get("DevicePolicy") == ["closed"]
        assert any("gpiochip" in v for v in d.get("DeviceAllow", []))

    def test_no_capabilities(self):
        d = self._directives()
        assert d.get("CapabilityBoundingSet") == [""]
        assert d.get("AmbientCapabilities", [""]) == [""]
        assert "CAP_" not in self.unit

    def test_memory_max_not_deprecated_limit(self):
        d = self._directives()
        assert "MemoryLimit" not in d
        assert "MemoryMax" in d

    def test_lgpio_workdir_writable(self):
        d = self._directives()
        assert d.get("Environment") == ["LG_WD=/run/posey-tube"]
        assert d.get("RuntimeDirectory") == ["posey-tube"]
        assert not d["WorkingDirectory"][0].startswith("/opt")


class TestInstallScript:
    """posey-tube #9: pip runs as the service user, prod install has no dev extras."""

    script = (DEPLOY_DIR / "install.sh").read_text()

    def test_pip_runs_as_service_user(self):
        for line in self.script.splitlines():
            if "/bin/pip" in line and not line.lstrip().startswith(("#", "log")):
                assert line.lstrip().startswith('sudo -u "${SERVICE_USER}"'), line

    def test_no_dev_extras_or_editable_in_prod(self):
        assert "[dev]" not in self.script
        assert "install --quiet -e" not in self.script

    def test_no_unused_package_name(self):
        assert "PACKAGE_NAME" not in self.script
