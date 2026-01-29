import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import json
from netmiko import ConnectHandler
from datetime import datetime
import ipaddress

# ---------------- CONSTANTS ---------------- #
PROPERTY_PLACEHOLDER = "Select Property"
SWITCH_PLACEHOLDER = "Select Switch"

#APP_VERSION = "v1.0.0-prod"
# or
APP_VERSION = "v1.0.0-dev"

BG = "#1e1e1e"
FG = "#e6e6e6"
ENTRY_BG = "#2b2b2b"
BTN_BG = "#3a9d23"
OUT_BG = "#111111"

now = datetime.now()
date_time = now.strftime("%Y-%m-%d %H:%M:%S")
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------- LOAD SWITCH DATA ---------------- #
try:
    with open("switches.json", "r") as f:
        SWITCHES = json.load(f)
except Exception as e:
    SWITCHES = {}
    load_error = str(e)
else:
    load_error = None

# ---------------- BUILD FLAT SEARCH INDEX ---------------- #
SWITCH_INDEX = {}
for prop, switches in SWITCHES.items():
    for name, ip in switches.items():
        display = f"{name}"
        SWITCH_INDEX[display] = (prop, name, ip)

# ---------------- OUTPUT HANDLER ---------------- #
def write_output(text, level="info"):
    output_box.configure(state="normal")
    if level == "error":
        tag = "error"
        prefix = "ERROR: "
    elif level == "success":
        tag = "success"
        prefix = "SUCCESS: "
    else:
        tag = "info"
        prefix = ""
    output_box.insert(tk.END, prefix, tag)
    output_box.insert(tk.END, text + "\n\n")
    output_box.see(tk.END)
    output_box.configure(state="disabled")

