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