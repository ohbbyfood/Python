import pandas as pd
from netmiko import ConnectHandler
import re


# Function to read devices from a text file and return a list of devices
def read_devices_from_file(file_path):
    devices = []
    with open('devices.txt', 'r') as file:
        for line in file:
            line = line.strip()
            if line:  # Skip empty lines
                # Split the line into device details
                device_details = line.split(',')
                device = {
                    'device_type': 'cisco_ios',
                    'host': line,  # IP address
                    'username': 'username',  # SSH username
                    'password': 'password',  # SSH password
                }
                devices.append(device)
    return devices


# Function to gather interface descriptions from a device
def gather_interface_descriptions(device):
    # Connect to the Cisco switch
    net_connect = ConnectHandler(**device)
    net_connect.enable()  # Enter enable mode

    # Retrieve the hostname of the device
    hostname = net_connect.send_command('show running-config | include hostname')
    hostname = hostname.split()[-1] if hostname else 'Unknown'

    # Retrieve the interface descriptions using a filtered command
    output = net_connect.send_command('show running-config | sec interface|description')

    # Debug: Print part of the output to verify its structure
    #print(
        #f"Output for {device['host']}:\n{output[:1000]}")  # Print the first 1000 characters of the output for inspection

    # Initialize variables
    interfaces = []
    interface_name = None
    description = None

    # Loop through the output line by line
    for line in output.splitlines():
        # Look for interface line
        if line.startswith('interface'):
            # If we had a previous interface, save it before switching to the new one
            if interface_name:
                interfaces.append({'Device IP': device['host'], 'Hostname': hostname, 'Interface': interface_name,
                                   'Description': description if description else ''})
            # Capture the interface name
            interface_name = line.split()[1]
            description = None  # Reset description for the new interface
        elif line.strip().startswith('description'):
            # Capture the description if available
            description = line.split('description', 1)[1].strip()

    # After loop ends, don't forget to append the last interface
    if interface_name:
        interfaces.append({'Device IP': device['host'], 'Hostname': hostname, 'Interface': interface_name,
                           'Description': description if description else 'No description'})

    # Disconnect from the device
    net_connect.disconnect()

    return interfaces


# Read the devices from the text file
devices = read_devices_from_file('devices.txt')

# Loop through the list of devices
all_interfaces = []

for device in devices:
    print(f"Gathering interface descriptions for device: {device['host']}...")

    # Get the interface descriptions for this device
    interfaces = gather_interface_descriptions(device)

    all_interfaces.extend(interfaces)

# If we have any interfaces, create a DataFrame and save to an Excel file
if all_interfaces:
    df = pd.DataFrame(all_interfaces)

    # Write the data to an Excel file
    output_file = 'all_switch_interfaces.xlsx'
    df.to_excel(output_file, index=False)

    print(f"Interface descriptions from all devices have been successfully saved to {output_file}")
else:
    print("No interface descriptions found from any devices.")
