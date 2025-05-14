# Main application entry point

import os
import sys
import time
import logging
import argparse

# Adjust path to import from netrt_core, assuming main.py is in the NETRT root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from netrt_core.config_loader import load_config
from netrt_core.logging_setup import setup_logging, TRANSACTION_LOGGER_NAME
from netrt_core.file_system_manager import FileSystemManager
from netrt_core.dicom_listener import DicomListener
from netrt_core.study_processor import StudyProcessor
# Import other necessary utilities if they are directly called or configured from main
# e.g., from ip_validation import load_valid_networks, is_ip_valid

logger = logging.getLogger(__name__) # Main application logger
transaction_logger = logging.getLogger(TRANSACTION_LOGGER_NAME)

def main():
    parser = argparse.ArgumentParser(description="NETRT DICOM Processing Application")
    parser.add_argument("--config", default="config.yaml", help="Path to the configuration file (default: config.yaml)")
    args = parser.parse_args()

    # 1. Load Configuration
    config = load_config(args.config)

    # 2. Setup Logging (must be done after config is loaded)
    setup_logging(config)

    logger.info("NETRT Application starting...")
    logger.info(f"Using configuration file: {os.path.abspath(args.config)}")
    logger.debug(f"Loaded configuration: {config}")

    # 3. Initialize Core Components
    # The study_processor_callback will be passed to FileSystemManager, 
    # which in turn passes it to its NewStudyEventHandler.
    # This callback needs to be a method of an initialized StudyProcessor instance.

    # Initialize FileSystemManager first, as StudyProcessor might need it (though not directly in current constructor)
    # and DicomListener needs it.
    # The FileSystemManager will also need the study_processor_callback later if using watchdog.
    
    # Placeholder for the actual study processing function that FSM will call
    # This needs to be carefully designed to avoid circular dependencies at init time
    # or to pass the processor instance later.
    
    # Solution: Instantiate StudyProcessor, then pass its method to FSM.
    study_processor_instance = StudyProcessor(config, None) # FSM not strictly needed by SP constructor for now

    file_system_manager = FileSystemManager(config, study_processor_instance.process_study)
    study_processor_instance.fsm = file_system_manager # Now link FSM to StudyProcessor
    
    dicom_listener = DicomListener(
        host=config.get("dicom_listener", {}).get("host", "0.0.0.0"),
        port=config.get("dicom_listener", {}).get("port", 11112),
        ae_title=config.get("dicom_listener", {}).get("ae_title", "NETRTCORE"),
        study_processor_callback=study_processor_instance.process_study, # This callback is for the listener itself (e.g. on connection close)
        file_system_manager=file_system_manager,
        config=config # Pass full config for listener to access negotiated_transfer_syntax settings
    )

    # 4. Start Services
    # Start file system watcher first if it runs in a separate thread
    file_system_manager.start_watching() 

    # Start DICOM listener (this might be blocking depending on implementation)
    # The DicomListener.start() method in the example was blocking.
    # If it needs to run in parallel with the watcher, one must be in a thread.
    # For Docker, a single blocking process is often fine if it handles signals.
    
    # For graceful shutdown:
    # import signal
    # def signal_handler(sig, frame):
    #     logger.info("Shutdown signal received. Stopping services...")
    #     dicom_listener.stop() # Assuming DicomListener has a stop method that releases the server
    #     file_system_manager.stop_watching()
    #     logger.info("NETRT Application stopped.")
    #     sys.exit(0)

    # signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    # signal.signal(signal.SIGTERM, signal_handler) # Handle `docker stop`

    try:
        logger.info(f"Starting DICOM listener on {dicom_listener.host}:{dicom_listener.port} AE: {dicom_listener.ae_title}")
        dicom_listener.start() # This is expected to block
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
    finally:
        logger.info("Stopping services...")
        if hasattr(dicom_listener, "stop") and callable(dicom_listener.stop):
            dicom_listener.stop()
        if hasattr(file_system_manager, "stop_watching") and callable(file_system_manager.stop_watching):
            file_system_manager.stop_watching()
        logger.info("NETRT Application shut down.")

if __name__ == "__main__":
    main()

