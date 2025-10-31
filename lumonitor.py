#!/usr/bin/env python3
"""
Lumonitor - Brightness Control Utility for Linux
A lightweight, desktop environment agnostic brightness controller
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')

from gi.repository import Gtk, Gdk, GLib, AppIndicator3
import subprocess
import json
import os
import re
from typing import List, Dict, Optional
import argparse


class BrightnessController:
    """Handles brightness control operations using ddcutil and xrandr fallback"""
    
    def __init__(self):
        self.use_ddcutil = self.check_ddcutil_available()
        self.monitors = self.get_monitors()
        self.brightness_cache = {}
        
    def check_ddcutil_available(self) -> bool:
        """Check if ddcutil is available and working"""
        try:
            # Try with sudo first
            result = subprocess.run(['sudo', 'ddcutil', 'detect'], 
                                  capture_output=True, text=True, check=True)
            # Check if any displays found
            if "Display 1" in result.stdout or "Display 2" in result.stdout:
                return True
            return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        
    def get_monitors(self) -> List[Dict[str, str]]:
        """Get list of available monitors"""
        if self.use_ddcutil:
            return self.get_ddcutil_monitors()
        else:
            return self.get_xrandr_monitors()
    
    def get_ddcutil_monitors(self) -> List[Dict[str, str]]:
        """Get monitors using ddcutil with sudo"""
        try:
            result = subprocess.run(['sudo', 'ddcutil', 'detect'], 
                                  capture_output=True, text=True, check=True)
            monitors = []
            
            current_display = None
            display_num = None
            for line in result.stdout.split('\n'):
                if line.startswith('Display '):
                    # Extract display number: "Display 1"
                    display_num = line.split()[1]
                    current_display = f"display-{display_num}"
                elif 'Model:' in line and current_display and display_num:
                    # Extract model name
                    model = line.split('Model:')[1].strip()
                    monitors.append({
                        'name': current_display,
                        'display_name': f"{model} (Display {display_num})",
                        'ddcutil_id': display_num
                    })
                    current_display = None
                    display_num = None
            
            return monitors
        except subprocess.CalledProcessError:
            # Fallback to xrandr if ddcutil fails
            return self.get_xrandr_monitors()
    
    def get_xrandr_monitors(self) -> List[Dict[str, str]]:
        """Get monitors using xrandr (fallback method)"""
        try:
            result = subprocess.run(['xrandr', '--listmonitors'], 
                                  capture_output=True, text=True, check=True)
            monitors = []
            
            for line in result.stdout.split('\n')[1:]:  # Skip header
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        monitor_name = parts[3]
                        monitors.append({
                            'name': monitor_name,
                            'display_name': monitor_name.replace('-', ' ').title(),
                            'ddcutil_id': None
                        })
            
            return monitors
        except subprocess.CalledProcessError:
            # Fallback to basic xrandr output parsing
            try:
                result = subprocess.run(['xrandr'], capture_output=True, text=True, check=True)
                monitors = []
                for line in result.stdout.split('\n'):
                    if ' connected' in line:
                        monitor_name = line.split()[0]
                        monitors.append({
                            'name': monitor_name,
                            'display_name': monitor_name.replace('-', ' ').title(),
                            'ddcutil_id': None
                        })
                return monitors
            except subprocess.CalledProcessError:
                return [{'name': 'default', 'display_name': 'Default Monitor', 'ddcutil_id': None}]
    
    def get_brightness(self, monitor: str) -> float:
        """Get current brightness for a monitor (0.0 to 1.0)"""
        if self.use_ddcutil:
            return self.get_ddcutil_brightness(monitor)
        else:
            return self.brightness_cache.get(monitor, 1.0)
    
    def get_ddcutil_brightness(self, monitor: str) -> float:
        """Get brightness using ddcutil with sudo"""
        try:
            # Find ddcutil_id for this monitor
            ddcutil_id = None
            for mon in self.monitors:
                if mon['name'] == monitor:
                    ddcutil_id = mon.get('ddcutil_id')
                    break
            
            if not ddcutil_id:
                return self.brightness_cache.get(monitor, 1.0)
            
            # Get brightness using VCP code 10 (brightness) with sudo
            result = subprocess.run(['sudo', 'ddcutil', '--display', ddcutil_id, 'getvcp', '10'], 
                                  capture_output=True, text=True, check=True)
            
            # Parse output: "VCP code 0x10 (Brightness): current value = 80, max value = 100"
            for line in result.stdout.split('\n'):
                if 'current value' in line:
                    parts = line.split('current value = ')[1]
                    current = int(parts.split(',')[0])
                    max_val = int(parts.split('max value = ')[1])
                    brightness = current / max_val
                    self.brightness_cache[monitor] = brightness
                    return brightness
                    
        except (subprocess.CalledProcessError, ValueError, IndexError):
            pass
        
        return self.brightness_cache.get(monitor, 1.0)
    
    def set_brightness(self, monitor: str, brightness: float):
        """Set brightness for a monitor (0.0 to 1.0)"""
        # Clamp brightness between 0.1 and 1.0
        brightness = max(0.1, min(1.0, brightness))
        
        if self.use_ddcutil:
            success = self.set_ddcutil_brightness(monitor, brightness)
            if success:
                return True
                
        # Fallback to xrandr
        return self.set_xrandr_brightness(monitor, brightness)
    
    def set_ddcutil_brightness(self, monitor: str, brightness: float) -> bool:
        """Set brightness using ddcutil with sudo"""
        try:
            # Find ddcutil_id for this monitor
            ddcutil_id = None
            for mon in self.monitors:
                if mon['name'] == monitor:
                    ddcutil_id = mon.get('ddcutil_id')
                    break
            
            if not ddcutil_id:
                return False
            
            # Convert 0.0-1.0 to 0-100 scale
            brightness_percent = int(brightness * 100)
            
            # Set brightness using VCP code 10 (brightness) with sudo
            subprocess.run(['sudo', 'ddcutil', '--display', ddcutil_id, 'setvcp', '10', str(brightness_percent)], 
                          check=True, capture_output=True)
            
            self.brightness_cache[monitor] = brightness
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"ddcutil error setting brightness: {e}")
            return False
    
    def set_xrandr_brightness(self, monitor: str, brightness: float) -> bool:
        """Set brightness using xrandr (software-only)"""
        try:
            subprocess.run(['xrandr', '--output', monitor, '--brightness', str(brightness)], 
                          check=True)
            self.brightness_cache[monitor] = brightness
            return True
        except subprocess.CalledProcessError as e:
            print(f"xrandr error setting brightness: {e}")
            return False


class LumonitorGUI:
    """Main GUI application using GTK"""
    
    def __init__(self, brightness_controller: BrightnessController):
        self.brightness_controller = brightness_controller
        self.window = None
        self.sliders = {}
        self.is_updating = False
        
        # Debounce mechanism for slider changes
        self.pending_changes = {}  # monitor_name -> brightness_value
        self.change_timers = {}    # monitor_name -> timer_id
        self.debounce_delay = 300  # milliseconds
        
        self.setup_window()
    
    def setup_window(self):
        """Create and setup the main window"""
        self.window = Gtk.Window(title="Lumonitor - Brightness Control")
        self.window.set_default_size(400, 300)
        self.window.set_border_width(15)
        self.window.connect("delete-event", self.on_window_delete)
        
        # Create main container
        vbox = Gtk.VBox(spacing=10)
        self.window.add(vbox)
        
        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<b><big>Lumonitor</big></b>")
        vbox.pack_start(title_label, False, False, 0)
        
        # Monitors section
        for monitor in self.brightness_controller.monitors:
            monitor_frame = self.create_monitor_control(monitor)
            vbox.pack_start(monitor_frame, False, False, 0)
        
        # Control buttons
        button_box = Gtk.HBox(spacing=10)
        vbox.pack_end(button_box, False, False, 0)
        
        # Reset button
        reset_btn = Gtk.Button(label="Reset All")
        reset_btn.connect("clicked", self.on_reset_clicked)
        button_box.pack_start(reset_btn, True, True, 0)
        
        # Hide button
        hide_btn = Gtk.Button(label="Hide to Tray")
        hide_btn.connect("clicked", self.on_hide_clicked)
        button_box.pack_start(hide_btn, True, True, 0)
        
        # Close button
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", self.on_close_clicked)
        button_box.pack_start(close_btn, True, True, 0)
    
    def create_monitor_control(self, monitor: Dict[str, str]):
        """Create brightness control for a single monitor"""
        frame = Gtk.Frame(label=monitor['display_name'])
        frame.set_border_width(5)
        
        vbox = Gtk.VBox(spacing=5)
        vbox.set_border_width(10)
        frame.add(vbox)
        
        # Brightness slider
        hbox = Gtk.HBox(spacing=10)
        vbox.pack_start(hbox, False, False, 0)
        
        # Label
        label = Gtk.Label(label="Brightness:")
        label.set_size_request(80, -1)
        hbox.pack_start(label, False, False, 0)
        
        # Slider
        adjustment = Gtk.Adjustment(value=100, lower=10, upper=100, 
                                  step_increment=1, page_increment=10)
        slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        slider.set_digits(0)
        slider.set_value_pos(Gtk.PositionType.RIGHT)
        slider.set_hexpand(True)
        
        # Get current brightness and set slider
        current_brightness = self.brightness_controller.get_brightness(monitor['name'])
        slider.set_value(current_brightness * 100)
        
        slider.connect("value-changed", self.on_brightness_changed, monitor['name'])
        hbox.pack_start(slider, True, True, 0)
        
        self.sliders[monitor['name']] = slider
        
        return frame
    
    def on_brightness_changed(self, slider, monitor_name):
        """Handle brightness slider change with debounce"""
        if self.is_updating:
            return
            
        brightness = slider.get_value() / 100.0
        
        # Store the pending change
        self.pending_changes[monitor_name] = brightness
        
        # Cancel previous timer for this monitor
        if monitor_name in self.change_timers:
            GLib.source_remove(self.change_timers[monitor_name])
        
        # Set new timer for debounced change
        self.change_timers[monitor_name] = GLib.timeout_add(
            self.debounce_delay, 
            self.apply_brightness_change, 
            monitor_name
        )
    
    def apply_brightness_change(self, monitor_name):
        """Apply the actual brightness change after debounce delay"""
        if monitor_name not in self.pending_changes:
            return False  # Remove timer
        
        brightness = self.pending_changes[monitor_name]
        success = self.brightness_controller.set_brightness(monitor_name, brightness)
        
        if not success:
            # Reset slider on failure
            self.is_updating = True
            old_brightness = self.brightness_controller.get_brightness(monitor_name)
            if monitor_name in self.sliders:
                self.sliders[monitor_name].set_value(old_brightness * 100)
            self.is_updating = False
        
        # Clean up
        if monitor_name in self.pending_changes:
            del self.pending_changes[monitor_name]
        if monitor_name in self.change_timers:
            del self.change_timers[monitor_name]
        
        return False  # Remove timer
    
    def on_reset_clicked(self, button):
        """Reset all monitors to 100% brightness"""
        # Cancel all pending changes
        for monitor_name in list(self.change_timers.keys()):
            GLib.source_remove(self.change_timers[monitor_name])
            del self.change_timers[monitor_name]
        self.pending_changes.clear()
        
        # Apply reset immediately
        self.is_updating = True
        for monitor in self.brightness_controller.monitors:
            self.brightness_controller.set_brightness(monitor['name'], 1.0)
            if monitor['name'] in self.sliders:
                self.sliders[monitor['name']].set_value(100)
        self.is_updating = False
    
    def on_hide_clicked(self, button):
        """Hide window to system tray"""
        self.window.hide()
    
    def on_close_clicked(self, button):
        """Close application"""
        Gtk.main_quit()
    
    def on_window_delete(self, window, event):
        """Handle window close button"""
        self.window.hide()
        return True  # Prevent window destruction
    
    def show(self):
        """Show the main window"""
        self.window.show_all()
    
    def hide(self):
        """Hide the main window"""
        self.window.hide()


class LumonitorTray:
    """System tray integration using AppIndicator"""
    
    def __init__(self, gui: LumonitorGUI, brightness_controller: BrightnessController):
        self.gui = gui
        self.brightness_controller = brightness_controller
        
        # Create indicator
        self.indicator = AppIndicator3.Indicator.new(
            "lumonitor",
            "display-brightness-symbolic",
            AppIndicator3.IndicatorCategory.HARDWARE
        )
        
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.setup_menu()
    
    def setup_menu(self):
        """Create the tray menu"""
        menu = Gtk.Menu()
        
        # Show/Hide GUI
        show_item = Gtk.MenuItem(label="Show Lumonitor")
        show_item.connect("activate", self.on_show_gui)
        menu.append(show_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quick brightness controls
        brightness_levels = [100, 75, 50, 25]
        for level in brightness_levels:
            item = Gtk.MenuItem(label=f"Set Brightness to {level}%")
            item.connect("activate", self.on_quick_brightness, level)
            menu.append(item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)
        
        menu.show_all()
        self.indicator.set_menu(menu)
    
    def on_show_gui(self, item):
        """Show the main GUI"""
        self.gui.show()
    
    def on_quick_brightness(self, item, level):
        """Set brightness to a specific level for all monitors"""
        brightness = level / 100.0
        for monitor in self.brightness_controller.monitors:
            self.brightness_controller.set_brightness(monitor['name'], brightness)
    
    def on_quit(self, item):
        """Quit the application"""
        Gtk.main_quit()


class Lumonitor:
    """Main application class"""
    
    def __init__(self, show_tray=True):
        self.brightness_controller = BrightnessController()
        self.gui = LumonitorGUI(self.brightness_controller)
        
        if show_tray:
            self.tray = LumonitorTray(self.gui, self.brightness_controller)
        else:
            self.tray = None
    
    def run(self):
        """Run the application"""
        self.gui.show()
        
        # Setup CSS for better looks
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #f6f5f4;
            }
            frame {
                background-color: white;
                border-radius: 6px;
                border: 1px solid #d1d5db;
            }
            scale {
                min-width: 200px;
            }
        """)
        
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        try:
            Gtk.main()
        except KeyboardInterrupt:
            print("\nExiting...")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Lumonitor - Brightness Control Utility")
    parser.add_argument("--no-tray", action="store_true", 
                       help="Disable system tray integration")
    parser.add_argument("--brightness", type=float, metavar="LEVEL",
                       help="Set brightness level (0.1 to 1.0) and exit")
    parser.add_argument("--brightness-step", type=str, metavar="STEP",
                       help="Adjust brightness by step (+0.1, -0.1) and exit")
    parser.add_argument("--monitor", type=str, metavar="NAME",
                       help="Specify monitor name (use with --brightness)")
    
    args = parser.parse_args()
    
    # Command line brightness setting
    if args.brightness is not None or args.brightness_step is not None:
        controller = BrightnessController()
        monitors = [args.monitor] if args.monitor else [m['name'] for m in controller.monitors]
        
        for monitor in monitors:
            if args.brightness is not None:
                # Set absolute brightness
                success = controller.set_brightness(monitor, args.brightness)
                if success:
                    print(f"Set brightness for {monitor} to {args.brightness * 100:.0f}%")
                else:
                    print(f"Failed to set brightness for {monitor}")
            
            elif args.brightness_step is not None:
                # Adjust brightness by step
                try:
                    step = float(args.brightness_step)
                    current = controller.get_brightness(monitor)
                    new_brightness = max(0.1, min(1.0, current + step))
                    success = controller.set_brightness(monitor, new_brightness)
                    if success:
                        print(f"Adjusted brightness for {monitor} to {new_brightness * 100:.0f}%")
                    else:
                        print(f"Failed to adjust brightness for {monitor}")
                except ValueError:
                    print(f"Invalid brightness step: {args.brightness_step}")
        return
    
    # GUI mode
    app = Lumonitor(show_tray=not args.no_tray)
    app.run()


if __name__ == "__main__":
    main()