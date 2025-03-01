import re
from netmiko import ConnectHandler
from datetime import timedelta

total_vlan_changes = 0


# Function to connect to the Cisco device and return the connection object
def create_connection(device_ip, username, password):
    """Create and return a connection handler object."""
    device = {
        'device_type': 'cisco_ios',
        'host': device_ip,
        'username': username,
        'password': password,
    }

    try:
        net_connect = ConnectHandler(**device)
        print(f"*** Successfully connected to {device_ip} ***")
        return net_connect
    except Exception as e:
        print(f"Error connecting to device {device_ip}: {e}")
        return None


# Function to retrieve the list of interfaces status
def get_interfaces_status(net_connect):
    """Retrieve list of interfaces and their status."""
    try:
        output = net_connect.send_command('show interfaces status')  # Retrieve interface status
        return output
    except Exception as e:
        print(f"Error retrieving interfaces status: {e}")
        return None


# Function to retrieve detailed interface information
def get_interface_details(net_connect, interface):
    """Retrieve detailed information for a specific interface."""
    try:
        command = f"show interfaces {interface}"
        output = net_connect.send_command(command)  # Retrieve interface details
        return output
    except Exception as e:
        print(f"Error retrieving details for interface {interface}: {e}")
        return None


# Function to parse last input and last output times
def parse_last_input_output(output):
    """Extract 'Last input' and 'Last output' times from the interface details."""
    last_input_regex = re.compile(r'Last input\s+(?P<last_input>[\w\d]+(?:w\d+d|d)?),\s+output\s+(?P<last_output>[\w\d]+(?:w\d+d|d)?)')

    match = last_input_regex.search(output)
    if match:
        last_input = match.group('last_input')
        last_output = match.group('last_output')
        return last_input, last_output
    else:
        print("No match found for last input and last output.")
        return None, None


# Function to convert time string to timedelta
def parse_time_to_timedelta(time_str):
    """Convert time strings like '12w6d', '6d23h', etc., to timedelta."""
    weeks_regex = re.compile(r'(?P<weeks>\d+)w')
    days_regex = re.compile(r'(?P<days>\d+)d')
    hours_regex = re.compile(r'(?P<hours>\d+)h')
    time_regex = re.compile(r'(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)')

    total_days, total_hours, total_minutes, total_seconds = 0, 0, 0, 0

    if 'never' in time_str.lower():
        return timedelta(days=365)  # Return timedelta() for 'never'

    weeks_match = weeks_regex.search(time_str)
    days_match = days_regex.search(time_str)
    hours_match = hours_regex.search(time_str)
    time_match = time_regex.search(time_str)

    if weeks_match:
        total_days += int(weeks_match.group('weeks')) * 7
    if days_match:
        total_days += int(days_match.group('days'))
    if hours_match:
        total_hours += int(hours_match.group('hours'))
    if time_match:
        total_hours += int(time_match.group('hours'))
        total_minutes += int(time_match.group('minutes'))
        total_seconds += int(time_match.group('seconds'))

    timedelta_result = timedelta(days=total_days, hours=total_hours, minutes=total_minutes, seconds=total_seconds)
    return timedelta_result


# Function to change the VLAN of an interface
def change_vlan(net_connect, interface, new_vlan):
    """Change the VLAN of the interface."""
    try:
        command = [f'interface {interface}', f'switchport access vlan {new_vlan}']
        net_connect.send_config_set(command)
        print(f"VLAN on interface {interface} changed to {new_vlan}")
    except Exception as e:
        print(f"Error changing VLAN on interface {interface}: {e}")


# Main function to check interfaces and change VLAN if necessary
def check_and_change_vlan(device_ip, username, password, time_threshold, new_vlan, vlan_change_counter):
    """Check interfaces on the device and change VLAN if they meet criteria."""
    # Create connection once and reuse
    net_connect = create_connection(device_ip, username, password)
    if not net_connect:
        print(f"Failed to connect to {device_ip}")
        return vlan_change_counter

    # Step 1: Retrieve the list of interfaces
    output = get_interfaces_status(net_connect)
    if output:
        # Step 2: Parse interfaces that are 'notconnect' and are not on VLAN 169
        interfaces = re.findall(r'(^\S+)\s+(?:.{0,25})\s+notconnect\s+(\S+)\s+', output, re.MULTILINE)
        interfaces_to_check = [interface for interface, vlan in interfaces if vlan not in ['169', 'trunk', 'unassigned',
                                                                                           '161', '162', '163', '164']]
        if len(interfaces_to_check) > 0:

            for interface in interfaces_to_check:
                print(f"Checking interface {interface}...")

                # Step 3: Retrieve detailed information about each interface
                interface_output = get_interface_details(net_connect, interface)

                if interface_output:
                    last_input, last_output = parse_last_input_output(interface_output)

                    if last_input and last_output:
                        # Step 4: Convert times and compare them against the threshold
                        last_input_time = parse_time_to_timedelta(last_input)
                        last_output_time = parse_time_to_timedelta(last_output)

                        # If either last_input_time or last_output_time exceeds the threshold, change the VLAN
                        if last_input_time >= time_threshold and last_output_time >= time_threshold:
                            print(f"Interface {interface} has been inactive for "
                                  f"Last input: {last_input_time.days} days, Last output: {last_output_time.days} days")
                            change_vlan(net_connect, interface, new_vlan)

                            # Increment the VLAN change counter
                            vlan_change_counter += 1
                        else:
                            print(f"Interface {interface} has been inactive for "
                                  f"Last input: {last_input_time.days} days, Last output: {last_output_time.days} days")
                            print(f"Interface {interface} is currently ACTIVE")
        else:
            print("-- No inactive interfaces --")
    else:
        print(f"Failed to retrieve interfaces from {device_ip}")

    # Close the connection after use
    net_connect.disconnect()
    return vlan_change_counter


# Main Execution
if __name__ == "__main__":
    # Device credentials
    username = input("Enter username: ")  # Replace with your username
    password = input("Enter password: ")  # Replace with your password

    # Time threshold: interfaces disconnected for more than 2 weeks
    time_threshold = timedelta(weeks=2)

    # The new VLAN to assign
    new_vlan = 169  # Replace with your desired VLAN ID

    # Read device IP addresses from the file
    with open('IOS_Test.txt', 'r') as file:
        device_ips = file.readlines()

    # Loop through each device IP from the file and run the check
    for device_ip in device_ips:
        device_ip = device_ip.strip()  # Remove any extra whitespace or newline characters
        if device_ip:  # Skip empty lines
            # Start VLAN counter for each device
            vlan_change_counter = 0
            # Execute the check and change VLAN logic for each device
            vlan_change_counter = check_and_change_vlan(device_ip, username, password, time_threshold, new_vlan,
                                                        vlan_change_counter)

            # Add the device's VLAN changes to the global total
            total_vlan_changes += vlan_change_counter

    # Print the total VLAN changes after all devices are processed
    print(f"\nTotal VLAN changes made across all devices: {total_vlan_changes}")