# ---------------- VLAN CHANGE LOGIC ---------------- #
def change_vlan():
    device = {
        "device_type": "cisco_ios",
        "host": ip_entry.get().strip(),
        "username": user_entry.get().strip(),
        "password": pass_entry.get().strip(),
    }

    host = ip_entry.get().strip()
    interface = int_entry.get().strip()
    vlan = vlan_entry.get().strip()
    description = desc_entry.get().strip()

    # --- Verifies IP address is in correct format --- #
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        write_output("Invalid IP address format.", "error")
        return

    # --- Only allow IPs that start with 10.154. --- #
    if not host.startswith("10.154."):
        write_output(
            f"Refusing connection to {host}.\n"
            "Only switches in the 10.154.x.x subnet are allowed.","error")
        return

    # --- Minimum required fields to be filled in to proceed --- #
    if not device["host"] or not interface or not vlan:
        write_output("Switch IP, Interface, and VLAN are required.", "error")
        return

    # ---- VLAN input validation ---- #
    if not vlan.isdigit():
        write_output("VLAN must be a numeric value.", "error")
        return

    if len(vlan) > 4:
        write_output("VLAN must be 4 digits or less.", "error")
        return

    vlan_id = int(vlan)

    reserved_vlans = {1, 7, 16, 18, 21, 26, 142, 133, 183, 184, 185, 186, 187, 201, 216, 217, 218, 233, 1002, 1003,
                      1004, 1005}

    if vlan_id in reserved_vlans:
        write_output(
            f"VLAN {vlan_id} is reserved and cannot be used.","error")
        return

    if not (2 <= vlan_id <= 4094):
        write_output(
            "VLAN must be between 2 and 4094.","error")
        return

    # --- Connects to device --- #
    try:
        output_box.configure(state="normal")

        output_box.insert(tk.END, f"[{timestamp}] ", "info")
        output_box.insert(tk.END, "Connecting ", "success")
        output_box.insert(tk.END, "to ", "info")
        output_box.insert(tk.END, f"{device['host']}", "host")  # <-- colored part
        output_box.insert(tk.END, "...\n\n", "info")

        output_box.see(tk.END)
        output_box.configure(state="disabled")

        conn = ConnectHandler(**device)
        conn.enable()

        # --- Interface status check --- #
        status = conn.send_command(f"show interface {interface} status")
        status_lower = status.lower()

        # ---- Invalid interface check ---- #
        invalid_markers = (
            "invalid input",
            "ambiguous command",
            "incomplete command",
            "invalid interface"
        )

        if any(marker in status_lower for marker in invalid_markers):
            conn.disconnect()
            write_output(f"Invalid interface '{interface}'.\n{status}","error")
            write_output(f"-----------------------------------------------------------------------------")
            return

        # --- Hard fail for forbidden states --- #
        forbidden_keywords = {"trunk", "unassigned", "routed", "161", "162", "163", "164"}

        if any(word in status_lower for word in forbidden_keywords):
            matched = [w for w in forbidden_keywords if w in status_lower]
            conn.disconnect()
            write_output(
                f"Interface contains forbidden state(s): {', '.join(matched)}\n\n{status}","error")
            return

        # --- VLAN existence check --- #
        vlan_check = conn.send_command(f"show vlan id {vlan}")
        if "not found" in vlan_check.lower():
            conn.disconnect()
            write_output(f"VLAN {vlan} does not exist.\n\n{vlan_check}", "error")
            return

        # snapshot before making changes
        snapshot_before = conn.send_command(f"show running-config interface {interface}")
        lines_before = snapshot_before.splitlines()

        # parse old VLAN & description
        old_vlan = next((line.split()[-1] for line in lines_before if "switchport access vlan" in line), "None")
        old_desc = next((line.replace("description ", "") for line in lines_before if "description" in line),
                        "None")

        # --- If interface is CONNECTED, require confirmation --- #
        if "connected" in status_lower and "notconnect" not in status_lower:
            # Attempt to extract VLAN from status output
            running_config = conn.send_command(f"show running-config interface {interface}")

            # Default VLAN if none found
            current_vlan = "Unknown"

            # Look for the line that specifies access VLAN
            for line in running_config.splitlines():
                line = line.strip()
                if line.startswith("switchport access vlan"):
                    current_vlan = line.split()[-1]  # Gets the VLAN number
                    break

            confirm = messagebox.askyesno(
                "Interface is CONNECTED",
                "⚠ THIS INTERFACE IS CURRENTLY CONNECTED ⚠\n\n"
                f"Interface: {interface}\n"
                f"Current VLAN: {current_vlan}\n"
                f"New VLAN: {vlan_entry.get().strip()}\n"
                f"Description: {old_desc}\n\n"
                "Are you sure you want to change the VLAN?"
            )

            if not confirm:
                conn.disconnect()
                write_output("Operation cancelled by user.", "info")
                return

        commands = [
            f"interface {interface}",
            f"switchport access vlan {vlan}",
        ]
        if description:
            commands.append(f"description {description}")

        conn.send_config_set(commands)
        conn.save_config()

        # snapshot after changes
        snapshot_after = conn.send_command(f"show running-config interface {interface}")
        lines_after = snapshot_after.splitlines()

        # parse new VLAN & description
        new_vlan = next((line.split()[-1] for line in lines_after if "switchport access vlan" in line), "None")
        new_desc = next((line.replace("description ", "") for line in lines_after if "description" in line),
                        "None")

        # display output with color tags
        write_output(f"{snapshot_after}\n")
        output_box.configure(state="normal")
        output_box.insert(tk.END, "INTERFACE SUMMARY\n", "host")
        output_box.insert(tk.END, "===================\n\n", "info")
        output_box.insert(tk.END, "Switch        : ", "host")
        output_box.insert(tk.END, f" {ip_entry.get()}\n", "info")
        output_box.insert(tk.END, "Interface     : ", "host")
        output_box.insert(tk.END, f" {interface}\n", "info")
        output_box.insert(tk.END, "VLAN          : ", "host")
        output_box.insert(tk.END, f" {old_vlan} → {new_vlan}\n", "info")
        output_box.insert(tk.END, "Description   : ", "host")
        output_box.insert(tk.END, f"{old_desc} →{new_desc}\n\n", "info")
        output_box.configure(state="disabled")
        write_output(f"✔ Configuration updated for {interface}", "success")
        write_output(f"-----------------------------------------------------------------------------")

        log_file = "vlan_changes.txt"

        # --- Open the file in append mode --- #
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] Username: {user_entry.get()}\n")
            f.write(f"[{timestamp}] {snapshot_after}\n")
            f.write(f"[{timestamp}] Interface: {interface}\n")
            f.write(f"[{timestamp}] Old VLAN: {old_vlan}\n")
            f.write(f"[{timestamp}] New VLAN: {new_vlan}\n")
            f.write(f"[{timestamp}] Old Description: {old_desc}\n")
            f.write(f"[{timestamp}] New Description: {new_desc}\n")
            f.write(f"[{timestamp}] Configuration updated for {interface}\n\n")
            f.write("-" * 100 + "\n\n")  # separator line

    except Exception as e:
        write_output(str(e), "error")

