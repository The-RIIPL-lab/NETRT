import logging

def setup_logger():
    """
    Creates and configures the standard logger for the NETRT application.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Configure the basic logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(),  # Log to STDOUT
            logging.FileHandler('NETRT.log'),  # Save log messages to a file
        ]
    )
    
    # Return the logger instance
    return logging.getLogger('NETRT')