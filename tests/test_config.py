# Tests for the wikibee configuration module
from pathlib import Path
from unittest.mock import patch

from wikibee import config


def test_get_config_path():
    """Test that get_config_path constructs the path correctly."""
    with patch("platformdirs.user_config_path") as mock_user_config_path:
        mock_user_config_path.return_value = Path("/fake/config/dir/wikibee")
        expected_path = Path("/fake/config/dir/wikibee") / "config.toml"
        assert config.get_config_path() == expected_path


def test_load_config_no_file():
    """Test that loading a non-existent file returns an empty dict."""
    with patch("pathlib.Path.exists", return_value=False):
        result = config.load_config()
        assert result == {}


def test_load_config_with_file(tmp_path):
    """Test that a TOML config file is loaded correctly."""
    config_path = tmp_path / "config.toml"
    config_content = """
    tts_voice = "test_voice"
    timeout = 30
    """
    config_path.write_text(config_content)

    expected_config = {
        "tts_voice": "test_voice",
        "timeout": 30,
    }

    with patch("wikibee.config.get_config_path", return_value=config_path):
        loaded_config = config.load_config()
        assert loaded_config == expected_config


def test_merge_configs():
    """Test that configurations are merged correctly."""
    defaults = {"timeout": 15, "tts_voice": "default_voice"}
    config_file = {"timeout": 30, "output_dir": "/tmp/output"}
    cli_args = {"tts_voice": "cli_voice", "output_dir": "/cli/output"}

    merged = config.merge_configs(defaults, config_file, cli_args)

    assert merged["timeout"] == 30  # from config_file, overrides default
    assert merged["tts_voice"] == "cli_voice"  # from cli_args, overrides default
    assert merged["output_dir"] == "/cli/output"  # from cli_args, overrides config_file
