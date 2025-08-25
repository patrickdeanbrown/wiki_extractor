from pathlib import Path
from typing import Any, Dict

import tomli
from typer import get_app_dir

class WikibeeConfig:
    """
    Represents the application's configuration, loaded from config.toml.
    """
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value from a specific section and key.
        """
        return self._data.get(section, {}).get(key, default)

    def __repr__(self) -> str:
        return f"WikibeeConfig({self._data})"

def get_config_file_path() -> Path:
    """
    Returns the expected path to the configuration file.
    """
    app_dir = get_app_dir("wikibee")
    config_dir = Path(app_dir)
    return config_dir / "config.toml"

def load_config() -> WikibeeConfig:
    """
    Loads the application configuration from config.toml.

    Returns a WikibeeConfig object. If the file does not exist or is invalid,
    it returns a default (empty) configuration.
    """
    config_path = get_config_file_path()
    config_data: Dict[str, Any] = {}

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                config_data = tomli.load(f)
        except tomli.TOMLDecodeError as e:
            print(f"Warning: Could not parse config file {config_path}: {e}")
        except Exception as e:
            print(f"Warning: Could not read config file {config_path}: {e}")

    return WikibeeConfig(config_data)

# Example usage (for internal testing/debugging)
if __name__ == "__main__":
    print(f"Expected config path: {get_config_file_path()}")
    config = load_config()
    print(f"Loaded config: {config}")
    output_dir_value = config.get('general', 'output_dir', 'not_set')
    print(f"Output directory from config: {output_dir_value}")
