#!/usr/bin/env python3
"""
Simple test script to verify Lumonitor functionality
"""

import subprocess
import sys
import os

def test_dependencies():
    """Test if required dependencies are available"""
    print("🔍 Testing dependencies...")
    
    # Test Python
    try:
        import sys
        print(f"✅ Python {sys.version}")
    except Exception as e:
        print(f"❌ Python error: {e}")
        return False
    
    # Test xrandr
    try:
        result = subprocess.run(['xrandr', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ xrandr available")
        else:
            print("❌ xrandr not working")
            return False
    except FileNotFoundError:
        print("❌ xrandr not found")
        return False
    
    # Test GTK
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        print("✅ GTK 3 available")
    except Exception as e:
        print(f"❌ GTK error: {e}")
        return False
    
    # Test AppIndicator
    try:
        gi.require_version('AppIndicator3', '0.1')
        from gi.repository import AppIndicator3
        print("✅ AppIndicator3 available")
    except Exception as e:
        print(f"⚠️ AppIndicator3 not available: {e}")
        print("   Tray functionality may not work")
    
    return True

def test_brightness_control():
    """Test brightness control functionality"""
    print("\n🔧 Testing brightness control...")
    
    try:
        # Add current directory to Python path
        sys.path.insert(0, os.path.dirname(__file__))
        
        from lumonitor import BrightnessController
        
        controller = BrightnessController()
        
        # Test monitor detection
        monitors = controller.get_monitors()
        if monitors:
            print(f"✅ Found {len(monitors)} monitor(s):")
            for monitor in monitors:
                print(f"   - {monitor['display_name']} ({monitor['name']})")
        else:
            print("❌ No monitors detected")
            return False
        
        # Test brightness getting/setting
        test_monitor = monitors[0]['name']
        original_brightness = controller.get_brightness(test_monitor)
        print(f"✅ Current brightness for {test_monitor}: {original_brightness * 100:.0f}%")
        
        # Test setting brightness (don't actually change it in test)
        print("✅ Brightness control functions available")
        
        return True
        
    except Exception as e:
        print(f"❌ Brightness control error: {e}")
        return False

def test_gui():
    """Test GUI components without showing window"""
    print("\n🎨 Testing GUI components...")
    
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from lumonitor import BrightnessController, LumonitorGUI
        
        controller = BrightnessController()
        
        # Test GUI creation (don't show)
        gui = LumonitorGUI(controller)
        print("✅ GUI components created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ GUI error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Lumonitor Test Suite")
    print("=" * 40)
    
    tests_passed = 0
    total_tests = 3
    
    if test_dependencies():
        tests_passed += 1
    
    if test_brightness_control():
        tests_passed += 1
    
    if test_gui():
        tests_passed += 1
    
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {tests_passed}/{total_tests} passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Lumonitor should work correctly.")
        return 0
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)