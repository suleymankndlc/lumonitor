#!/bin/bash

# Lumonitor Installation Script
# Installs Lumonitor system-wide or locally

set -e

INSTALL_DIR="/opt/lumonitor"
DESKTOP_FILE="/usr/share/applications/lumonitor.desktop"
LOCAL_DESKTOP="$HOME/.local/share/applications/lumonitor.desktop"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check xrandr
    if ! command -v xrandr &> /dev/null; then
        print_warning "xrandr not found. Install xorg-xrandr for full functionality"
    fi
    
    print_status "Dependencies check completed"
}

install_python_deps() {
    print_status "Installing Python dependencies..."
    
    # Try to install with pip
    if command -v pip3 &> /dev/null; then
        pip3 install --user -r "$SCRIPT_DIR/requirements.txt"
    elif command -v pip &> /dev/null; then
        pip install --user -r "$SCRIPT_DIR/requirements.txt"
    else
        print_warning "pip not found. Please install Python dependencies manually:"
        cat "$SCRIPT_DIR/requirements.txt"
    fi
}

install_system() {
    print_status "Installing system-wide..."
    
    if [[ $EUID -ne 0 ]]; then
        print_error "System-wide installation requires root privileges"
        print_status "Run: sudo $0 --system"
        exit 1
    fi
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    
    # Copy files
    cp "$SCRIPT_DIR/lumonitor.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lumonitor.py"
    
    # Create desktop file
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Lumonitor
GenericName=Brightness Control
Comment=Adjust monitor brightness with an easy-to-use interface
Icon=display-brightness-symbolic
Exec=python3 $INSTALL_DIR/lumonitor.py
Terminal=false
Categories=Settings;System;
Keywords=brightness;monitor;display;backlight;
StartupNotify=true
EOF
    
    print_status "System-wide installation completed"
    print_status "You can now run Lumonitor from your application menu"
}

install_local() {
    print_status "Installing locally for user $USER..."
    
    # Make script executable
    chmod +x "$SCRIPT_DIR/lumonitor.py"
    
    # Create local applications directory
    mkdir -p "$(dirname "$LOCAL_DESKTOP")"
    
    # Create desktop file
    cat > "$LOCAL_DESKTOP" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Lumonitor
GenericName=Brightness Control
Comment=Adjust monitor brightness with an easy-to-use interface
Icon=display-brightness-symbolic
Exec=python3 $SCRIPT_DIR/lumonitor.py
Terminal=false
Categories=Settings;System;
Keywords=brightness;monitor;display;backlight;
StartupNotify=true
EOF
    
    # Update desktop database
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$HOME/.local/share/applications"
    fi
    
    print_status "Local installation completed"
    print_status "You can now run Lumonitor from your application menu"
    print_status "Or run directly: python3 $SCRIPT_DIR/lumonitor.py"
}

uninstall() {
    print_status "Uninstalling Lumonitor..."
    
    # Remove system files (requires root)
    if [[ $EUID -eq 0 ]]; then
        rm -rf "$INSTALL_DIR"
        rm -f "$DESKTOP_FILE"
        print_status "System installation removed"
    fi
    
    # Remove local files
    rm -f "$LOCAL_DESKTOP"
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    fi
    
    print_status "Uninstallation completed"
}

show_help() {
    cat << EOF
Lumonitor Installation Script

Usage: $0 [OPTIONS]

OPTIONS:
    --system        Install system-wide (requires sudo)
    --local         Install locally for current user (default)
    --uninstall     Remove Lumonitor installation
    --help          Show this help message

EXAMPLES:
    $0                  # Install locally
    sudo $0 --system    # Install system-wide
    $0 --uninstall      # Uninstall
EOF
}

# Main script logic
case "${1:-}" in
    --system)
        check_dependencies
        install_python_deps
        install_system
        ;;
    --local)
        check_dependencies
        install_python_deps
        install_local
        ;;
    --uninstall)
        uninstall
        ;;
    --help|-h)
        show_help
        ;;
    "")
        check_dependencies
        install_python_deps
        install_local
        ;;
    *)
        print_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac