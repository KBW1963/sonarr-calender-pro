#!/usr/bin/env python3
"""
Sonarr Calendar Tracker Pro - Configuration Setup Tool
Creates and saves configuration settings to a hidden file
Now with refresh interval in hours
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / '.sonarr_calendar_config.json'

class SonarrConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sonarr Calendar Pro - Configuration Setup")
        self.root.geometry("800x850")
        self.root.resizable(False, False)
        
        # Set icon if available
        try:
            self.root.iconbitmap(default='icon.ico')
        except:
            pass
        
        # Center the window
        self.center_window()
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="Sonarr Calendar Pro - Configuration", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Sonarr Configuration Section
        self.create_section_header(main_frame, "Sonarr Connection Settings", 1)
        
        # Sonarr URL
        ttk.Label(main_frame, text="Sonarr URL:", font=('Arial', 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.sonarr_url = ttk.Entry(main_frame, width=50, font=('Arial', 10))
        self.sonarr_url.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Label(main_frame, text="e.g., http://192.168.1.100:8989", 
                 font=('Arial', 8), foreground='gray').grid(row=3, column=1, sticky=tk.W, padx=(10, 0))
        
        # Sonarr API Key
        ttk.Label(main_frame, text="API Key:", font=('Arial', 10)).grid(row=4, column=0, sticky=tk.W, pady=5)
        self.sonarr_api_key = ttk.Entry(main_frame, width=50, font=('Arial', 10))
        self.sonarr_api_key.grid(row=4, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        ttk.Label(main_frame, text="Find this in Sonarr > Settings > General", 
                 font=('Arial', 8), foreground='gray').grid(row=5, column=1, sticky=tk.W, padx=(10, 0))
        
        # Test Connection Button
        self.test_btn = ttk.Button(main_frame, text="Test Connection", command=self.test_connection)
        self.test_btn.grid(row=6, column=1, sticky=tk.W, pady=10, padx=(10, 0))
        self.connection_status = ttk.Label(main_frame, text="", font=('Arial', 9))
        self.connection_status.grid(row=6, column=2, sticky=tk.W, pady=10)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=7, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=20)
        
        # Date Range Configuration Section
        self.create_section_header(main_frame, "Date Range Settings", 8)
        
        # Days Past
        ttk.Label(main_frame, text="Days to Look Back:", font=('Arial', 10)).grid(row=9, column=0, sticky=tk.W, pady=5)
        self.days_past = ttk.Spinbox(main_frame, from_=0, to=90, width=10, font=('Arial', 10))
        self.days_past.grid(row=9, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.days_past.set(7)
        ttk.Label(main_frame, text="(0-90 days)", font=('Arial', 8), foreground='gray').grid(row=9, column=2, sticky=tk.W)
        
        # Days Future
        ttk.Label(main_frame, text="Days to Look Forward:", font=('Arial', 10)).grid(row=10, column=0, sticky=tk.W, pady=5)
        self.days_future = ttk.Combobox(main_frame, values=[7, 14, 30, 60, 90, 180, 365], width=8, font=('Arial', 10), state='readonly')
        self.days_future.grid(row=10, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.days_future.set(30)
        ttk.Label(main_frame, text="(7-365 days)", font=('Arial', 8), foreground='gray').grid(row=10, column=2, sticky=tk.W)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=11, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=20)
        
        # File Paths Configuration Section
        self.create_section_header(main_frame, "File & Directory Settings", 12)
        
        # Output HTML File
        ttk.Label(main_frame, text="HTML Output File:", font=('Arial', 10)).grid(row=13, column=0, sticky=tk.W, pady=5)
        self.output_html = ttk.Entry(main_frame, width=45, font=('Arial', 10))
        self.output_html.grid(row=13, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Button(main_frame, text="Browse", command=lambda: self.browse_file(self.output_html, "HTML Files", "*.html")).grid(row=13, column=3, padx=(5, 0))
        
        # Output JSON File (Optional)
        ttk.Label(main_frame, text="JSON Output File (Optional):", font=('Arial', 10)).grid(row=14, column=0, sticky=tk.W, pady=5)
        self.output_json = ttk.Entry(main_frame, width=45, font=('Arial', 10))
        self.output_json.grid(row=14, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Button(main_frame, text="Browse", command=lambda: self.browse_file(self.output_json, "JSON Files", "*.json")).grid(row=14, column=3, padx=(5, 0))
        
        # Image Cache Directory
        ttk.Label(main_frame, text="Image Cache Directory:", font=('Arial', 10)).grid(row=15, column=0, sticky=tk.W, pady=5)
        self.image_cache = ttk.Entry(main_frame, width=45, font=('Arial', 10))
        self.image_cache.grid(row=15, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Button(main_frame, text="Browse", command=lambda: self.browse_directory(self.image_cache)).grid(row=15, column=3, padx=(5, 0))
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=16, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=20)
        
        # Refresh Configuration Section
        self.create_section_header(main_frame, "Refresh Settings", 17)
        
        # Refresh Interval - NOW IN HOURS
        ttk.Label(main_frame, text="Auto-Refresh Interval:", font=('Arial', 10)).grid(row=18, column=0, sticky=tk.W, pady=5)
        self.refresh_interval = ttk.Combobox(main_frame, values=[1, 2, 3, 4, 6, 8, 12, 24, 48, 72, 168], width=8, font=('Arial', 10), state='readonly')
        self.refresh_interval.grid(row=18, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.refresh_interval.set(6)  # Default 6 hours
        ttk.Label(main_frame, text="hours (1-168 hours / 7 days)", font=('Arial', 8), foreground='gray').grid(row=18, column=2, sticky=tk.W)
        
        # Info text about refresh
        ttk.Label(main_frame, text="⏰"" The script will automatically refresh the calendar at this interval", 
                 font=('Arial', 10 ), foreground='#666666').grid(row=19, column=1, columnspan=2, sticky=tk.W, padx=(10, 0), pady=(0, 10))
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=20, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=20)
        
        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=21, column=0, columnspan=4, pady=20)
        
        self.save_btn = ttk.Button(button_frame, text="💾 Save Configuration", command=self.save_configuration, width=25)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        self.load_btn = ttk.Button(button_frame, text="📂 Load Configuration", command=self.load_configuration, width=25)
        self.load_btn.pack(side=tk.LEFT, padx=5)
        
        self.default_btn = ttk.Button(button_frame, text="🔄 Reset to Defaults", command=self.reset_defaults, width=25)
        self.default_btn.pack(side=tk.LEFT, padx=5)
              
        self.exit_btn = ttk.Button(button_frame, text="🚪 Exit", command=self.root.quit, width=20)
        self.exit_btn.pack()
        
        # Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready to configure...")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        status_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Load existing configuration if available
        self.load_configuration()
    
    def center_window(self):
        """Center the window on the screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_section_header(self, parent, text, row):
        """Create a section header with underline"""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 5))
        
        label = ttk.Label(frame, text=text, font=('Arial', 11, 'bold'))
        label.pack(anchor=tk.W)
        
        separator = ttk.Separator(frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=(2, 0))
    
    def browse_file(self, entry, file_type, extension):
        """Browse for a file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[(file_type, extension), ("All Files", "*.*")]
        )
        if filename:
            entry.delete(0, tk.END)
            entry.insert(0, filename)
    
    def browse_directory(self, entry):
        """Browse for a directory"""
        directory = filedialog.askdirectory()
        if directory:
            entry.delete(0, tk.END)
            entry.insert(0, directory)
    
    def test_connection(self):
        """Test connection to Sonarr"""
        import requests
        
        url = self.sonarr_url.get().strip()
        api_key = self.sonarr_api_key.get().strip()
        
        if not url or not api_key:
            self.connection_status.config(text="❌ URL and API Key required", foreground='red')
            return
        
        self.connection_status.config(text="⏳ Testing connection...", foreground='blue')
        self.root.update()
        
        try:
            headers = {"X-Api-Key": api_key}
            response = requests.get(f"{url}/api/v3/system/status", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                version = data.get('version', 'Unknown')
                self.connection_status.config(text=f"✅ Connected! Sonarr v{version}", foreground='green')
            else:
                self.connection_status.config(text=f"❌ Connection failed (Status: {response.status_code})", foreground='red')
        except requests.exceptions.ConnectionError:
            self.connection_status.config(text="❌ Cannot connect to Sonarr", foreground='red')
        except Exception as e:
            self.connection_status.config(text=f"❌ Error: {str(e)[:30]}...", foreground='red')
    
    def validate_config(self):
        """Validate configuration values"""
        errors = []
        
        # Validate Sonarr URL
        url = self.sonarr_url.get().strip()
        if not url:
            errors.append("Sonarr URL is required")
        elif not url.startswith(('http://', 'https://')):
            errors.append("Sonarr URL must start with http:// or https://")
        
        # Validate API Key
        if not self.sonarr_api_key.get().strip():
            errors.append("Sonarr API Key is required")
        
        # Validate days past
        try:
            days_past = int(self.days_past.get())
            if days_past < 0 or days_past > 365:
                errors.append("Days Past must be between 0 and 365")
        except ValueError:
            errors.append("Days Past must be a valid number")
        
        # Validate days future
        try:
            days_future = int(self.days_future.get())
            if days_future < 1 or days_future > 365:
                errors.append("Days Future must be between 1 and 365")
        except ValueError:
            errors.append("Days Future must be a valid number")
        
        # Validate file paths
        html_path = self.output_html.get().strip()
        if not html_path:
            errors.append("HTML Output File path is required")
        else:
            # Check if directory exists or can be created
            html_dir = os.path.dirname(html_path)
            if html_dir and not os.path.exists(html_dir):
                try:
                    os.makedirs(html_dir, exist_ok=True)
                except:
                    errors.append(f"Cannot create directory for HTML file: {html_dir}")
        
        # Validate cache directory
        cache_dir = self.image_cache.get().strip()
        if cache_dir and not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except:
                errors.append(f"Cannot create cache directory: {cache_dir}")
        
        # Validate refresh interval (now in hours)
        try:
            refresh_hours = int(self.refresh_interval.get())
            if refresh_hours < 1 or refresh_hours > 168:
                errors.append("Refresh Interval must be between 1 and 168 hours")
        except ValueError:
            errors.append("Refresh Interval must be a valid number")
        
        return errors
    
    def save_configuration(self):
        """Save configuration to hidden file"""
        # Validate configuration
        errors = self.validate_config()
        if errors:
            error_msg = "Please fix the following errors:\n\n• " + "\n• ".join(errors)
            messagebox.showerror("Validation Error", error_msg)
            return
        
        # Prepare configuration data
        config = {
            'sonarr_url': self.sonarr_url.get().strip(),
            'sonarr_api_key': self.sonarr_api_key.get().strip(),
            'days_past': int(self.days_past.get()),
            'days_future': int(self.days_future.get()),
            'output_html_file': self.output_html.get().strip(),
            'output_json_file': self.output_json.get().strip() or None,
            'image_cache_dir': self.image_cache.get().strip() or "sonarr_images/",
            'refresh_interval_hours': int(self.refresh_interval.get()),  # Store in hours
            'html_title': "Sonarr Calendar Pro",
            'html_theme': "dark",
            'grid_columns': 4,
            'image_quality': "poster",
            'image_size': "500",
            'enable_image_cache': True
        }
        
        try:
            # Save to hidden file
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            
            # Display summary
            self.show_config_summary(config)
            
            self.status_var.set(f"✅ Configuration saved successfully to {CONFIG_FILE.name}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save configuration:\n{str(e)}")
            self.status_var.set("❌ Failed to save configuration")
    
    def show_config_summary(self, config):
        """Display a summary of saved configuration"""
        summary = f"""✅ Configuration Saved Successfully!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SONARR SETTINGS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL:          {config['sonarr_url']}
