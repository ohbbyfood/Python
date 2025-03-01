import re
from netmiko import ConnectHandler
from openpyxl import Workbook


# Function to connect to the device and run the command to get interface status and hostname
def get_device_data(connection, device_type):
    try:
        # Send command to get interface status depending on the device type
        if device_type == 'cisco_ios' or device_type == 'cisco_xe':
            output_interfaces = connection.send_command('show interfaces status')

            # Send command to get hostname for Cisco devices
            hostname_match = re.search(r"^hostname\s+(\S+)", connection.send_command('show running-config | include hostname'))
            if hostname_match:
                hostname = hostname_match.group(1)
            else:
                hostname = "Hostname not found"

        elif device_type == 'juniper':
            output_interfaces = connection.send_command('show ethernet-switching interfaces')

            # Send command to get hostname for Juniper devices
            hostname_match = re.search(r"Hostname:\s+([^\n]+)", connection.send_command('show version'))
            if not hostname_match:
                hostname_match = re.search(r"system hostnames\s+([^\n]+)", connection.send_command('show configuration system hostnames'))

            if hostname_match:
                hostname = hostname_match.group(1)
            else:
                hostname = "Hostname not found"

        else:
            output_interfaces = "Unsupported device type"
            hostname = "Unknown"

        return output_interfaces, hostname, None  # Return None for error

    except Exception as e:
        # Return None for output data and hostname, with the error message
        return None, None, str(e)


# Function to process the show interfaces status output and filter based on the criteria
def process_output(output, device_type):
    # Regular expression to match lines in the 'show ethernet-switching interfaces' output for Juniper
    if device_type == 'juniper':
        # Adjusted regex for Juniper `show ethernet-switching interfaces` output
        regex = re.compile(r'^(?P<interface>\S+)\s+(?P<state>\S+)\s+(?P<vlan_members>\S+)\s+.*$', re.MULTILINE)

        # Filter out lines starting with "Interface"
        lines = output.splitlines()
        lines = [line for line in lines if not line.startswith('Interface')]  # Exclude header lines
        filtered_output = "\n".join(lines)
    else:
        # Adjusted regex for Cisco IOS and IOS XE `show interfaces status` output
        regex = re.compile(
            r'^(?P<interface>\S+)\s+(?P<description>.*?)\s+(?P<status>connected|notconnect)\s+(?P<vlan>\S+)\s+.*$',
            re.MULTILINE)

        # Split the output into lines
        lines = output.splitlines()
        lines = [line for line in lines if not line.startswith('Port')]  # Exclude header lines

        # Rejoin the filtered lines back into a single string for regex processing
        filtered_output = "\n".join(lines)

    # Find all matches using the regex
    matches = regex.findall(filtered_output)

    # Filtered lines for juniper
    if device_type == 'juniper':
        filtered_matches = [match for match in matches if match[2] not in ["vlan169", "vlan1", "default", "mgmt"]]
    # Filtered lines for Cisco
    else:
        filtered_matches = [match for match in matches if match[3] not in ["169", "trunk", "1", "unassigned", "routed",
                                                                           "161", "162", "163", "164", "4094"]]

    return filtered_matches


# Function to export the data to an Excel file (overwrites the file each time)
def export_to_excel(data, hostname, ip_address, device_type, error_message, wb, ws):

    # Gather property
    if ip_address.startswith(('10.154.216.', '10.154.217.')):
        location = 'ARIA'
    elif ip_address.startswith(('10.154.16.', '10.154.18.')):
        location = 'BEL'
    elif ip_address.startswith('10.154.36.'):
        location = 'CSC'
    elif ip_address.startswith('10.154.201.'):
        location = 'EXCAL'
    elif ip_address.startswith('10.154.142.'):
        location = 'LUX'
    elif ip_address.startswith(('10.154.183.', '10.154.184.', '10.154.185.', '10.154.186.', '10.154.187.')):
        location = 'MBAY'
    elif ip_address.startswith(('10.154.233.', '10.154.7.')):
        location = 'MGM'
    elif ip_address.startswith('10.154.21.'):
        location = 'NYNY'
    elif ip_address.startswith('10.154.133'):
        location = 'PARK'
    elif ip_address.startswith('10.154.26.'):
        location = 'TCOLV'
    elif ip_address.startswith('10.154.218.'):
        location = 'VDARA'
    else:
        location = 'FALSE'

    # If there's an error, ensure it's recorded in Excel
    if error_message:
        ws.append([location, 'N/A', ip_address, "N/A", "N/A", '', "N/A", "N/A", error_message])
        return

    # Only export if we have data
    if not data:
        return  # Skip if there's no relevant data

    # Add the data to the sheet
    for row in data:
        if device_type == 'juniper':
            ws.append(
                [location, hostname, ip_address, device_type, row[0], '', row[2], row[1],
                 "N/A"])  # For Juniper, add state as status
        else:
            ws.append([location, hostname, ip_address, device_type, row[0], row[1], row[3],
                       row[2], "N/A"])  # For Cisco, add status in a separate column


