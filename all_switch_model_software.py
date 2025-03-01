from netmiko import ConnectHandler
import openpyxl
import re


# Function to read device IP addresses from a text file
def read_device_ips():
    device_ips = []
    with open('IOS_Test.txt', 'r') as f:
        for line in f:
            if line.strip():  # Ignore empty lines
                device_ips.append(line.strip())
    return device_ips


# Function to detect device type by checking the prompt
def detect_device_type(connection):
    prompt = connection.send_command('show version')
    if re.search(r"NX-OS", prompt, re.IGNORECASE):
        return 'nx-os'
    elif re.search(r'Adaptive Security Appliance', prompt, re.IGNORECASE):
        return 'asa'
    elif re.search(r'IOS-XE|IOS', prompt, re.IGNORECASE):
        return 'cisco'
    elif re.search(r'JUNOS', prompt, re.IGNORECASE):
        return 'juniper'
    else:
        return None


# Function to gather device info including serial numbers
def gather_device_info(device_ip):
    device = {
        'host': device_ip,
        'username': user,
        'password': password,
        'device_type': 'cisco_ios',
    }

    # Gather property
    if device_ip.startswith(('10.154.216.', '10.154.217.')):
        location = 'ARIA'
    elif device_ip.startswith(('10.154.16.', '10.154.18.')):
        location = 'BEL'
    elif device_ip.startswith('10.154.36.'):
        location = 'CSC'
    elif device_ip.startswith('10.154.201.'):
        location = 'EXCAL'
    elif device_ip.startswith('10.154.142.'):
        location = 'LUX'
    elif device_ip.startswith(('10.154.183.', '10.154.184.', '10.154.185.', '10.154.186.', '10.154.187.')):
        location = 'MBAY'
    elif device_ip.startswith(('10.154.233.', '10.154.7.')):
        location = 'MGM'
    elif device_ip.startswith('10.154.21.'):
        location = 'NYNY'
    elif device_ip.startswith('10.154.133'):
        location = 'PARK'
    elif device_ip.startswith('10.154.26.'):
        location = 'TCOLV'
    elif device_ip.startswith('10.154.218.'):
        location = 'VDARA'
    else:
        location = 'FALSE'

    try:
        connection = ConnectHandler(**device)
        device_type = detect_device_type(connection)
        if not device_type:
            raise Exception("Device type could not be determined.")
        print(f"Device type detected: {device_type.upper()}")

        if device_type == 'cisco':
            device['device_type'] = 'cisco_ios'
        elif device_type == 'juniper':
            device['device_type'] = 'juniper'

        connection = ConnectHandler(**device)
        connection.enable()

        # Gather device info for IOS/IOSXE devices
        if device_type == 'cisco':
            # Gather information from 'show version'
            show_version_output = connection.send_command('show version')
            show_cr_tr_location = connection.send_command('show snmp location')
            show_int_description = connection.send_command('show interfaces description')

            # Extract Hostname
            hostname_match = re.search(r"^hostname\s+(\S+)",
                                       connection.send_command('show running-config | include hostname'))
            if hostname_match:
                hostname = hostname_match.group(1)
            else:
                hostname = "Hostname not found"

            # Extract Model
            model_match = re.search(r"(?i)Model number\s*:\s*(\S+)", show_version_output)
            if model_match:
                model = model_match.group(1)
            else:
                model = "Model not found"

            # Extract Software Version
            software_version_match = re.search(r"Version\s+([^\n,]+)", show_version_output)
            if software_version_match:
                software_version = software_version_match.group(1)
            else:
                software_version = "Software version not found"

            # Extract Serial Numbers (From show inventory or show version)
            serial_match = re.findall(r"(?i)System Serial Number\s*:\s*(\S+)", show_version_output)
            serial_numbers = serial_match[:4]  # Limit to 4 serial numbers if there are more

            # If fewer than 4 serial numbers, fill in the missing ones as "N/A"
            while len(serial_numbers) < 4:
                serial_numbers.append('N/A')

            # Filter out N/A in serial_number list and get total devices for switch_count
            filtered_serial_numbers = [item for item in serial_numbers if item != 'N/A']
            switch_count = len(filtered_serial_numbers)

            # Regex to extract "CR" or "TR" from snmp location
            snmp_match = re.search(r"\b(?:CR|TR)\d+\b", show_cr_tr_location)
            if snmp_match:
                snmp_location = snmp_match.group(0)
            else:
                snmp_location = ""

            # Gather all interfaces that match uplink description pattern
            uplink_match = re.findall(r"(\S+)\s+(?:up|down)\s+(?:up|down)?\s*uplink to\s+([A-Za-z0-9-]+(?:"
                                      r"[A-Za-z0-9-]+\s*)*)\s+(\S+)", show_int_description)
            desc_matches = [item for sublist in uplink_match for item in sublist]  # Turn tuple into list

            # Include N/A for devices without redundant uplink
            while len(desc_matches) < 6:
                desc_matches.append('N/A')

            # Gather port link speed for uplink interfaces
            uplink_speed_command = connection.send_command(f"show int status | inc uplink to")
            uplink_speed_match = re.findall(r"\S+\s+uplink\s+to\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(.+)",
                                            uplink_speed_command)
            uplink_list = [item for sublist in uplink_speed_match for item in sublist]

            while len(uplink_list) < 4:
                uplink_list.append('N/A')

            return {
                'Property': location,
                'CR/TR': snmp_location.upper(),
                'Type': device_type.upper(),
                'IP': device_ip,
                'Hostname': hostname,
                'Model': model,
                'Software': software_version,
                'Device Count': switch_count,
                'Serial Number 1': serial_numbers[0],
                'Serial Number 2': serial_numbers[1],
                'Serial Number 3': serial_numbers[2],
                'Serial Number 4': serial_numbers[3],
                'Uplink Interface #1': desc_matches[0],
                'Port Speed #1': uplink_list[0],
                'Port Inventory #1': uplink_list[1],
                'Neighbor #1': desc_matches[1],
                'Neighbor Interface #1': desc_matches[2],
                'Uplink Interface #2': desc_matches[3],
                'Port Speed #2': uplink_list[2],
                'Port Inventory #2': uplink_list[3],
                'Neighbor #2': desc_matches[4],
                'Neighbor Interface #2': desc_matches[5],
                'Error': "No Error"
            }

        # Gather device info for JUNOS devices
        elif device_type == 'juniper':
            # For Juniper devices, gather the hostname using 'show version'
            show_version_output = connection.send_command('show version')
            show_chassis_output = connection.send_command('show chassis hardware')
            show_int_description = connection.send_command('show interfaces descriptions')
            show_chassis_inventory = connection.send_command('show chassis hardware | find "PIC 1"')

            serial_numbers = []
            port_speed = []
            inventory = []
            device_type = 'junos'

            switch_count = 0
            for line in show_chassis_output.splitlines():
                line = line.strip()
                if line.startswith('FPC'):
                    switch_count += 1

            # Gather the hostname from 'show version'
            hostname_match = re.search(r"Hostname:\s+([^\n]+)", show_version_output)
            if hostname_match:
                hostname = hostname_match.group(1)
            else:
                hostname = "Hostname not found"

            # Gather the model from 'show version'
            model_match = re.search(r"Model:\s*(\S+.*)", show_version_output)
            if model_match:
                model = model_match.group(1).upper()
            else:
                model = "Model not found"

            # Gather the software version
            software_version_match = re.search(r"(\d+\.\d+R\d+\.\d+)", show_version_output)
            if software_version_match:
                software_version = software_version_match.group(1)
            else:
                software_version = "Software version not found"

            # Extract Serial Numbers
            for line in show_chassis_output.splitlines():
                if line.strip().startswith("FPC"):  # Only process lines starting with "FPC"
                    # Search for the serial number using regex
                    serial_match = re.search(r'([A-Za-z]+\d+)(?=\s)', line)
                    if serial_match:
                        serial_numbers.append(serial_match.group())

            # If fewer than 4 serial numbers, fill in the missing ones as "N/A"
            while len(serial_numbers) < 4:
                serial_numbers.append('N/A')

            # Filter out N/A in serial_number list and get total devices for switch_count
            filtered_serial_numbers = [item for item in serial_numbers if item != 'N/A']
            switch_count = len(filtered_serial_numbers)

            # Gather all interfaces that match uplink description pattern
            uplink_match = re.findall(
                r"(\S+)\s+(?:up|down)\s+(?:up|down)?\s*uplink to\s+([A-Za-z0-9-]+(?:[A-Za-z0-9-]+\s*)*)\s+(\S+)",
                show_int_description)
            desc_matches = [item for sublist in uplink_match for item in sublist]  # Turn tuple into list

            # Include N/A for devices without redundant uplink
            while len(desc_matches) < 6:
                desc_matches.append('N/A')

            # Gather port link speed for uplink interfaces
            uplink_speed_match = re.findall(r"(\S+)\s+(?:up|down)\s+(?:up|down)?\s*uplink to",
                                            show_int_description)
            # Run a loop for multiple uplinks to gather port speed (10Gbps, 1000mbps, etc.)
            for port in uplink_speed_match:
                uplink_gather = connection.send_command(f'show interfaces {port} | match Speed:')
                uplink_gather_match = re.search(r"Speed:\s*(\d+\s*mbps|Auto)", uplink_gather)
                port_speed.append(uplink_gather_match.group(1))

            # Add 'N/A' to 'Port Speed' in case there's only 1 uplink
            while len(port_speed) < 2:
                port_speed.append('N/A')

            # Extract SFP Inventory
            for line in show_chassis_inventory.splitlines():
                if line.strip().startswith("Xcvr"):  # Only process lines starting with "FPC"
                    # Search for the serial number using regex
                    inventory_match = re.search(r'^\s*Xcvr\s+\d+.*\s+(SFP[+-]?\d*(?:G?[A-Za-z0-9\-]+)*)\s*$', line)
                    if inventory_match:
                        inventory.append(inventory_match.group(1))

            # Add 'N/A' to 'Inventory' in case there's only 1 uplink
            while len(inventory) < 2:
                inventory.append('N/A')

            # Extract CR/TR
            connection.send_command_timing('configure')
            show_cr_tr_location = connection.send_command('show snmp location')

            return {
                'Property': location,
                'CR/TR': show_cr_tr_location,
                'Type': device_type.upper(),
                'IP': device_ip,
                'Hostname': hostname,
                'Model': model,
                'Software': software_version,
                'Device Count': switch_count,
                'Serial Number 1': serial_numbers[0],
                'Serial Number 2': serial_numbers[1],
                'Serial Number 3': serial_numbers[2],
                'Serial Number 4': serial_numbers[3],
                'Uplink Interface #1': desc_matches[0],
                'Port Speed #1': port_speed[0],
                'Port Inventory #1': inventory[0],
                'Neighbor #1': desc_matches[1],
                'Neighbor Interface #1': desc_matches[2],
                'Uplink Interface #2': desc_matches[3],
                'Port Speed #2': port_speed[1],
                'Port Inventory #2': inventory[1],
                'Neighbor #2': desc_matches[4],
                'Neighbor Interface #2': desc_matches[5],
                'Error': "No Error"
            }

        # Gather device info for NX-OS devices
        if device_type == 'nx-os':
            # Gather information from 'show version'
            show_version_output = connection.send_command('show version')
            show_inventory_output = connection.send_command('show inventory')
            show_cr_tr_location = connection.send_command('show snmp location')
            show_int_description = connection.send_command('show interfaces description')

            # Extract Hostname
            hostname_match = connection.send_command('show hostname')
            print(hostname_match)

            # Extract Model
            model_match = re.search(r"(?<=cisco )[^(]*", show_version_output)
            if model_match:
                model = model_match.group(0)
                print(model)
            else:
                model = "Model not found"

            # Extract Software Version
            software_version_match = re.search(r"(?<=System version: )[^\n]*", show_version_output)
            if software_version_match:
                software_version = software_version_match.group(0)
                print(software_version)
            else:
                software_version = "Software version not found"

            # Extract Serial Numbers (From show inventory or show version)
            serial_match = re.findall(r"NAME: \"Chassis\"[^\n]*\n.*?SN:\s*([a-zA-Z0-9]+)", show_inventory_output, re.DOTALL)
            print(serial_match)
            serial_numbers = serial_match[:4]  # Limit to 4 serial numbers if there are more

            # If fewer than 4 serial numbers, fill in the missing ones as "N/A"
            while len(serial_numbers) < 4:
                serial_numbers.append('N/A')

            # Filter out N/A in serial_number list and get total devices for switch_count
            filtered_serial_numbers = [item for item in serial_numbers if item != 'N/A']
            switch_count = len(filtered_serial_numbers)

            # Regex to extract "CR" or "TR" from snmp location
            snmp_match = re.search(r"\b(?:CR|TR)\d+\b", show_cr_tr_location)
            if snmp_match:
                snmp_location = snmp_match.group(0)
            else:
                snmp_location = ""

            # Gather all interfaces that match uplink description pattern
            uplink_match = re.findall(r"(\S+)\s+(?:up|down)\s+(?:up|down)?\s*uplink to\s+([A-Za-z0-9-]+(?:"
                                      r"[A-Za-z0-9-]+\s*)*)\s+(\S+)", show_int_description)
            desc_matches = [item for sublist in uplink_match for item in sublist]  # Turn tuple into list

            # Include N/A for devices without redundant uplink
            while len(desc_matches) < 6:
                desc_matches.append('N/A')

            # Gather port link speed for uplink interfaces
            uplink_speed_command = connection.send_command(f"show int status | inc uplink to")
            uplink_speed_match = re.findall(r"\S+\s+uplink\s+to\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(.+)",
                                            uplink_speed_command)
            uplink_list = [item for sublist in uplink_speed_match for item in sublist]

            while len(uplink_list) < 4:
                uplink_list.append('N/A')

            return {
                'Property': location,
                'CR/TR': snmp_location.upper(),
                'Type': device_type.upper(),
                'IP': device_ip,
                'Hostname': hostname_match.strip(),
                'Model': model.strip(),
                'Software': software_version,
                'Device Count': switch_count,
                'Serial Number 1': serial_numbers[0],
                'Serial Number 2': serial_numbers[1],
                'Serial Number 3': serial_numbers[2],
                'Serial Number 4': serial_numbers[3],
                'Uplink Interface #1': desc_matches[0],
                'Port Speed #1': uplink_list[0],
                'Port Inventory #1': uplink_list[1],
                'Neighbor #1': desc_matches[1],
                'Neighbor Interface #1': desc_matches[2],
                'Uplink Interface #2': desc_matches[3],
                'Port Speed #2': uplink_list[2],
                'Port Inventory #2': uplink_list[3],
                'Neighbor #2': desc_matches[4],
                'Neighbor Interface #2': desc_matches[5],
                'Error': "No Error"
            }

        connection.disconnect()

    except Exception as e:
        print(f"An error occurred with device {device_ip}: {e}\n")
        return {
            'Property': location,
            'CR/TR': "Error",
            'Type': "Error",
            'IP': device_ip,
            'Hostname': "Error",
            'Model': "Error",
            'Software': "Error",
            'Device Count': "Error",
            'Serial Number 1': "Error",
            'Serial Number 2': "Error",
            'Serial Number 3': "Error",
            'Serial Number 4': "Error",
            'Uplink Interface #1': "Error",
            'Port Speed #1': "Error",
            'Port Inventory #1': "Error",
            'Neighbor #1': "Error",
            'Neighbor Interface #1': "Error",
            'Uplink Interface #2': "Error",
            'Port Speed #2': "Error",
            'Port Inventory #2': "Error",
            'Neighbor #2': "Error",
            'Neighbor Interface #2': "Error",
            'Error': f"Error: {e}"
        }


