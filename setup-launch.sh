#!/bin/bash
# ═══════════════════════════════════════════════════════════
# IT Aman — One-Click Launch Setup
# Run this ONCE on each device to create desktop shortcut
# so users can open the tool without typing commands.
# ═══════════════════════════════════════════════════════════

set -e

echo "========================================"
echo " IT Aman — One-Click Launch Setup"
echo "========================================"

# Must be root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Run this script as root (sudo)"
    exit 1
fi

INSTALL_DIR="/opt/it-aman"
POLICY_FILE="/usr/share/polkit-1/actions/com.it-aman.gui.policy"
DESKTOP_FILE="/usr/share/applications/it-aman.desktop"
LOCAL_DESKTOP="/root/Desktop/it-aman.desktop"
SUDOERS_FILE="/etc/sudoers.d/it-aman-gui"

# 1. Install Polkit policy (allows pkexec to run GUI without password)
echo "[1/4] Installing Polkit policy..."
mkdir -p /usr/share/polkit-1/actions/
if [ -f "$INSTALL_DIR/com.it-aman.gui.policy" ]; then
    cp "$INSTALL_DIR/com.it-aman.gui.policy" "$POLICY_FILE"
    echo "  ✓ Polkit policy installed"
else
    # Download from GitHub if not local
    curl -sL "https://raw.githubusercontent.com/abubakrahmed1911-hue/Printers-Tools/main/com.it-aman.gui.policy" \
        -o "$POLICY_FILE" 2>/dev/null || true
    if [ -f "$POLICY_FILE" ]; then
        echo "  ✓ Polkit policy downloaded from GitHub"
    else
        echo "  ⚠ Could not install Polkit policy (will use sudoers fallback)"
    fi
fi

# 2. Install desktop shortcut
echo "[2/4] Installing desktop shortcut..."
mkdir -p /usr/share/applications/

# Use pkexec if polkit is available, otherwise use sudo
if [ -f "$POLICY_FILE" ]; then
    EXEC_CMD="pkexec /usr/bin/python3 $INSTALL_DIR/src/gui.py"
else
    EXEC_CMD="sudo /usr/bin/python3 $INSTALL_DIR/src/gui.py"
fi

cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Name=IT Aman Printer Tool
Name[ar]=أداة إدارة الطابعات
Comment=Printer management and diagnostic tool
Comment[ar]=أداة إدارة وتشخيص الطابعات
Exec=$EXEC_CMD
Icon=printer
Terminal=false
Type=Application
Categories=System;Settings;HardwareSettings;
Keywords=printer;CUPS;driver;thermal;network;
StartupNotify=true
DESKTOP_EOF

echo "  ✓ Desktop shortcut installed to $DESKTOP_FILE"

# 3. Copy to all user desktops
echo "[3/4] Copying shortcut to user desktops..."
for user_home in /home/*; do
    if [ -d "$user_home/Desktop" ] || [ -d "$user_home/سطح المكتب" ]; then
        # Find the actual Desktop directory
        DESK_DIR="$user_home/Desktop"
        [ -d "$user_home/سطح المكتب" ] && DESK_DIR="$user_home/سطح المكتب"

        cp "$DESKTOP_FILE" "$DESK_DIR/it-aman.desktop"
        # Get the user who owns this home dir
        USERNAME=$(basename "$user_home")
        chown "$USERNAME:$USERNAME" "$DESK_DIR/it-aman.desktop" 2>/dev/null || true
        chmod +x "$DESK_DIR/it-aman.desktop" 2>/dev/null || true
        echo "  ✓ Shortcut copied to $DESK_DIR"
    fi
done

# Also add to root desktop if it exists
if [ -d "/root/Desktop" ]; then
    cp "$DESKTOP_FILE" "/root/Desktop/it-aman.desktop"
    chmod +x "/root/Desktop/it-aman.desktop" 2>/dev/null || true
    echo "  ✓ Shortcut copied to /root/Desktop"
fi

# 4. Add sudoers entry (allows sudo without password for gui.py)
echo "[4/4] Setting up passwordless sudo for GUI..."
echo "%users ALL=(root) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/src/gui.py" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
echo "  ✓ Sudoers rule installed — no password needed for GUI"

# Update desktop database
update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  Now you can open IT Aman by:"
echo "  • Double-clicking the desktop shortcut"
echo "  • Finding it in Applications menu"
echo "  • Running: pkexec python3 $INSTALL_DIR/src/gui.py"
echo ""
echo "  No need to type sudo commands anymore!"
echo "═══════════════════════════════════════"
