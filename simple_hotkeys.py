#!/usr/bin/env python3
"""
Lumonitor Simple Hotkey Service
Uses system keyboard shortcuts without complex dependencies
"""

import subprocess
import time
import os
import sys
import signal
import threading
from pathlib import Path


class SimpleHotkeyService:
    """Simple hotkey service using system tools"""
    
    def __init__(self):
        self.running = False
        self.step_size = 0.1
        self.lumonitor_path = Path(__file__).parent / "lumonitor.py"
        
    def increase_brightness(self):
        """Increase brightness using lumonitor CLI"""
        try:
            result = subprocess.run([
                sys.executable, str(self.lumonitor_path), 
                '--brightness', str(min(1.0, 0.1 + self.step_size))
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print("🔆 Brightness increased")
            else:
                print(f"❌ Error: {result.stderr}")
        except Exception as e:
            print(f"Error increasing brightness: {e}")
    
    def decrease_brightness(self):
        """Decrease brightness using lumonitor CLI"""
        try:
            result = subprocess.run([
                sys.executable, str(self.lumonitor_path), 
                '--brightness', str(max(0.1, 1.0 - self.step_size))
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print("🔅 Brightness decreased")
            else:
                print(f"❌ Error: {result.stderr}")
        except Exception as e:
            print(f"Error decreasing brightness: {e}")
    
    def reset_brightness(self):
        """Reset brightness to 100%"""
        try:
            result = subprocess.run([
                sys.executable, str(self.lumonitor_path), 
                '--brightness', '1.0'
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print("🔆 Brightness reset to 100%")
            else:
                print(f"❌ Error: {result.stderr}")
        except Exception as e:
            print(f"Error resetting brightness: {e}")
    
    def setup_gnome_shortcuts(self):
        """Setup GNOME keyboard shortcuts"""
        shortcuts = [
            {
                'name': 'lumonitor-increase',
                'command': f'python3 {self.lumonitor_path} --brightness-step +0.1',
                'binding': '<Super><Shift>Up'
            },
            {
                'name': 'lumonitor-decrease', 
                'command': f'python3 {self.lumonitor_path} --brightness-step -0.1',
                'binding': '<Super><Shift>Down'
            },
            {
                'name': 'lumonitor-reset',
                'command': f'python3 {self.lumonitor_path} --brightness 1.0',
                'binding': '<Super><Shift>r'
            }
        ]
        
        print("Setting up GNOME keyboard shortcuts...")
        for i, shortcut in enumerate(shortcuts):
            try:
                # Set command
                subprocess.run([
                    'gsettings', 'set', 
                    f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lumonitor{i}/',
                    'command', shortcut['command']
                ], check=True)
                
                # Set name
                subprocess.run([
                    'gsettings', 'set',
                    f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lumonitor{i}/',
                    'name', shortcut['name']
                ], check=True)
                
                # Set binding
                subprocess.run([
                    'gsettings', 'set',
                    f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lumonitor{i}/',
                    'binding', shortcut['binding']
                ], check=True)
                
                print(f"✅ {shortcut['name']}: {shortcut['binding']}")
                
            except subprocess.CalledProcessError as e:
                print(f"❌ Error setting up {shortcut['name']}: {e}")
        
        # Register the custom keybindings
        try:
            current_bindings = subprocess.run([
                'gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'
            ], capture_output=True, text=True, check=True).stdout.strip()
            
            # Parse current bindings
            if current_bindings == "@as []":
                new_bindings = []
            else:
                # Remove brackets and quotes, split by comma
                current_bindings = current_bindings.strip("[]'\"")
                new_bindings = [b.strip().strip("'\"") for b in current_bindings.split(",") if b.strip()]
            
            # Add our bindings
            for i in range(len(shortcuts)):
                binding_path = f'/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lumonitor{i}/'
                if binding_path not in new_bindings:
                    new_bindings.append(binding_path)
            
            # Set new bindings list
            bindings_str = "[" + ", ".join(f"'{b}'" for b in new_bindings) + "]"
            subprocess.run([
                'gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 
                'custom-keybindings', bindings_str
            ], check=True)
            
            print("✅ GNOME keyboard shortcuts registered")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Error registering shortcuts: {e}")
    
    def remove_gnome_shortcuts(self):
        """Remove GNOME keyboard shortcuts"""
        print("Removing GNOME keyboard shortcuts...")
        try:
            current_bindings = subprocess.run([
                'gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'
            ], capture_output=True, text=True, check=True).stdout.strip()
            
            if current_bindings != "@as []":
                current_bindings = current_bindings.strip("[]'\"")
                new_bindings = []
                for binding in current_bindings.split(","):
                    binding = binding.strip().strip("'\"")
                    if not binding.endswith('lumonitor0/') and not binding.endswith('lumonitor1/') and not binding.endswith('lumonitor2/'):
                        new_bindings.append(binding)
                
                bindings_str = "[" + ", ".join(f"'{b}'" for b in new_bindings if b) + "]"
                subprocess.run([
                    'gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 
                    'custom-keybindings', bindings_str
                ], check=True)
                
                print("✅ GNOME shortcuts removed")
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Error removing shortcuts: {e}")


def main():
    service = SimpleHotkeyService()
    
    import argparse
    parser = argparse.ArgumentParser(description="Lumonitor Hotkey Service")
    parser.add_argument('--setup', action='store_true', help='Setup keyboard shortcuts')
    parser.add_argument('--remove', action='store_true', help='Remove keyboard shortcuts')
    parser.add_argument('--test-increase', action='store_true', help='Test brightness increase')
    parser.add_argument('--test-decrease', action='store_true', help='Test brightness decrease')
    parser.add_argument('--test-reset', action='store_true', help='Test brightness reset')
    
    args = parser.parse_args()
    
    if args.setup:
        service.setup_gnome_shortcuts()
        print("\nKeyboard shortcuts setup complete!")
        print("Shortcuts:")
        print("  Super+Shift+↑  : Increase brightness")
        print("  Super+Shift+↓  : Decrease brightness")
        print("  Super+Shift+R  : Reset brightness to 100%")
    elif args.remove:
        service.remove_gnome_shortcuts()
    elif args.test_increase:
        service.increase_brightness()
    elif args.test_decrease:
        service.decrease_brightness()
    elif args.test_reset:
        service.reset_brightness()
    else:
        print("Lumonitor Simple Hotkey Service")
        print("Usage:")
        print("  --setup        Setup GNOME keyboard shortcuts")
        print("  --remove       Remove keyboard shortcuts")
        print("  --test-*       Test brightness controls")


if __name__ == "__main__":
    main()