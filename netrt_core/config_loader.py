# netrt_core/config_loader.py

import yaml
import os
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "dicom_listener": {
        "host": "0.0.0.0",
        "port": 11112,
        "ae_title": "NETRTCORE"
    },
    "dicom_destination": {
        "ip": "127.0.0.1",
        "port": 104,
        "ae_title": "DEST_AET"
    },
    "directories": {
        "working": "~/CNCT_working",
        "logs": "~/CNCT_logs",
        "quarantine_subdir": "quarantine" # Subdirectory within working_dir
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "application_log_file": "application.log",
        "transaction_log_file": "transaction.log"
    },
    "anonymization": {
        "enabled": True,
        "rules": {
            "remove_tags": [
                "AccessionNumber", 
                "PatientID"
            ],
            "blank_tags": [], # Example: "PatientBirthDate"
            "generate_random_id_prefix": "NETRT_ ANON_"
        }
    },
    "processing": {
        "ignore_contour_names_containing": ["skull"],
        "default_series_description": "Processed DicomRT with Overlay",
        "default_series_number": 9901
    },
    "feature_flags": {
        "enable_segmentation_export": False
    }
}

def load_config(config_path="config.yaml"):
    """Loads configuration from a YAML file, using defaults if the file doesn't exist or is incomplete."""
    config = DEFAULT_CONFIG.copy() # Start with defaults

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
            if user_config:
                # Deep merge user_config into config
                # A simple update might not be enough for nested dicts
                for key, value in user_config.items():
                    if isinstance(value, dict) and isinstance(config.get(key), dict):
                        config[key].update(value)
                    else:
                        config[key] = value
                logger.info(f"Successfully loaded configuration from {config_path}")
            else:
                logger.warning(f"Configuration file {config_path} is empty. Using default configuration.")
                _save_default_config(config_path, config) # Save defaults if file was empty

        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration file {config_path}: {e}. Using default configuration.")
        except Exception as e:
            logger.error(f"Error loading configuration file {config_path}: {e}. Using default configuration.")
    else:
        logger.warning(f"Configuration file {config_path} not found. Using default configuration and creating it.")
        _save_default_config(config_path, config)
    
    # Expand user paths for directories
    if "directories" in config:
        for key, path_val in config["directories"].items():
            if isinstance(path_val, str) and "subdir" not in key.lower(): # Don't expand subdir names
                 config["directories"][key] = os.path.expanduser(path_val)

    return config

def _save_default_config(config_path, config_data):
    """Saves the provided configuration data (usually defaults) to the specified path."""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config_data, f, sort_keys=False, default_flow_style=False)
        logger.info(f"Saved default configuration to {config_path}")
    except Exception as e:
        logger.error(f"Could not save default configuration to {config_path}: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test loading (will create config.yaml in current dir if not exists)
    cfg = load_config("test_config.yaml")
    print("Loaded configuration:")
    import json
    print(json.dumps(cfg, indent=4))

    # Test that directories are expanded
    print(f"Working directory: {cfg['directories']['working']}")
    print(f"Logs directory: {cfg['directories']['logs']}")