# Function to write data to an Excel file
def write_to_excel(device_data, output_file):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Device Info"

    # Add headers including serial numbers
    headers = ["Property", "CR/TR", "Type", "IP", "Hostname", "Model", "Software", "Device Count",
               "Serial Number 1", "Serial Number 2", "Serial Number 3", "Serial Number 4", "Uplink Interface #1",
               "Port Speed #1", "Port Inventory #1", "Neighbor #1", "Neighbor Interface #1", "Uplink Interface #2",
               "Port Speed #2", "Port Inventory #2", "Neighbor #2", "Neighbor Interface #2", "Error"]
    sheet.append(headers)

    # Add device data
    for device in device_data:
        sheet.append([device['Property'], device['CR/TR'], device['Type'], device['IP'], device['Hostname'],
                      device['Model'], device['Software'], device['Device Count'], device['Serial Number 1'],
                      device['Serial Number 2'], device['Serial Number 3'], device['Serial Number 4'],
                      device['Uplink Interface #1'], device['Port Speed #1'], device['Port Inventory #1'],
                      device['Neighbor #1'], device['Neighbor Interface #1'], device['Uplink Interface #2'],
                      device['Port Speed #2'], device['Port Inventory #2'], device['Neighbor #2'],
                      device['Neighbor Interface #2'], device['Error']])

    # Save the Excel file
    workbook.save(output_file)
    print(f"Data exported to {output_file}")


# Main function to process the devices
def main():
    output_file = '%Y-%m-%d_device_info.xlsx'

    device_ips = read_device_ips()
    device_data = []

    for device_ip in device_ips:
        print(f"Connecting to {device_ip}...")
        device = gather_device_info(device_ip)
        if device:
            device_data.append(device)

    write_to_excel(device_data, output_file)


# Get credentials from the user
username = input("Enter username: ")  # Replace with your username
password = input("Enter password: ")  # Replace with your password

if __name__ == "__main__":
    main()
