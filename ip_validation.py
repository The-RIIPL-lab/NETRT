import json
import ipaddress

def load_valid_networks(filename):
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            return data.get('valid_networks', [])
    except FileNotFoundError:
        print(f"Error: The file {filename} was not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON.")
        return []

def is_ip_valid(ip, networks):
    try:
        ip_obj = ipaddress.ip_address(ip)
        for network in networks:
            if ip_obj in ipaddress.ip_network(network):
                return True
        return False
    except ValueError:
        print(f"Error: {ip} is not a valid IP address.")
        return False

if __name__ == "__main__":
    valid_networks = load_valid_networks("valid_networks.json")

    # Example usage
    test_ip = "192.168.1.50"  # This should return True
    if is_ip_valid(test_ip, valid_networks):
        print(f"The IP address {test_ip} is within the valid network ranges.")
    else:
        print(f"The IP address {test_ip} is NOT within the valid network ranges.")