def main():
    # Create a new workbook and sheet (this is done once at the start)
    wb = Workbook()
    ws = wb.active
    ws.title = "Interface Status"

    # Add headers to the Excel file
    ws.append(["Location", "Hostname", "IP Address", "Device Type", "Interface", "Description/State", "VLAN", "Status",
               "Error"])

    # Read device IP addresses from the file
    with open('IOS_Test.txt', 'r') as file:
        device_ips = file.readlines()

    # Define credentials (assuming same credentials for all devices)
    username = input("Enter username: ")  # Replace with your username
    password = input("Enter password: ")  # Replace with your password

    # Loop through each IP address from the file
    for device_ip in device_ips:
        device_ip = device_ip.strip()  # Remove any extra whitespace or newline characters
        if device_ip:  # Skip empty lines
            print(f"Connecting to device {device_ip}...")

            # Check device type and connect accordingly
            try:
                # Create device connection object based on the device type
                device = {
                    'device_type': 'cisco_ios',  # Default type, will be changed if needed
                    'host': device_ip,
                    'username': username,
                    'password': password,
                    'secret': password,  # Enable password if needed
                }

                # Establish SSH connection to the device
                with ConnectHandler(**device) as connection:
                    # Dynamically detect device type
                    prompt = connection.send_command('show version')
                    if re.search(r"NX-OS", prompt, re.IGNORECASE):
                        device_type = 'cisco_nxos'
                    elif re.search(r'Adaptive Security Appliance', prompt, re.IGNORECASE):
                        device_type = 'asa'
                    elif re.search(r'IOS-XE|IOS', prompt, re.IGNORECASE):
                        device_type = 'cisco_ios'
                    elif re.search(r'JUNOS', prompt, re.IGNORECASE):
                        device_type = 'juniper'  # If Juniper device is detected
                    else:
                        device_type = 'unknown'
                        print(f"Unknown device type for {device_ip}. Using 'cisco_ios' as fallback.")
                        device_type = 'cisco_ios'  # Default to Cisco if unknown

                    print(f"Device type detected: {device_type}")

                    # Get the output of the command (interface status and hostname)
                    output_interfaces, hostname, error_message = get_device_data(connection, device_type)

                    # If the connection failed, log the error and continue to next device
                    if error_message:
                        print(f"Error connecting to {device_ip}: {error_message}")
                        # Export the error message to the Excel file
                        export_to_excel([], "N/A", device_ip, device_type, error_message, wb, ws)
                        continue

                    # Process the output to filter the necessary data
                    filtered_data = process_output(output_interfaces, device_type)

                    # Export the data to Excel if there are any filtered matches
                    if filtered_data:
                        export_to_excel(filtered_data, hostname, device_ip, device_type, "", wb, ws)

                    # If no relevant data was found, print a message and continue
                    if not filtered_data:
                        print(f"*** No device data for {device_ip} ***")  # Print this message when no interfaces are # found
                        continue

            except Exception as e:
                print(f"Failed to connect to {device_ip}. Error: {str(e)}")
                export_to_excel([], "N/A", device_ip, 'unknown', str(e), wb, ws)

    # Save the workbook after all devices are processed
    wb.save("interface_status.xlsx")
    print(f"Data has been saved to 'interface_status.xlsx'")


if __name__ == "__main__":
    main()
