#!/usr/bin/env python3
"""
Lumonitor Hotkey Service
Global keyboard shortcuts for brightness control
"""

from pynput import keyboard
import subprocess
import json
import os
import sys
from typing import Dict, Callable


class HotkeyManager:
    """Manages global keyboard shortcuts for brightness control"""
    
    def __init__(self, brightness_controller):
        self.brightness_controller = brightness_controller
        self.listener = None
        self.hotkeys = {
            # Default hotkeys
            '<ctrl>+<alt>+<up>': self.increase_brightness,
            '<ctrl>+<alt>+<down>': self.decrease_brightness,
            '<ctrl>+<alt>+<shift>+r': self.reset_brightness,
        }
        self.step_size = 0.1  # 10% steps
        
    def increase_brightness(self):
        """Increase brightness for all monitors"""
        for monitor in self.brightness_controller.monitors:
            current = self.brightness_controller.get_brightness(monitor['name'])
            new_brightness = min(1.0, current + self.step_size)
            self.brightness_controller.set_brightness(monitor['name'], new_brightness)
            print(f"Brightness: {new_brightness * 100:.0f}%")
    
    def decrease_brightness(self):
        """Decrease brightness for all monitors"""
        for monitor in self.brightness_controller.monitors:
            current = self.brightness_controller.get_brightness(monitor['name'])
            new_brightness = max(0.1, current - self.step_size)
            self.brightness_controller.set_brightness(monitor['name'], new_brightness)
            print(f"Brightness: {new_brightness * 100:.0f}%")
    
    def reset_brightness(self):
        """Reset brightness to 100% for all monitors"""
        for monitor in self.brightness_controller.monitors:
            self.brightness_controller.set_brightness(monitor['name'], 1.0)
        print("Brightness reset to 100%")
    
    def on_hotkey_pressed(self, hotkey_func):
        """Handle hotkey press"""
        try:
            hotkey_func()
        except Exception as e:
            print(f"Error executing hotkey: {e}")
    
    def start_listening(self):
        """Start listening for hotkeys"""
        if self.listener is not None:
            return
            
        print("Starting hotkey service...")
        print("Hotkeys:")
        print("  Ctrl+Alt+↑     : Increase brightness")
        print("  Ctrl+Alt+↓     : Decrease brightness") 
        print("  Ctrl+Alt+Shift+R : Reset to 100%")
        
        # Create hotkey combinations
        hotkey_combinations = []
        for hotkey_str, func in self.hotkeys.items():
            try:
                # Parse hotkey string to pynput format
                combo = self.parse_hotkey(hotkey_str)
                hotkey_combinations.append((combo, lambda f=func: self.on_hotkey_pressed(f)))
            except Exception as e:
                print(f"Error parsing hotkey {hotkey_str}: {e}")
        
        # Start global hotkey listener
        try:
            with keyboard.GlobalHotKeys({
                '<ctrl>+<alt>+<up>': self.increase_brightness,
                '<ctrl>+<alt>+<down>': self.decrease_brightness,
                '<ctrl>+<alt>+<shift>+r': self.reset_brightness,
            }) as self.listener:
                self.listener.join()
        except Exception as e:
            print(f"Error starting hotkey listener: {e}")
    
    def parse_hotkey(self, hotkey_str: str):
        """Parse hotkey string to pynput format"""
        # This is a simplified parser - pynput handles the format directly
        return hotkey_str
    
    def stop_listening(self):
        """Stop listening for hotkeys"""
        if self.listener is not None:
            self.listener.stop()
            self.listener = None


def main():
    """Run hotkey service standalone"""
    import sys
    sys.path.append(os.path.dirname(__file__))
    
    try:
        from lumonitor import BrightnessController
        
        brightness_controller = BrightnessController()
        hotkey_manager = HotkeyManager(brightness_controller)
        
        print("Lumonitor Hotkey Service")
        print("Press Ctrl+C to exit")
        
        try:
            hotkey_manager.start_listening()
        except KeyboardInterrupt:
            print("\nExiting hotkey service...")
            hotkey_manager.stop_listening()
            
    except ImportError as e:
        print(f"Error importing brightness controller: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()