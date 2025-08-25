import logging
import os
from unittest.mock import patch

import pytest

from wikibee.cli import app
from typer.testing import CliRunner

# Fixture to create a temporary config directory and file
@pytest.fixture
def temp_config_dir(tmp_path):
    config_dir = tmp_path / ".config" / "wikibee"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir

# Fixture to mock typer.get_app_dir
@pytest.fixture
def mock_get_app_dir(temp_config_dir):
    with patch(
        "wikibee.config.get_app_dir",
        return_value=str(temp_config_dir)
    ):
        yield

# Fixture for CliRunner
@pytest.fixture
def runner():
    return CliRunner()

# --- Test Cases ---

def test_no_config_file_uses_defaults(runner, mock_get_app_dir):
    """Test that hardcoded defaults are used when no config file exists."""
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article", "--no-save"])
        assert result.exit_code == 0
        assert "Output saved to:" not in result.stdout # no_save is True


def test_empty_config_file_uses_defaults(runner, temp_config_dir, mock_get_app_dir):
    """Test that hardcoded defaults are used when config file is empty."""
    (temp_config_dir / "config.toml").touch()
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article", "--no-save"])
        assert result.exit_code == 0
        assert "Output saved to:" not in result.stdout


def test_invalid_config_file_uses_defaults_and_warns(
    runner, temp_config_dir, mock_get_app_dir
):
    """Test that invalid config file is ignored and a warning is printed."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("invalid toml = [")
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article", "--no-save"])
        assert result.exit_code == 0
        assert "Warning: Could not parse config file" in result.stdout
        assert "Output saved to:" not in result.stdout


def test_config_file_sets_output_dir(runner, temp_config_dir, mock_get_app_dir):
    """Test that output_dir is set from config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[general]\noutput_dir = \"/tmp/wikibee_test_output\"")
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article"])
        assert result.exit_code == 0
        assert "Output saved to: /tmp/wikibee_test_output" in result.stdout


def test_config_file_sets_tts_server(runner, temp_config_dir, mock_get_app_dir):
    """Test that tts_server is set from config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[tts]\nserver_url = \"http://custom-tts:8000\"")
    # Mock TTSClientError to avoid actual network call
    with patch("wikibee.cli.TTSOpenAIClient") as mock_tts_client, \
         patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        mock_tts_client.return_value.synthesize_to_file.side_effect = Exception(
            "Mocked TTS Error"
        )
        result = runner.invoke(app, ["test_article", "--audio"])
        assert result.exit_code == 1 # Expect failure due to mocked error
        mock_tts_client.assert_called_once_with(base_url="http://custom-tts:8000")


def test_env_var_overrides_config_file(runner, temp_config_dir, mock_get_app_dir):
    """Test that environment variable overrides config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[general]\noutput_dir = \"/tmp/from_config\"")

    with patch.dict(os.environ, {"WIKIBEE_OUTPUT_DIR": "/tmp/from_env"}), \
         patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article"])
        assert result.exit_code == 0
        assert "Output saved to: /tmp/from_env" in result.stdout


def test_cli_arg_overrides_env_var_and_config(
    runner, temp_config_dir, mock_get_app_dir
):
    """Test that CLI argument overrides env var and config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[general]\noutput_dir = \"/tmp/from_config\"")

    with patch.dict(os.environ, {"WIKIBEE_OUTPUT_DIR": "/tmp/from_env"}), \
         patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article", "--output", "/tmp/from_cli"])
        assert result.exit_code == 0
        assert "Output saved to: /tmp/from_cli" in result.stdout


def test_config_file_sets_search_limit(runner, temp_config_dir, mock_get_app_dir):
    """Test that search_limit is set from config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[search]\nsearch_limit = 5")

    # Mock _handle_search to check the limit passed to it
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        result = runner.invoke(app, ["test_article"])
        assert result.exit_code == 0
        # Check that _handle_search was called with args.search_limit == 5
        assert mock_handle_search.call_args[0][1].search_limit == 5


def test_config_file_sets_retries(runner, temp_config_dir, mock_get_app_dir):
    """Test that retries is set from config file."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text("[general]\nretries = 7")

    # Mock extract_wikipedia_text to check the retries passed to it
    with patch("wikibee.cli.extract_wikipedia_text") as mock_extract_wikipedia_text, \
         patch("wikibee.cli._handle_search") as mock_handle_search:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract_wikipedia_text.return_value = ("test content", "Test Title")
        result = runner.invoke(app, ["test_article"])
        assert result.exit_code == 0
        # Check that extract_wikipedia_text was called with retries == 7
        assert mock_extract_wikipedia_text.call_args[1]["retries"] == 7


def test_config_file_sets_boolean_flags(runner, temp_config_dir, mock_get_app_dir):
    """Test that boolean flags like no_save, verbose, yolo are set from config."""
    config_path = temp_config_dir / "config.toml"
    config_path.write_text(
        "[general]\nno_save = true\nverbose = true\nauto_select = true"
    )

    # Mock _handle_search and logging to check verbose and yolo
    with patch("wikibee.cli._handle_search") as mock_handle_search, \
         patch("logging.getLogger") as mock_get_logger, \
         patch("wikibee.cli.extract_wikipedia_text") as mock_extract:
        mock_handle_search.return_value = "http://example.com/article"
        mock_extract.return_value = ("test content", "Test Article")
        mock_get_logger.return_value.setLevel.return_value = None # Mock setLevel

        result = runner.invoke(app, ["test_article"])
        assert result.exit_code == 0

        # Check no_save (should not save to disk)
        assert "Output saved to:" not in result.stdout

        # Check verbose (logging level should be set to DEBUG)
        mock_get_logger.assert_called_once_with()
        mock_get_logger.return_value.setLevel.assert_called_once_with(logging.DEBUG)

        # Check yolo (auto_select in config maps to yolo)
        assert mock_handle_search.call_args[0][1].yolo is True


