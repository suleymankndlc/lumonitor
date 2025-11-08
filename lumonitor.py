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
from pathlib import Path
import threading
from queue import Queue
import time


class BrightnessController:
    """Handles brightness control operations using ddcutil and xrandr fallback"""
    
    def __init__(self):
        self.use_ddcutil = self.check_ddcutil_available()
        self.monitors = self.get_monitors()
        self.brightness_cache = {}
        self.cache_dir = Path.home() / '.cache' / 'lumonitor'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe queue for brightness changes
        self.pending_changes = {}  # monitor -> (brightness, timestamp)
        self.change_lock = threading.Lock()
        self.worker_thread = None
        self.running = True
        
        # Start background worker
        self._start_worker()
        
    def _start_worker(self):
        """Start background worker thread for applying brightness changes"""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def _worker_loop(self):
        """Background worker that applies brightness changes"""
        while self.running:
            time.sleep(0.05)  # Check every 50ms
            
            with self.change_lock:
                if not self.pending_changes:
                    continue
                    
                # Process all pending changes
                to_apply = dict(self.pending_changes)
                self.pending_changes.clear()
            
            # Apply changes outside the lock (can be slow)
            for monitor, (brightness, _) in to_apply.items():
                self._apply_brightness_hardware(monitor, brightness)
        
    def _get_cache_file(self, monitor: str) -> Path:
        """Get cache file path for a monitor"""
        # Sanitize monitor name for filename
        safe_name = monitor.replace('/', '_').replace(' ', '_')
        return self.cache_dir / f'brightness_{safe_name}'
    
    def _read_cached_brightness(self, monitor: str) -> Optional[float]:
        """Read brightness from cache file"""
        cache_file = self._get_cache_file(monitor)
        try:
            if cache_file.exists():
                value = float(cache_file.read_text().strip())
                return max(0.0, min(1.0, value))
        except (ValueError, IOError):
            pass
        return None
    
    def _write_cached_brightness(self, monitor: str, brightness: float):
        """Write brightness to cache file"""
        cache_file = self._get_cache_file(monitor)
        try:
            cache_file.write_text(f"{brightness:.2f}\n")
        except IOError:
            pass
        
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
        # İlk önce cache'i kontrol et
        cached = self._read_cached_brightness(monitor)
        if cached is not None:
            return cached
        
        # Cache yoksa ddcutil veya xrandr'dan oku
        if self.use_ddcutil:
            brightness = self.get_ddcutil_brightness(monitor)
        else:
            brightness = self.brightness_cache.get(monitor, 1.0)
        
        # Cache'e yaz
        self._write_cached_brightness(monitor, brightness)
        return brightness
    
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
        """Set brightness for a monitor (0.0 to 1.0) - immediate cache update, async hardware"""
        # Clamp brightness between 0.1 and 1.0
        brightness = max(0.1, min(1.0, brightness))
        
        # İlk önce cache'e yaz (anında UI response)
        self._write_cached_brightness(monitor, brightness)
        
        # Memory cache'i de güncelle
        self.brightness_cache[monitor] = brightness
        
        # Hardware değişikliğini queue'ya ekle (async)
        with self.change_lock:
            self.pending_changes[monitor] = (brightness, time.time())
        
        return True
    
    def _apply_brightness_hardware(self, monitor: str, brightness: float):
        """Actually apply brightness to hardware (called from worker thread)"""
        if self.use_ddcutil:
            self.set_ddcutil_brightness(monitor, brightness)
        else:
            self.set_xrandr_brightness(monitor, brightness)
    
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
            
            # Başarılı olursa memory cache'i de güncelle
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
            # Memory cache'i güncelle
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
        self.debounce_delay = 500  # milliseconds - increased for smoother feel
        
        self.setup_window()
    
    def setup_window(self):
        """Create and setup the main window"""
        self.window = Gtk.Window(title="Lumonitor")
        self.window.set_default_size(520, 380)
        self.window.set_border_width(0)
        self.window.connect("delete-event", self.on_window_delete)
        
        # Modern window styling
        self.window.set_resizable(False)
        
        # Modern window styling
        self.window.set_resizable(False)
        
        # Main container with padding
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.add(main_box)
        
        # Header section
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header.set_name("header")
        main_box.pack_start(header, False, False, 0)
        
        # Title with icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box.set_margin_start(24)
        title_box.set_margin_end(24)
        title_box.set_margin_top(24)
        title_box.set_margin_bottom(16)
        
        icon = Gtk.Image.new_from_icon_name("display-brightness-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        icon.set_pixel_size(24)
        title_box.pack_start(icon, False, False, 0)
        
        title_label = Gtk.Label()
        title_label.set_markup("<span size='14000' weight='600'>Lumonitor</span>")
        title_label.set_halign(Gtk.Align.START)
        title_box.pack_start(title_label, True, True, 0)
        
        header.pack_start(title_box, False, False, 0)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_name("header-separator")
        header.pack_start(separator, False, False, 0)
        
        # Content area
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        main_box.pack_start(content, True, True, 0)
        
        content.set_margin_bottom(24)
        main_box.pack_start(content, True, True, 0)
        
        # Monitors section
        for monitor in self.brightness_controller.monitors:
            monitor_frame = self.create_monitor_control(monitor)
            content.pack_start(monitor_frame, False, False, 0)
        
        # Footer with buttons
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_start(24)
        footer.set_margin_end(24)
        footer.set_margin_bottom(24)
        footer.set_margin_top(8)
        main_box.pack_end(footer, False, False, 0)
        
        # Reset button (secondary style)
        reset_btn = Gtk.Button(label="🔄  Reset")
        reset_btn.set_name("secondary-button")
        reset_btn.connect("clicked", self.on_reset_clicked)
        footer.pack_start(reset_btn, False, False, 0)
        
        # Spacer
        footer.pack_start(Gtk.Box(), True, True, 0)
        
        # Hide button (secondary style)
        hide_btn = Gtk.Button(label="📥  Hide to Tray")
        hide_btn.set_name("secondary-button")
        hide_btn.connect("clicked", self.on_hide_clicked)
        footer.pack_start(hide_btn, False, False, 0)
        
        # Close button (ghost style)
        close_btn = Gtk.Button(label="Close")
        close_btn.set_name("ghost-button")
        close_btn.connect("clicked", self.on_close_clicked)
        footer.pack_start(close_btn, False, False, 0)
    
    def create_monitor_control(self, monitor: Dict[str, str]):
        """Create brightness control for a single monitor"""
        # Card container
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_name("card")
        
        # Monitor name/label
        name_label = Gtk.Label(label=monitor['display_name'])
        name_label.set_name("monitor-label")
        name_label.set_halign(Gtk.Align.START)
        card.pack_start(name_label, False, False, 0)
        
        # Slider container
        slider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.pack_start(slider_box, False, False, 0)
        
        # Brightness icon
        icon = Gtk.Image.new_from_icon_name("display-brightness-symbolic", Gtk.IconSize.BUTTON)
        icon.set_opacity(0.6)
        slider_box.pack_start(icon, False, False, 0)
        
        # Slider
        adjustment = Gtk.Adjustment(value=100, lower=10, upper=100, 
                                  step_increment=1, page_increment=10)
        slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        slider.set_name("brightness-slider")
        slider.set_digits(0)
        slider.set_value_pos(Gtk.PositionType.RIGHT)
        slider.set_draw_value(True)
        slider.set_hexpand(True)
        
        # Get current brightness and set slider
        current_brightness = self.brightness_controller.get_brightness(monitor['name'])
        slider.set_value(current_brightness * 100)
        
        slider.connect("value-changed", self.on_brightness_changed, monitor['name'])
        slider_box.pack_start(slider, True, True, 0)
        
        self.sliders[monitor['name']] = slider
        
        return card
    
    def on_brightness_changed(self, slider, monitor_name):
        """Handle brightness slider change with debounce"""
        if self.is_updating:
            return
        
        # Update UI immediately for smooth feel
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
        show_item = Gtk.MenuItem(label="🎛  Open Lumonitor")
        show_item.connect("activate", self.on_show_gui)
        menu.append(show_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quick brightness controls with emojis
        brightness_levels = [
            (100, "☀️  100%"),
            (75, "🔆  75%"),
            (50, "🔅  50%"),
            (25, "🌙  25%")
        ]
        for level, label in brightness_levels:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", self.on_quick_brightness, level)
            menu.append(item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="❌  Quit Lumonitor")
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
    
    def __init__(self, show_tray=True, start_minimized=False):
        self.brightness_controller = BrightnessController()
        self.gui = LumonitorGUI(self.brightness_controller)
        self.start_minimized = start_minimized
        
        if show_tray:
            self.tray = LumonitorTray(self.gui, self.brightness_controller)
        else:
            self.tray = None
    
    def run(self):
        """Run the application"""
        if not self.start_minimized:
            self.gui.show()
        
        # Modern shadcn-inspired CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            /* Modern color palette - shadcn inspired */
            window {
                background-color: #fafafa;
            }
            
            #header {
                background: linear-gradient(to bottom, #ffffff 0%, #fafafa 100%);
            }
            
            #header-separator {
                background-color: #e5e5e5;
                min-height: 1px;
            }
            
            /* Card styling - subtle shadow, rounded corners */
            #card {
                background-color: #ffffff;
                border-radius: 12px;
                padding: 20px;
                border: 1px solid #e5e5e5;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
            }
            
            #card:hover {
                border-color: #d4d4d4;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
                transition: all 150ms ease;
            }
            
            /* Monitor label */
            #monitor-label {
                color: #18181b;
                font-weight: 600;
                font-size: 14px;
            }
            
            /* Slider styling - modern accent */
            #brightness-slider slider {
                background-color: #18181b;
                border-radius: 8px;
                min-width: 18px;
                min-height: 18px;
                margin: -7px;
                transition: all 100ms ease;
            }
            
            #brightness-slider slider:hover {
                background-color: #3b82f6;
                min-width: 20px;
                min-height: 20px;
            }
            
            #brightness-slider trough {
                background-color: #e5e5e5;
                border-radius: 8px;
                min-height: 4px;
            }
            
            #brightness-slider highlight {
                background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
                border-radius: 8px;
                transition: all 100ms ease;
            }
            
            #brightness-slider value {
                color: #71717a;
                font-size: 13px;
                font-weight: 500;
            }
            
            /* Button styles - shadcn inspired */
            button {
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
                font-size: 14px;
                min-height: 36px;
                transition: all 150ms ease;
            }
            
            #secondary-button {
                background: #f4f4f5;
                color: #18181b;
                border: 1px solid #e4e4e7;
            }
            
            #secondary-button:hover {
                background: #e4e4e7;
                border-color: #d4d4d8;
            }
            
            #secondary-button:active {
                background: #d4d4d8;
            }
            
            #ghost-button {
                background: transparent;
                color: #71717a;
                border: none;
            }
            
            #ghost-button:hover {
                background: #f4f4f5;
                color: #18181b;
            }
            
            #ghost-button:active {
                background: #e4e4e7;
            }
            
            /* Dialog specific styles */
            #dialog-header {
                background: linear-gradient(to bottom, #ffffff 0%, #fafafa 100%);
            }
            
            #dialog-separator {
                background-color: #e5e5e5;
                min-height: 1px;
            }
            
            #shortcut-label {
                color: #18181b;
                font-weight: 500;
                font-size: 13px;
            }
            
            #shortcut-entry {
                border-radius: 8px;
                border: 1px solid #e4e4e7;
                padding: 8px 12px;
                background-color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            
            #shortcut-entry:focus {
                border-color: #3b82f6;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
            }
            
            /* Primary button - accent */
            #primary-button {
                background: linear-gradient(to bottom, #3b82f6 0%, #2563eb 100%);
                color: #ffffff;
                border: none;
                font-weight: 600;
            }
            
            #primary-button:hover {
                background: linear-gradient(to bottom, #2563eb 0%, #1d4ed8 100%);
            }
            
            #primary-button:active {
                background: #1d4ed8;
            }
            
            /* Destructive button - red */
            #destructive-button {
                background: transparent;
                color: #dc2626;
                border: 1px solid #fca5a5;
            }
            
            #destructive-button:hover {
                background: #fef2f2;
                border-color: #f87171;
            }
            
            #destructive-button:active {
                background: #fee2e2;
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
    parser.add_argument("--minimized", action="store_true",
                       help="Start minimized to system tray")
    
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
    app = Lumonitor(show_tray=not args.no_tray, start_minimized=args.minimized)
    app.run()


if __name__ == "__main__":
    main()