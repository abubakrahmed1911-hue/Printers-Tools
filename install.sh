#!/bin/bash
# ═══════════════════════════════════════════════════════════
# IT Aman Printer Tool v3.18 — Installation Script
# ═══════════════════════════════════════════════════════════

set -e

REPO="abubakrahmed1911-hue/Printers-Tools"
BRANCH="main"
INSTALL_DIR="/opt/it-aman"
CONFIG_DIR="/etc/it-aman"
LOG_DIR="/var/log/it-aman"
SOCKET_DIR="/run/it-aman"
DRIVERS_DIR="$INSTALL_DIR/drivers"
SERVICE_FILE="/etc/systemd/system/it-aman.service"
DESKTOP_FILE="/usr/share/applications/it-aman.desktop"
POLICY_FILE="/usr/share/polkit-1/actions/com.it-aman.gui.policy"
SUDOERS_FILE="/etc/sudoers.d/it-aman-gui"

echo "========================================"
echo " IT Aman Printer Tool v3.18 Installer"
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

# ── 2b. Unlock immutable files (chattr +i blocks updates!) ──
echo "  Unlocking immutable files (chattr -i)..."
# Remove immutable flag from ALL files in the install dir
# This is CRITICAL: if someone ran 'chattr +i' on daemon.py, gui.py, etc.,
# even root cannot overwrite them — which breaks auto-updates.
if [ -d "$INSTALL_DIR" ]; then
    chattr -R -i "$INSTALL_DIR" 2>/dev/null || true
fi
# Also unlock backup dir if it exists
if [ -d "${INSTALL_DIR}.backup" ]; then
    chattr -R -i "${INSTALL_DIR}.backup" 2>/dev/null || true
fi
# Unlock CUPS driver files that may have been protected
for f in /usr/lib/cups/filter/rastertoprinter /usr/lib/cups/filter/rastertoprintercm /usr/lib/cups/filter/rastertoprinterlm /usr/share/cups/model/80mmSeries.ppd; do
    chattr -i "$f" 2>/dev/null || true
done
echo "  ✓ Immutable flags cleared"

# ── 3. Download files from GitHub ──
echo "[3/10] Downloading IT Aman files..."
mkdir -p "$INSTALL_DIR/src" "$DRIVERS_DIR"

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

# ── 4. Download thermal printer drivers from GitHub ──
echo "[4/10] Downloading thermal printer drivers..."
DRIVER_BASE_URL="$BASE_URL/drivers"

# Download driver files (silently skip if not found on GitHub)
for driver_file in rastertoprinter rastertoprintercm rastertoprinterlm 80mmSeries.ppd; do
    echo "  Downloading $driver_file..."
    curl -sL "$DRIVER_BASE_URL/$driver_file" -o "$DRIVERS_DIR/$driver_file" 2>/dev/null || true
    if [ -f "$DRIVERS_DIR/$driver_file" ]; then
        SIZE=$(stat -c%s "$DRIVERS_DIR/$driver_file" 2>/dev/null || echo "0")
        if [ "$SIZE" -gt 100 ]; then
            echo "    ✓ $driver_file downloaded ($SIZE bytes)"
        else
            echo "    ⚠ $driver_file is too small ($SIZE bytes) — may need manual placement"
            rm -f "$DRIVERS_DIR/$driver_file" 2>/dev/null || true
        fi
    else
        echo "    ⚠ $driver_file not found on GitHub — place manually in $DRIVERS_DIR/"
    fi
done

# Install driver files to CUPS directories
echo "  Installing drivers to CUPS..."

# Install filter files
for filter_file in rastertoprinter rastertoprintercm rastertoprinterlm; do
    if [ -f "$DRIVERS_DIR/$filter_file" ]; then
        cp "$DRIVERS_DIR/$filter_file" "/usr/lib/cups/filter/$filter_file" 2>/dev/null || true
        chmod 755 "/usr/lib/cups/filter/$filter_file" 2>/dev/null || true
        echo "    ✓ Installed filter: $filter_file"
    fi
done

# Install PPD file
if [ -f "$DRIVERS_DIR/80mmSeries.ppd" ]; then
    mkdir -p /usr/share/cups/model
    cp "$DRIVERS_DIR/80mmSeries.ppd" "/usr/share/cups/model/80mmSeries.ppd" 2>/dev/null || true
    echo "    ✓ Installed PPD: 80mmSeries.ppd"
fi

# ── 5. Create directories ──
echo "[5/10] Creating directories..."
mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$SOCKET_DIR"

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
    echo "║  IT Aman Printer Tool v3.18 installed!          ║"
    echo "╠══════════════════════════════════════════════════╣"
    echo "║  Daemon: ACTIVE (running in background)         ║"
    echo "║  Socket: $SOCKET_DIR/it-aman.sock"
    echo "║  Config: $CONFIG_DIR/config.json"
    echo "║  Log:    $LOG_DIR/daemon.log"
    echo "║  Drivers: $DRIVERS_DIR"
    echo "║                                                  ║"
    echo "║  Auto-update: ENABLED (auto-install from GitHub) ║"
    echo "║                                                  ║"
    echo "║  To open the GUI (pick one):                     ║"
    echo "║  * Double-click desktop shortcut                 ║"
    echo "║  * Find it in Applications menu                  ║"
    echo "║  * Run: pkexec python3 $INSTALL_DIR/src/gui.py"
    echo "║                                                  ║"
    echo "║  Thermal drivers installed to:                   ║"
    echo "║  * /usr/lib/cups/filter/                         ║"
    echo "║  * /usr/share/cups/model/                        ║"
    echo "╚══════════════════════════════════════════════════╝"
else
    echo ""
    echo "Daemon did not start. Check logs:"
    echo "  journalctl -u it-aman.service -n 20"
    echo "  cat $LOG_DIR/daemon.log"
fi
