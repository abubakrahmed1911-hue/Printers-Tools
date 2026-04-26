#!/bin/bash
# ═══════════════════════════════════════════════════════════
# IT Aman Printer Tool v3.12 — Installation Script
# ═══════════════════════════════════════════════════════════

set -e

REPO="abubakrahmed1911-hue/Printers-Tools"
BRANCH="main"
INSTALL_DIR="/opt/it-aman"
CONFIG_DIR="/etc/it-aman"
LOG_DIR="/var/log/it-aman"
SOCKET_DIR="/run/it-aman"
SERVICE_FILE="/etc/systemd/system/it-aman.service"
DESKTOP_FILE="/usr/share/applications/it-aman.desktop"
POLICY_FILE="/usr/share/polkit-1/actions/com.it-aman.gui.policy"
SUDOERS_FILE="/etc/sudoers.d/it-aman-gui"

echo "========================================"
echo " IT Aman Printer Tool v3.12 Installer"
echo "========================================"
echo ""

# ── Must be root ──
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Run this script as root (sudo)"
    exit 1
fi

# ── 1. Install dependencies ──
echo "[1/10] Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    cups cups-bsd avahi-daemon avahi-utils \
    curl wget policykit-1 2>/dev/null || true

# ── 2. Stop old service if running ──
echo "[2/10] Stopping old service (if any)..."
systemctl stop it-aman.service 2>/dev/null || true
systemctl disable it-aman.service 2>/dev/null || true

# ── 3. Download files from GitHub ──
echo "[3/10] Downloading IT Aman files..."
mkdir -p "$INSTALL_DIR/src"

BASE_URL="https://raw.githubusercontent.com/$REPO/$BRANCH"

curl -sL "$BASE_URL/src/daemon.py" -o "$INSTALL_DIR/src/daemon.py"
curl -sL "$BASE_URL/src/gui.py" -o "$INSTALL_DIR/src/gui.py"
curl -sL "$BASE_URL/version.json" -o "$INSTALL_DIR/version.json"
curl -sL "$BASE_URL/public.pem" -o "$INSTALL_DIR/public.pem"
curl -sL "$BASE_URL/printer_definitions.json" -o "$INSTALL_DIR/printer_definitions.json"
curl -sL "$BASE_URL/.gitignore" -o "$INSTALL_DIR/.gitignore"
curl -sL "$BASE_URL/CHANGELOG.md" -o "$INSTALL_DIR/CHANGELOG.md"

# Make daemon executable
chmod +x "$INSTALL_DIR/src/daemon.py"
chmod +x "$INSTALL_DIR/src/gui.py"

echo "  Downloaded to $INSTALL_DIR"

# ── 4. Create directories ──
echo "[4/10] Creating directories..."
mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$SOCKET_DIR"

# ── 5. Sync centralized printer definitions ──
echo "[5/10] Syncing centralized printer definitions..."
if [ -f "$INSTALL_DIR/printer_definitions.json" ]; then
    cp "$INSTALL_DIR/printer_definitions.json" "$CONFIG_DIR/printer_definitions.json"
    echo "  ✓ Printer definitions synced to $CONFIG_DIR"
else
    echo "  ⚠ printer_definitions.json not found — skipping"
fi

# ── 6. Create systemd service ──
echo "[6/10] Installing systemd service..."
cat > "$SERVICE_FILE" << 'SERVICE_EOF'
[Unit]
Description=IT Aman Printer Daemon
After=network.target cups.service
Requires=cups.service

[Service]
Type=forking
PIDFile=/run/it-aman/it-aman.pid
ExecStart=/usr/bin/python3 /opt/it-aman/src/daemon.py
ExecStop=/bin/kill -TERM $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# ── 7. Install Polkit policy (allows GUI without password) ──
echo "[7/10] Installing Polkit policy..."
mkdir -p /usr/share/polkit-1/actions/
curl -sL "$BASE_URL/com.it-aman.gui.policy" -o "$POLICY_FILE" 2>/dev/null || true
if [ -f "$POLICY_FILE" ]; then
    echo "  ✓ Polkit policy installed (no password needed for GUI)"
else
    echo "  ⚠ Polkit policy not downloaded — will use sudoers fallback"
fi

# ── 8. Add sudoers entry (passwordless sudo for GUI) ──
echo "[8/10] Setting up passwordless sudo for GUI..."
echo "%users ALL=(root) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/src/gui.py" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
echo "  ✓ Sudoers rule installed"

# ── 9. Create desktop shortcut ──
echo "[9/10] Creating desktop shortcut..."

# Use pkexec if polkit is available, otherwise sudo
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

# Copy shortcut to all user desktops
for user_home in /home/*; do
    if [ -d "$user_home/Desktop" ]; then
        cp "$DESKTOP_FILE" "$user_home/Desktop/it-aman.desktop"
        USERNAME=$(basename "$user_home")
        chown "$USERNAME:$USERNAME" "$user_home/Desktop/it-aman.desktop" 2>/dev/null || true
        chmod +x "$user_home/Desktop/it-aman.desktop" 2>/dev/null || true
    fi
    # Arabic desktop folder name
    if [ -d "$user_home/سطح المكتب" ]; then
        cp "$DESKTOP_FILE" "$user_home/سطح المكتب/it-aman.desktop"
        USERNAME=$(basename "$user_home")
        chown "$USERNAME:$USERNAME" "$user_home/سطح المكتب/it-aman.desktop" 2>/dev/null || true
        chmod +x "$user_home/سطح المكتب/it-aman.desktop" 2>/dev/null || true
    fi
done

# Root desktop too
if [ -d "/root/Desktop" ]; then
    cp "$DESKTOP_FILE" "/root/Desktop/it-aman.desktop"
    chmod +x "/root/Desktop/it-aman.desktop" 2>/dev/null || true
fi

update-desktop-database /usr/share/applications/ 2>/dev/null || true
echo "  ✓ Desktop shortcut installed"

# ── 10. Enable and start daemon ──
echo "[10/10] Enabling and starting daemon..."
systemctl daemon-reload
systemctl enable it-aman.service
systemctl restart it-aman.service

# ── Verify ──
sleep 2

if systemctl is-active --quiet it-aman.service; then
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  ✅ IT Aman Printer Tool v3.12 installed!       ║"
    echo "╠══════════════════════════════════════════════════╣"
    echo "║  Daemon: ACTIVE (running in background)         ║"
    echo "║  Socket: $SOCKET_DIR/it-aman.sock"
    echo "║  Config: $CONFIG_DIR/config.json"
    echo "║  Defs:   $CONFIG_DIR/printer_definitions.json"
    echo "║  Log:    $LOG_DIR/daemon.log"
    echo "║                                                  ║"
    echo "║  Auto-update: ENABLED (checks every minute)     ║"
    echo "║  Centralized definitions: ENABLED               ║"
    echo "║                                                  ║"
    echo "║  To open the GUI (pick one):                     ║"
    echo "║  • Double-click desktop shortcut                 ║"
    echo "║  • Find it in Applications menu                  ║"
    echo "║  • Run: pkexec python3 $INSTALL_DIR/src/gui.py"
    echo "║                                                  ║"
    echo "║  No need for 'sudo python3 ...' anymore!         ║"
    echo "╚══════════════════════════════════════════════════╝"
else
    echo ""
    echo "⚠️  Daemon did not start. Check logs:"
    echo "  journalctl -u it-aman.service -n 20"
    echo "  cat $LOG_DIR/daemon.log"
fi
