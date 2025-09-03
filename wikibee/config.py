# Configuration management for wikibee
import sys
from pathlib import Path
from typing import Any, Dict

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def get_config_path() -> Path:
    """
    Returns the platform-specific path for the configuration file.

    Returns:
        Path: The path to the configuration file.
    """
    return Path(platformdirs.user_config_path("wikibee")) / "config.toml"


def load_config() -> Dict[str, Any]:
    """
    Loads the configuration from the TOML file.

    Returns:
        dict: The configuration dictionary, or an empty dict if not found.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def merge_configs(
    defaults: Dict[str, Any],
    config_file: Dict[str, Any],
    cli_args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merges configurations from defaults, config file, and CLI arguments.

    Args:
        defaults: Dictionary of default values.
        config_file: Dictionary of values from the config file.
        cli_args: Dictionary of values from the command line.

    Returns:
        dict: The merged configuration.
    """
    merged = defaults.copy()
    merged.update(config_file)
    cli_args_filtered = {k: v for k, v in cli_args.items() if v is not None}
    merged.update(cli_args_filtered)
    return merged
