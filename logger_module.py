import logging
from datetime import datetime

def setup_logger():
    """
    Creates and configures the standard logger for the NETRT application.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create a timestamp for the filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Configure the basic logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(),  # Log to STDOUT
            logging.FileHandler(f'NETRT_{timestamp}.log'),  # Save log messages to a dated file
        ]
    )
    
    # Return the logger instance
    return logging.getLogger('NETRT')