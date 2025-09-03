from unittest.mock import MagicMock

from typer.testing import CliRunner

try:  # Python 3.11+
    import tomllib as tomli  # type: ignore[attr-defined]
except Exception:  # Python < 3.11
    import tomli  # type: ignore[no-redef]

from wikibee import cli


def test_config_precedence(monkeypatch, tmp_path):
    """
    Test the configuration precedence: CLI > config file > defaults.
    """
    # 1. Create a temporary config file
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
timeout = 20
tts_voice = "config-voice"
"""
    )

    # 2. Patch get_config_path to use the temporary file
    monkeypatch.setattr(cli.config, "get_config_path", lambda: config_path)

    # 3. Patch a function at the end of the chain to inspect the final `args`
    mock_write_outputs = MagicMock()
    monkeypatch.setattr(cli, "_write_outputs", mock_write_outputs)

    # Also patch extract_wikipedia_text to avoid network calls
    monkeypatch.setattr(
        cli,
        "extract_wikipedia_text",
        lambda url, **kwargs: ("Fake content.", "Fake Title"),
    )

    # 4. Run the CLI
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "https://example.org/wiki/Fake",
            "--timeout",
            "30",  # CLI override
            # tts_voice is NOT provided, so config value should be used
            # lead_only is NOT provided, so default should be used
        ],
    )

    assert result.exit_code == 0

    # 5. Assert that _write_outputs was called with the correct, merged config
    assert mock_write_outputs.call_count == 1
    call_args, call_kwargs = mock_write_outputs.call_args
    final_args = call_args[0]  # The `args` object is the first positional argument

    # CLI override: timeout=30 should win over config file's 20
    assert final_args.timeout == 30

    # Config file value: tts_voice="config-voice" should be used
    assert final_args.tts_voice == "config-voice"

    # Default value: lead_only=False should be used
    assert final_args.lead_only is False


def test_config_init(monkeypatch, tmp_path):
    """
    Test that `wikibee config init` creates a default config file.
    """
    # 1. Set up a temporary path for the config file
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.config, "get_config_path", lambda: config_path)

    # 2. Run the `config init` command
    runner = CliRunner()
    result = runner.invoke(cli.app, ["config", "init", "--force"])

    assert result.exit_code == 0
    assert (
        f"Default configuration file created at {config_path}"
        in result.stdout.replace("\n", "")
    )

    # 3. Verify the file was created and has the correct content
    assert config_path.exists()

    with open(config_path, "rb") as f:
        created_config = tomli.load(f)

    expected_config = {k: v for k, v in cli.DEFAULTS.items() if v is not None}
    assert created_config == expected_config