# ---------------- DROPDOWN LOGIC ---------------- #
def update_switch_list(*args):
    ip_entry.delete(0, tk.END)
    switch_combo.set(SWITCH_PLACEHOLDER)
    prop = property_var.get()
    if prop == PROPERTY_PLACEHOLDER:
        switch_combo["values"] = []
        return
    switches = SWITCHES.get(prop, {})
    switch_combo["values"] = sorted(switches.keys())

def fill_ip(event=None):
    prop = property_var.get()
    sw = switch_var.get()
    if prop in SWITCHES and sw in SWITCHES[prop]:
        ip_entry.delete(0, tk.END)
        ip_entry.insert(0, SWITCHES[prop][sw])
    else:
        ip_entry.delete(0, tk.END)

    # Clear the search box
    search_entry.var.set("")

# ---------------- SEARCH AUTOCOMPLETE ---------------- #
class AutocompleteEntry(tk.Entry):
    def __init__(self, master, search_index, **kwargs):
        super().__init__(master, **kwargs)
        self.master = master
        self.search_index = search_index
        self.var = self["textvariable"] = tk.StringVar()
        self.var.trace_add("write", self.on_change)

        self.listbox_window = None
        self.listbox = None
        self.matches = []

        self.keyboard_index = None
        self.keyboard_mode = False

        self.bind("<Down>", self.move_down)
        self.bind("<Up>", self.move_up)
        self.bind("<Return>", self.select_item)
        self.bind("<Escape>", self.hide_listbox)

        self.master.bind_all("<Button-1>", self.global_click, "+")

    def on_change(self, *args):
        self.keyboard_mode = False
        text = self.var.get().lower()
        self.hide_listbox()
        if not text:
            return
        self.matches = [display for display in self.search_index if text in display.lower()]
        if self.matches:
            self.show_listbox(self.matches)

    def show_listbox(self, matches):
        self.hide_listbox()
        self.listbox_window = tk.Toplevel(self)
        self.listbox_window.overrideredirect(True)
        self.listbox_window.attributes("-topmost", True)

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.listbox_window.geometry(f"{self.winfo_width()}x{min(6,len(matches))*20}+{x}+{y}")

        self.listbox = tk.Listbox(self.listbox_window, height=min(6,len(matches)))
        self.listbox.pack(fill="both", expand=True)

        for m in matches:
            self.listbox.insert(tk.END, m)

        self.listbox.bind("<ButtonRelease-1>", self.select_item)
        self.listbox.bind("<Double-Button-1>", self.select_item)
        self.listbox.bind("<Motion>", self.on_hover)

        self.keyboard_index = None
        self.keyboard_mode = False

    def on_hover(self, event):
        if self.listbox and not self.keyboard_mode:
            index = self.listbox.nearest(event.y)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.listbox.activate(index)

    def hide_listbox(self, event=None):
        self.keyboard_index = None
        self.keyboard_mode = False
        if self.listbox_window:
            self.listbox_window.destroy()
            self.listbox_window = None
            self.listbox = None

    def move_down(self, event):
        if self.listbox:
            self.keyboard_mode = True
            if self.keyboard_index is None:
                self.keyboard_index = 0
            else:
                self.keyboard_index = min(self.keyboard_index + 1, self.listbox.size() - 1)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.keyboard_index)
            self.listbox.activate(self.keyboard_index)
        return "break"

    def move_up(self, event):
        if self.listbox:
            self.keyboard_mode = True
            if self.keyboard_index is None:
                self.keyboard_index = self.listbox.size() - 1
            else:
                self.keyboard_index = max(self.keyboard_index - 1, 0)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.keyboard_index)
            self.listbox.activate(self.keyboard_index)
        return "break"

    def select_item(self, event=None):
        if not self.listbox:
            return "break"

        if event and event.widget == self.listbox and hasattr(event, "y"):
            index = self.listbox.nearest(event.y)
        elif self.keyboard_index is not None:
            index = self.keyboard_index
        else:
            index = 0

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        selection = self.listbox.get(index)

        prop, sw, ip = self.search_index[selection]
        property_var.set(prop)
        switch_var.set(sw)
        ip_entry.delete(0, tk.END)
        ip_entry.insert(0, ip)

        self.var.set(selection)
        self.hide_listbox()
        self.icursor(tk.END)
        return "break"

    def global_click(self, event):
        if self.listbox_window:
            widget = event.widget
            if widget not in (self, self.listbox) and not str(widget).startswith(str(self.listbox)):
                self.hide_listbox()

# ---------------- GUI SETUP ---------------- #
root = tk.Tk()
root.title("CEN VLAN Tool")
root.geometry("900x600")
root.configure(bg=BG)
root.resizable(True, True)

