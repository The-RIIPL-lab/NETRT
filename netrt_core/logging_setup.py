# netrt_core/logging_setup.py

import logging
import os
import sys

# Define a specific logger for transaction events
TRANSACTION_LOGGER_NAME = "transaction"

def setup_logging(config):
    """Sets up logging for the application based on the provided configuration."""
    log_config = config.get("logging", {})
    log_level_str = log_config.get("level", "INFO").upper()
    log_format_str = log_config.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logs_dir = os.path.expanduser(config.get("directories", {}).get("logs", "~/CNCT_logs"))
    app_log_filename = log_config.get("application_log_file", "application.log")
    trans_log_filename = log_config.get("transaction_log_file", "transaction.log")

    app_log_path = os.path.join(logs_dir, app_log_filename)
    trans_log_path = os.path.join(logs_dir, trans_log_filename)

    try:
        os.makedirs(logs_dir, exist_ok=True)
    except OSError as e:
        # Fallback to console logging if directory creation fails
        logging.basicConfig(level=log_level, format=log_format_str, stream=sys.stdout)
        logging.error(f"Could not create logs directory {logs_dir}: {e}. Falling back to console logging.")
        return

    # Basic configuration for the root logger - primarily for console output and setting level
    # Handlers will be added specifically to avoid duplicate messages if root already has handlers.
    logging.basicConfig(level=log_level, format=log_format_str, handlers=[logging.StreamHandler(sys.stdout)])
    # For applications, it is often better to get the root logger and add handlers to it,
    # or configure loggers on a per-module basis if more granularity is needed.
    # For simplicity here, basicConfig sets up the root. We will add file handlers.

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level) # Ensure root logger level is set

    # Clear existing handlers from root to avoid duplication if script is re-run in some contexts
    # This might be too aggressive if other libraries also configure root logger.
    # A better approach for libraries is to use logging.getLogger(__name__)
    # and for applications to configure the root logger or specific application loggers.
    # For now, let's assume we control the top-level config.
    # for handler in root_logger.handlers[:]:
    #     root_logger.removeHandler(handler)

    # Console Handler (already added by basicConfig if no handlers were present)
    # We can customize it if needed or ensure it's there.
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setFormatter(logging.Formatter(log_format_str))
    # console_handler.setLevel(log_level)
    # if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    #     root_logger.addHandler(console_handler)

    # Application File Handler
    try:
        app_file_handler = logging.FileHandler(app_log_path)
        app_file_handler.setFormatter(logging.Formatter(log_format_str))
        app_file_handler.setLevel(log_level)
        root_logger.addHandler(app_file_handler)
        logging.info(f"Application logging configured. Level: {log_level_str}. File: {app_log_path}")
    except Exception as e:
        logging.error(f"Failed to configure application file logger at {app_log_path}: {e}", exc_info=True)

    # Transaction File Handler (for a specific logger)
    try:
        transaction_logger = logging.getLogger(TRANSACTION_LOGGER_NAME)
        transaction_logger.setLevel(log_level) # Transactions should also respect the global level or have their own
        transaction_logger.propagate = False # Do not propagate to root logger to avoid duplicate file/console logs

        trans_file_handler = logging.FileHandler(trans_log_path)
        # Transaction log might have a simpler format, or a specific one
        trans_log_format_str = log_config.get("transaction_log_format", "%(asctime)s [%(levelname)s]: %(message)s")
        trans_file_handler.setFormatter(logging.Formatter(trans_log_format_str))
        trans_file_handler.setLevel(log_level)
        
        transaction_logger.addHandler(trans_file_handler)
        
        # Optionally, add a console handler for transactions too if needed for debugging, but usually not.
        # trans_console_handler = logging.StreamHandler(sys.stdout)
        # trans_console_handler.setFormatter(logging.Formatter(trans_log_format_str))
        # trans_console_handler.setLevel(log_level)
        # transaction_logger.addHandler(trans_console_handler)

        transaction_logger.info(f"Transaction logging configured. Level: {log_level_str}. File: {trans_log_path}") # Log to its own file
    except Exception as e:
        logging.error(f"Failed to configure transaction file logger at {trans_log_path}: {e}", exc_info=True)

if __name__ == "__main__":
    # Example usage:
    example_config = {
        "directories": {
            "logs": "~/CNCT_logs_test_logging"
        },
        "logging": {
            "level": "DEBUG",
            "format": "%(asctime)s [%(levelname)s] %(name)s %(module)s:%(lineno)d: %(message)s",
            "application_log_file": "app_test.log",
            "transaction_log_file": "trans_test.log",
            "transaction_log_format": "%(asctime)s TXN: %(message)s"
        }
    }
    setup_logging(example_config)

    # Test general logging
    logger = logging.getLogger("my_app_module")
    logger.debug("This is a debug message for the app log.")
    logger.info("This is an info message for the app log.")
    logger.warning("This is a warning message for the app log.")

    # Test transaction logging
    transaction_logger = logging.getLogger(TRANSACTION_LOGGER_NAME)
    transaction_logger.info("STUDY_RECEIVED StudyUID=1.2.3 SourceIP=10.0.0.1 DestIP=10.0.0.2")
    transaction_logger.info("STUDY_SENT StudyUID=1.2.3 DestIP=10.0.0.2")

    print(f"Logging setup complete. Check logs in {os.path.expanduser(example_config['directories']['logs'])}")

