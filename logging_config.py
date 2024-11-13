import logging

def setup_logging():
    # Create a basic logger
    logging.basicConfig(
        level=logging.INFO,  # Set the desired logging level
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('NETRT.log'),  # Save log messages to a single file
            logging.StreamHandler()  # Also output logs to console
        ]
    )

# Ensure the logger is set up only once
setup_logging()