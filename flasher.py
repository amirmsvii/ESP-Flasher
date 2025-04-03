import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
import subprocess
import threading
import serial.tools.list_ports #type: ignore[import]
import os
import datetime
import re
import json

class BatchFlasherGUI:
    def __init__(self, root):
        self.root = root
        root.title("ESP32 Production Flasher")
        root.geometry("700x600")
        # Add icon
        def resource_path(relative_path):
            try:
                base_path = sys._MEIPASS # type: ignore[reportGeneralTypeIssues]
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)
        try:
            icon_path = resource_path('flasher_icon.png')
            icon = tk.PhotoImage(file=icon_path)
            root.iconphoto(False, icon)
        except tk.TclError:
            pass

        # Variables
        self.firmware_path = tk.StringVar()
        self.log_file = "flash_log.txt"
        self.device_db = "device_database.json"
        
        # Initialize device database
        if not os.path.exists(self.device_db):
            with open(self.device_db, 'w') as f:
                json.dump([], f)
                
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Firmware selection
        firmware_frame = ttk.LabelFrame(main_frame, text="Firmware", padding="10")
        firmware_frame.pack(fill=tk.X, pady=5)
        
        ttk.Entry(firmware_frame, textvariable=self.firmware_path, width=50).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        ttk.Button(firmware_frame, text="Browse", command=self.browse_firmware).pack(side=tk.RIGHT)
        
        # Port selection
        port_frame = ttk.LabelFrame(main_frame, text="ESP32 Devices", padding="10")
        port_frame.pack(fill=tk.X, pady=5)
        
        self.ports_frame = ttk.Frame(port_frame)
        self.ports_frame.pack(fill=tk.X, pady=5)
        
        port_button_frame = ttk.Frame(port_frame)
        port_button_frame.pack(fill=tk.X)
        
        ttk.Button(port_button_frame, text="Refresh Ports", command=self.refresh_ports).pack(side=tk.LEFT, padx=5)
        ttk.Button(port_button_frame, text="Select All", command=lambda: self.select_all(True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(port_button_frame, text="Deselect All", command=lambda: self.select_all(False)).pack(side=tk.LEFT, padx=5)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(action_frame, text="Flash Selected Devices", command=self.flash_devices).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Device History", command=self.view_device_history).pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, pady=5)
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log = scrolledtext.ScrolledText(log_frame, height=15)
        self.log.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Initialize
        self.refresh_ports()
        self.log_message("ESP32 Production Flasher initialized")
        
    def browse_firmware(self):
        filename = filedialog.askopenfilename(
            title="Select Firmware Binary",
            filetypes=(("Binary files", "*.bin"), ("All files", "*.*"))
        )
        if filename:
            self.firmware_path.set(filename)
            self.log_message(f"Selected firmware: {filename}")
    
    def refresh_ports(self):
        # Clear previous ports
        for widget in self.ports_frame.winfo_children():
            widget.destroy()
            
        # Get available ports
        self.available_ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_vars = {}
        
        if not self.available_ports:
            ttk.Label(self.ports_frame, text="No devices found").pack()
            return
            
        # Create checkboxes for each port
        for i, port in enumerate(self.available_ports):
            var = tk.BooleanVar(value=True)
            self.port_vars[port] = var
            
            # Add port info to each checkbox
            port_info = next((p for p in serial.tools.list_ports.comports() if p.device == port), None)
            description = f"{port} - {port_info.description if port_info else 'Unknown'}"
            
            frame = ttk.Frame(self.ports_frame)
            frame.pack(fill=tk.X, pady=2)
            
            cb = ttk.Checkbutton(frame, text=description, variable=var)
            cb.pack(side=tk.LEFT)
            
            # Try to get existing history
            device_info = self.get_device_history(port)
            if device_info:
                last_flashed = device_info.get('last_flashed', 'Never')
                ttk.Label(frame, text=f"Last flashed: {last_flashed}").pack(side=tk.RIGHT)
        
        self.log_message(f"Found {len(self.available_ports)} device(s)")
    
    def select_all(self, state):
        for var in self.port_vars.values():
            var.set(state)
    
    def log_message(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.log.insert(tk.END, log_entry)
        self.log.see(tk.END)
        
    def flash_devices(self):
        selected_ports = [port for port, var in self.port_vars.items() if var.get()]
        
        # Validate selections
        if not selected_ports:
            self.log_message("ERROR: No ports selected!")
            return
            
        if not self.firmware_path.get() or not os.path.exists(self.firmware_path.get()):
            self.log_message("ERROR: Please select a valid firmware file")
            return
        
        # Start flashing in a separate thread
        self.status_var.set(f"Flashing {len(selected_ports)} device(s)...")
        threading.Thread(target=self._flash_thread, args=(selected_ports,), daemon=True).start()
    
    def _flash_thread(self, ports):
        total_ports = len(ports)
        successful_flashes = 0
        
        self.progress_var.set(0)
        
        for idx, port in enumerate(ports):
            self.log_message(f"Flashing device on {port}...")
            
            # Flash the device
            flash_cmd = [
                "python", "-m", "esptool", 
                "--chip", "esp32", 
                "--port", port, 
                "--baud", "921600", 
                "write_flash", "0x0", self.firmware_path.get()
            ]
            
            flash_process = subprocess.Popen(
                flash_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW 
            )
            
            # Stream output and capture MAC address
            mac_address = None
            flash_output = ""
            
            while True:
                line = flash_process.stdout.readline()
                if not line and flash_process.poll() is not None:
                    break
                if line:
                    self.log.insert(tk.END, line)
                    self.log.see(tk.END)
                    self.root.update_idletasks()
                    flash_output += line
                    
                    # Try to extract MAC address
                    if "MAC:" in line:
                        mac_match = re.search(r'MAC: ([0-9a-fA-F:]{17})', line)
                        if mac_match:
                            mac_address = mac_match.group(1)
            
            # Update progress
            self.progress_var.set((idx + 1) / total_ports * 100)
            
            # Check if flashing was successful
            if flash_process.returncode == 0:
                self.log_message(f"SUCCESS: Device on {port} flashed successfully!")
                successful_flashes += 1
                
                # Log successful flash
                self.log_successful_flash(port, mac_address)
            else:
                self.log_message(f"ERROR: Failed to flash device on {port}")
        
        # Flashing complete
        self.log_message(f"Flashing complete. {successful_flashes} of {total_ports} devices successfully flashed.")
        self.status_var.set(f"Ready - Last operation: {successful_flashes}/{total_ports} successful")

        # After flashing loop completes
        self.log_message(f"Flashing complete. {successful_flashes} of {total_ports} devices successfully flashed.")
        self.status_var.set(f"Ready - Last operation: {successful_flashes}/{total_ports} successful")
    
        # Refresh ports list to update last flashed dates
        self.root.after(100, self.refresh_ports)  # Add this line
    
    def log_successful_flash(self, port, mac_address):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Log to file
        with open(self.log_file, "a") as f:
            f.write(f"{timestamp},{port},{mac_address},{self.firmware_path.get()}\n")
        
        # Update device database
        devices = []
        if os.path.exists(self.device_db):
            with open(self.device_db, 'r') as f:
                try:
                    devices = json.load(f)
                except json.JSONDecodeError:
                    devices = []
        
        # Find existing device or create new entry
        device_entry = next((d for d in devices if d.get('mac') == mac_address), None)
        
        if device_entry:
            device_entry['flash_count'] = device_entry.get('flash_count', 0) + 1
            device_entry['last_flashed'] = timestamp
            device_entry['last_firmware'] = os.path.basename(self.firmware_path.get())
            device_entry['port_history'] = device_entry.get('port_history', [])
            if port not in device_entry['port_history']:
                device_entry['port_history'].append(port)
        else:
            devices.append({
                'mac': mac_address,
                'first_seen': timestamp,
                'last_flashed': timestamp,
                'flash_count': 1,
                'last_firmware': os.path.basename(self.firmware_path.get()),
                'port_history': [port]
            })
        
        # Save updated database
        with open(self.device_db, 'w') as f:
            json.dump(devices, f, indent=2)
    
    def get_device_history(self, port):
        if not os.path.exists(self.device_db):
            return None
            
        try:
            with open(self.device_db, 'r') as f:
                devices = json.load(f)
                
            # Find device that was last seen on this port
            for device in devices:
                if 'port_history' in device and port in device['port_history']:
                    return device
        except:
            pass
            
        return None
    
    def view_device_history(self):
        if not os.path.exists(self.device_db):
            self.log_message("No device history available")
            return
            
        # Create new window for device history
        history_window = tk.Toplevel(self.root)
        history_window.title("Device Flash History")
        history_window.geometry("800x500")
        
        # Create treeview for devices
        columns = ("MAC Address", "First Seen", "Last Flashed", "Flash Count", "Last Firmware")
        tree = ttk.Treeview(history_window, columns=columns, show="headings")
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load device data
        try:
            with open(self.device_db, 'r') as f:
                devices = json.load(f)
                
            for device in devices:
                tree.insert("", tk.END, values=(
                    device.get('mac', 'Unknown'),
                    device.get('first_seen', 'Unknown'),
                    device.get('last_flashed', 'Unknown'),
                    device.get('flash_count', 0),
                    device.get('last_firmware', 'Unknown')
                ))
        except Exception as e:
            ttk.Label(history_window, text=f"Error loading device history: {str(e)}").pack()

if __name__ == "__main__":
    root = tk.Tk()
    app = BatchFlasherGUI(root)
    root.mainloop()