# ---------------- STYLE ---------------- #
style = ttk.Style()
style.theme_use("default")
style.configure("TCombobox", fieldbackground="white", background="white")

# ================= TOP ROW ================= #
top = tk.Frame(root, bg=BG)
top.pack(fill="x", padx=12, pady=(10,4))

property_var = tk.StringVar(value=PROPERTY_PLACEHOLDER)
switch_var = tk.StringVar(value=SWITCH_PLACEHOLDER)

top.columnconfigure(1, weight=1)
top.columnconfigure(3, weight=1)
top.columnconfigure(5, weight=2)

tk.Label(top, text="Property", bg=BG, fg=FG).grid(row=0, column=0, sticky="w", padx=(0,6))
property_combo = ttk.Combobox(
    top,
    textvariable=property_var,
    state="readonly",
    values=[PROPERTY_PLACEHOLDER]+sorted(SWITCHES.keys()),
)
property_combo.grid(row=0, column=1, sticky="ew", padx=(0,12))
property_var.trace_add("write", update_switch_list)

tk.Label(top, text="Switch", bg=BG, fg=FG).grid(row=0, column=2, sticky="w", padx=(0,6))
switch_combo = ttk.Combobox(
    top,
    textvariable=switch_var,
    state="readonly",
)
switch_combo.grid(row=0, column=3, sticky="ew", padx=(0,12))
switch_combo.bind("<<ComboboxSelected>>", fill_ip)

tk.Label(top, text="Search Switch", bg=BG, fg=FG).grid(row=0, column=4, sticky="w", padx=(0,6))
search_entry = AutocompleteEntry(top, SWITCH_INDEX, bg=ENTRY_BG, fg=FG, insertbackground=FG)
search_entry.grid(row=0, column=5, sticky="ew")

# ================= MAIN AREA ================= #
main = tk.Frame(root, bg=BG)
main.pack(fill="both", expand=True)

left = tk.Frame(main, bg=BG)
left.pack(side="left", padx=12, pady=10, anchor="n")

divider = tk.Frame(main, bg="white", width=3)
divider.pack(side="left", fill="y", padx=6, pady=10)

right = tk.Frame(main, bg=BG)
right.pack(side="left", padx=12, pady=10, fill="both", expand=True)

# ---------------- LEFT INPUTS ---------------- #
def label(text):
    return tk.Label(left, text=text, bg=BG, fg=FG, anchor="w")

def entry(show=None):
    return tk.Entry(left, width=28, bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat", show=show)

label("Switch IP").pack(anchor="w")
ip_entry = entry()
ip_entry.pack(pady=(0,6))

label("Username").pack(anchor="w")
user_entry = entry()
user_entry.pack(pady=(0,6))

label("Password").pack(anchor="w")
pass_entry = entry(show="*")
pass_entry.pack(pady=(0,6))

label("Interface").pack(anchor="w")
int_entry = entry()
int_entry.pack(pady=(0,6))

label("VLAN ID").pack(anchor="w")
vlan_entry = entry()
vlan_entry.pack(pady=(0,6))

label("Description (optional)").pack(anchor="w")
desc_entry = entry()
desc_entry.pack(pady=(0,12))

tk.Button(
    left,
    text="CHANGE VLAN",
    command=change_vlan,
    bg=BTN_BG,
    fg="white",
    relief="flat",
    height=2,
    width=24,
).pack()

version_label = tk.Label(
    root,
    text=f"Version: {APP_VERSION}",
    font=("Consolas", 9),
    bg=BG,
    fg="gray40")

version_label.place(x=6, rely=1.0, anchor="sw")

# ---------------- OUTPUT PANEL ---------------- #
tk.Label(right, text="Output", bg=BG, fg=FG).pack(anchor="w")
output_box = tk.Text(right, bg=OUT_BG, fg=FG, insertbackground=FG, relief="flat", wrap="word")
output_box.pack(fill="both", expand=True)

output_box.tag_config("error", foreground="red", font=("Consolas",10,"bold"))
output_box.tag_config("success", foreground="lime", font=("Consolas",10,"bold"))
output_box.tag_config("info", foreground="white", font=("Consolas",10))
output_box.tag_config("host", foreground="#FF7A7A", font=("Consolas", 10, "bold"))
output_box.configure(state="disabled")

# ---------------- MINIMUM SIZE ---------------- #
root.update_idletasks()
root.minsize(root.winfo_width(), root.winfo_height())

# ---------------- JSON LOAD ERROR ---------------- #
if load_error:
    write_output(f"Failed to load switches.json:\n{load_error}", "error")

root.mainloop()