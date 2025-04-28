import json
import ipaddress
from logger_module import setup_logger

# Get logger
logger = setup_logger()

def load_valid_networks(filename):
    """
    Load the list of valid network ranges from a JSON file.
    
    Args:
        filename (str): Path to the JSON file containing valid network ranges
        
    Returns:
        list: List of valid network CIDR ranges
    """
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            return data.get('valid_networks', [])
    except FileNotFoundError:
        logger.error(f"The file {filename} was not found.")
        return []
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON.")
        return []

def is_ip_valid(ip, networks):
    """
    Check if an IP address is within any of the valid network ranges.
    
    Args:
        ip (str): IP address to validate
        networks (list): List of valid network CIDR ranges
        
    Returns:
        bool: True if the IP is within any valid network range, False otherwise
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        for network in networks:
            if ip_obj in ipaddress.ip_network(network):
                return True
        return False
    except ValueError:
        logger.error(f"{ip} is not a valid IP address.")
        return False

if __name__ == "__main__":
    valid_networks = load_valid_networks("valid_networks.json")

    # Example usage
    test_ip = "192.168.1.50"  # This should return True
    if is_ip_valid(test_ip, valid_networks):
        logger.info(f"The IP address {test_ip} is within the valid network ranges.")
    else:
        logger.warning(f"The IP address {test_ip} is NOT within the valid network ranges.")