API Key:      {'•' * 32}{config['sonarr_api_key'][-4:] if config['sonarr_api_key'] else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE RANGE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Look Back:    {config['days_past']} days
Look Forward: {config['days_future']} days

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE PATHS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HTML Output:  {config['output_html_file']}
JSON Output:  {config['output_json_file'] or 'Not enabled'}
Cache Dir:    {config['image_cache_dir']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REFRESH SETTINGS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Interval:     {config['refresh_interval_hours']} hours

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The configuration has been saved to:
{CONFIG_FILE}

You can now run the main Sonarr Calendar script:
  python sonarr_calendar.py"""
        
        messagebox.showinfo("Configuration Saved", summary)
    
    def load_configuration(self):
        """Load configuration from hidden file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                
                # Populate fields
                self.sonarr_url.delete(0, tk.END)
                self.sonarr_url.insert(0, config.get('sonarr_url', ''))
                
                self.sonarr_api_key.delete(0, tk.END)
                self.sonarr_api_key.insert(0, config.get('sonarr_api_key', ''))
                
                self.days_past.delete(0, tk.END)
                self.days_past.insert(0, config.get('days_past', 7))
                
                self.days_future.set(config.get('days_future', 30))
                
                self.output_html.delete(0, tk.END)
                self.output_html.insert(0, config.get('output_html_file', ''))
                
                self.output_json.delete(0, tk.END)
                self.output_json.insert(0, config.get('output_json_file', ''))
                
                self.image_cache.delete(0, tk.END)
                self.image_cache.insert(0, config.get('image_cache_dir', ''))
                
                # Load refresh interval in hours
                refresh_hours = config.get('refresh_interval_hours', 6)
                self.refresh_interval.set(refresh_hours)
                
                self.status_var.set(f"📂 Configuration loaded from {CONFIG_FILE.name}")
                
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load configuration:\n{str(e)}")
                self.reset_defaults()
        else:
            self.status_var.set("ℹ️ No existing configuration found. Using defaults.")
            self.reset_defaults()
    
    def reset_defaults(self):
        """Reset to default values"""
        self.sonarr_url.delete(0, tk.END)
        self.sonarr_url.insert(0, "http://localhost:8989")
        
        self.sonarr_api_key.delete(0, tk.END)
        
        self.days_past.delete(0, tk.END)
        self.days_past.insert(0, 7)
        
        self.days_future.set(30)
        
        # Set default paths based on user's home directory
        home_dir = str(Path.home())
        default_html = os.path.join(home_dir, "sonarr-calendar", "sonarr_calendar.html")
        default_json = os.path.join(home_dir, "sonarr-calendar", "sonarr_calendar_data.json")
        default_cache = os.path.join(home_dir, "sonarr-calendar", "sonarr_images")
        
        self.output_html.delete(0, tk.END)
        self.output_html.insert(0, default_html)
        
        self.output_json.delete(0, tk.END)
        self.output_json.insert(0, default_json)
        
        self.image_cache.delete(0, tk.END)
        self.image_cache.insert(0, default_cache)
        
        self.refresh_interval.set(6)  # Default 6 hours
        
        self.status_var.set("🔄 Reset to default values")

def main():
    """Main function to run the configuration GUI"""
    root = tk.Tk()
    app = SonarrConfigApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()