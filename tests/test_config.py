"""Tests for config.py loader and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from posey_tube.config import load_config, load_token, ConfigError, DEFAULT_CONFIG_PATH, DEFAULT_SECRETS_PATH
from posey_tube.pins import PinConfig


class TestConfigLoader:
    """Tests for load_config() and validation."""

    def _write_config(self, content: str) -> Path:
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        tf.write(content)
        tf.close()
        return Path(tf.name)

    def test_valid_config_loads(self):
        cfg = self._write_config("""
[pins.led]
bcm = 17
direction = "out"
active_high = false
max_on_s = 600
label = "Desk lamp"

[pins.btn]
bcm = 27
direction = "in"
pull = "up"
""")
        try:
            pins = load_config(cfg)
            assert len(pins) == 2
            assert pins[0].name == "led"
            assert pins[0].bcm == 17
            assert pins[0].direction == "out"
            assert pins[0].active_high is False
            assert pins[0].max_on_s == 600
            assert pins[0].label == "Desk lamp"
            assert pins[1].name == "btn"
            assert pins[1].bcm == 27
            assert pins[1].direction == "in"
            assert pins[1].pull == "up"
            assert pins[1].max_on_s is None
        finally:
            cfg.unlink()

    def test_missing_config_file_raises(self):
        with pytest.raises(ConfigError, match="Config file not found"):
            load_config(Path("/nonexistent/path.toml"))

    def test_invalid_toml_raises(self):
        cfg = self._write_config("this is not toml [")
        try:
            with pytest.raises(ConfigError, match="Invalid TOML"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_missing_pins_table_raises(self):
        cfg = self._write_config("foo = 'bar'")
        try:
            with pytest.raises(ConfigError, match="Missing or invalid"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_invalid_direction_raises(self):
        cfg = self._write_config('[pins.x]\nbcm = 17\ndirection = "sideways"\n')
        try:
            with pytest.raises(ConfigError, match="direction must be 'out' or 'in'"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_non_integer_bcm_raises(self):
        cfg = self._write_config('[pins.x]\nbcm = "17"\ndirection = "out"\n')
        try:
            with pytest.raises(ConfigError, match="bcm must be an integer"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_bcm_out_of_range_raises(self):
        cfg = self._write_config('[pins.x]\nbcm = 99\ndirection = "out"\n')
        try:
            with pytest.raises(ConfigError, match="out of range"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_reserved_bcm_rejected(self):
        for reserved in (0, 1, 2, 3, 14, 15):
            cfg = self._write_config(f"[pins.x]\nbcm = {reserved}\ndirection = \"out\"\n")
            try:
                with pytest.raises(ConfigError, match="reserved"):
                    load_config(cfg)
            finally:
                cfg.unlink()

    def test_duplicate_bcm_rejected(self):
        cfg = self._write_config("""
[pins.a]
bcm = 17
direction = "out"
max_on_s = 600

[pins.b]
bcm = 17
direction = "out"
max_on_s = 600
""")
        try:
            with pytest.raises(ConfigError, match="already used"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_output_missing_max_on_s_raises(self):
        cfg = self._write_config('[pins.x]\nbcm = 17\ndirection = "out"\n')
        try:
            with pytest.raises(ConfigError, match="max_on_s is required"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_output_max_on_s_range(self):
        for bad_val in (0, -1, 86401):
            cfg = self._write_config(f'[pins.x]\nbcm = 17\ndirection = "out"\nmax_on_s = {bad_val}\n')
            try:
                with pytest.raises(ConfigError, match="1..86400"):
                    load_config(cfg)
            finally:
                cfg.unlink()

    def test_input_with_max_on_s_rejected(self):
        cfg = self._write_config('[pins.x]\nbcm = 17\ndirection = "in"\nmax_on_s = 600\n')
        try:
            with pytest.raises(ConfigError, match="max_on_s is only for outputs"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_input_pull_validation(self):
        for bad in ("sideways", "foo", 123):
            cfg = self._write_config(f'[pins.x]\nbcm = 17\ndirection = "in"\npull = "{bad}"\n')
            try:
                with pytest.raises(ConfigError, match="pull must be"):
                    load_config(cfg)
            finally:
                cfg.unlink()

    def test_output_pull_rejected(self):
        cfg = self._write_config('[pins.x]\nbcm = 17\ndirection = "out"\npull = "up"\nmax_on_s = 600\n')
        try:
            with pytest.raises(ConfigError, match="pull is only for inputs"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_non_boolean_active_high_raises(self):
        cfg = self._write_config('[pins.x]\nbcm = 17\ndirection = "out"\nactive_high = "yes"\nmax_on_s = 600\n')
        try:
            with pytest.raises(ConfigError, match="active_high must be a boolean"):
                load_config(cfg)
        finally:
            cfg.unlink()

    def test_empty_config_rejected(self):
        cfg = self._write_config("pins = {}\n")
        try:
            with pytest.raises(ConfigError, match="No pins configured"):
                load_config(cfg)
        finally:
            cfg.unlink()


class TestTokenLoader:
    """Tests for load_token()."""

    def _write_secrets(self, content: str) -> Path:
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
        tf.write(content)
        tf.close()
        return Path(tf.name)

    def test_valid_token_loads(self):
        sec = self._write_secrets('POSEY_TUBE_TOKEN=abc123\n')
        try:
            assert load_token(sec) == "abc123"
        finally:
            sec.unlink()

    def test_token_with_quotes(self):
        sec = self._write_secrets('POSEY_TUBE_TOKEN="abc123"\n')
        try:
            assert load_token(sec) == "abc123"
        finally:
            sec.unlink()

    def test_missing_token_raises(self):
        sec = self._write_secrets("OTHER=foo\n")
        try:
            with pytest.raises(ConfigError, match="POSEY_TUBE_TOKEN not set"):
                load_token(sec)
        finally:
            sec.unlink()

    def test_missing_secrets_file_raises(self):
        with pytest.raises(ConfigError, match="Secrets file not found"):
            load_token(Path("/nonexistent/secrets.env"))