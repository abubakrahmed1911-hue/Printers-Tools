#!/bin/bash
# ═══════════════════════════════════════════════════════════
# IT Aman Printer Tool v3.8 — Installation Script
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

echo "========================================"
echo " IT Aman Printer Tool v3.8 Installer"
echo "========================================"
echo ""

# ── Must be root ──
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Run this script as root (sudo)"
    exit 1
fi

# ── 1. Install dependencies ──
echo "[1/7] Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    cups cups-bsd avahi-daemon avahi-utils \
    curl wget 2>/dev/null || true

# ── 2. Stop old service if running ──
echo "[2/7] Stopping old service (if any)..."
systemctl stop it-aman.service 2>/dev/null || true
systemctl disable it-aman.service 2>/dev/null || true

# ── 3. Download files from GitHub ──
echo "[3/7] Downloading IT Aman files..."
mkdir -p "$INSTALL_DIR/src"

BASE_URL="https://raw.githubusercontent.com/$REPO/$BRANCH"

curl -sL "$BASE_URL/src/daemon.py" -o "$INSTALL_DIR/src/daemon.py"
curl -sL "$BASE_URL/src/gui.py" -o "$INSTALL_DIR/src/gui.py"
curl -sL "$BASE_URL/version.json" -o "$INSTALL_DIR/version.json"
curl -sL "$BASE_URL/public.pem" -o "$INSTALL_DIR/public.pem"
curl -sL "$BASE_URL/.gitignore" -o "$INSTALL_DIR/.gitignore"
curl -sL "$BASE_URL/CHANGELOG.md" -o "$INSTALL_DIR/CHANGELOG.md"

# Make daemon executable
chmod +x "$INSTALL_DIR/src/daemon.py"
chmod +x "$INSTALL_DIR/src/gui.py"

echo "  Downloaded to $INSTALL_DIR"

# ── 4. Create directories ──
echo "[4/7] Creating directories..."
mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$SOCKET_DIR"

# ── 5. Create systemd service ──
echo "[5/7] Installing systemd service..."
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

# ── 6. Create desktop shortcut ──
echo "[6/7] Creating desktop shortcut..."
cat > "$DESKTOP_FILE" << 'DESKTOP_EOF'
[Desktop Entry]
Name=IT Aman Printer Tool
Name[ar]=أداة إدارة الطابعات
Comment=Printer management tool
Comment[ar]=أداة إدارة الطابعات
Exec=sudo python3 /opt/it-aman/src/gui.py
Icon=printer
Terminal=false
Type=Application
Categories=System;Settings;
DESKTOP_EOF

# ── 7. Enable and start daemon ──
echo "[7/7] Enabling and starting daemon..."
systemctl daemon-reload
systemctl enable it-aman.service
systemctl restart it-aman.service

# ── Verify ──
sleep 2

if systemctl is-active --quiet it-aman.service; then
    echo ""
    echo "✅ IT Aman Printer Tool v3.8 installed successfully!"
    echo ""
    echo "  Daemon: ACTIVE (running in background)"
    echo "  Socket: $SOCKET_DIR/it-aman.sock"
    echo "  Config: $CONFIG_DIR/config.json"
    echo "  Log:    $LOG_DIR/daemon.log"
    echo ""
    echo "  Auto-update: ENABLED (checks every 60 seconds)"
    echo ""
    echo "To open the GUI:"
    echo "  sudo python3 $INSTALL_DIR/src/gui.py"
    echo ""
    echo "Or find 'IT Aman Printer Tool' in your applications menu."
else
    echo ""
    echo "⚠️  Daemon did not start. Check logs:"
    echo "  journalctl -u it-aman.service -n 20"
    echo "  cat $LOG_DIR/daemon.log"
fi
