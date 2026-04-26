#!/usr/bin/env python3
"""
IT Aman Printer Daemon v3.11
=============================
A Unix socket daemon for managing CUPS printers on Linux.
Runs as root, listens on /run/it-aman/it-aman.sock, and processes
JSON commands from the GTK3 GUI client.
Developed by IT Helpdesk Operation.

Key changes from v3.10:
  - CRITICAL FIX: pulse_loop timer leak causing GUI freeze — now returns True
    for GLib auto-repeat instead of creating new timers each cycle
  - CRITICAL FIX: Network printer setup now works when only URI is provided
    (no IP), extracting IP from URI for LPD fallback
  - CRITICAL FIX: Thermal driver install now receives USB URI from wizard
    detection, ensuring correct printer is configured
  - FIX: Spooler clear now only removes temp/control files (c*) not data
    files (d*), preventing accidental job data loss
  - FIX: CUPS start retries 3 times before resorting to spool cleanup
  - FIX: Network printer card passes full_uri and uri for better setup
  - VERSION bumped to 3.11

Architecture:
  - Unix socket at /run/it-aman/it-aman.sock
  - JSON command dispatch via ALLOWED_COMMANDS whitelist
  - Config at /etc/it-aman/config.json
  - Logging to /var/log/it-aman/daemon.log
  - ThreadPoolExecutor for network scan (64 TCP, 20 model probe)
"""

import os
import sys
import json
import socket
import struct
import signal
import subprocess
import threading
import logging
import logging.handlers
import shutil
import tempfile
import hashlib
import time
import re
import zipfile
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "3.11"

# Paths
SOCKET_PATH = "/run/it-aman/it-aman.sock"
CONFIG_DIR = "/etc/it-aman"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOG_DIR = "/var/log/it-aman"
LOG_PATH = os.path.join(LOG_DIR, "daemon.log")
PID_PATH = "/run/it-aman/it-aman.pid"

# GitHub update URLs (public repo -- no token required)
GITHUB_REPO = "abubakrahmed1911-hue/Printers-Tools"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"

# Driver download URLs
KYOCERA_DEB_URL = (
    "https://www.dropbox.com/scl/fi/u4ilpehz9aeemnnfeec6z/"
    "kyodialog_9.3-0_amd64.deb?rlkey=re8satdq4iduzxaqugb7l0oqw"
    "&st=4a85xjj9&dl=1"
)
XPRINTER_DRIVER_URL = (
    "https://www.dropbox.com/scl/fi/9knkouz84hqeouumyk5bd/"
    "install-xp80?rlkey=gjibguc0903787o1bjnx1s89u&st=fgtg9f6a&dl=1"
)
SPRT_DRIVER_URL = (
    "https://www.dropbox.com/scl/fo/eoxs40b23h5g8zxk0vhnj/"
    "AGVfJEgg05my1TcWe1xHCs4?rlkey=pqx2yv4x5blqmz0vks058ef9g"
    "&st=hcp53bq0&dl=1"
)

# Thermal printer constants
SPRT_PPD_DEST = "/usr/share/cups/model/SPRIT/80mmSeries.ppd"
XPRINTER_PRINTER_NAME = "xp80"
SPRT_PRINTER_NAME = "SPRT"

# Network scan defaults
SCAN_TCP_WORKERS = 64
SCAN_PROBE_WORKERS = 20
SCAN_PORTS = [631, 9100]          # IPP + raw JetDirect
SCAN_TIMEOUT_SEC = 1.0            # per TCP connect
MODEL_PROBE_TIMEOUT = 5           # seconds for HTTP model probe

# Socket buffer
SOCKET_RECV_BUF = 65536

# Auto-update settings
AUTO_UPDATE_INTERVAL = 60       # seconds between checks (1 minute)
AUTO_UPDATE_ENABLED = True      # set to False to disable background auto-update

# User-Agent for HTTP requests (uses VERSION constant)
_USER_AGENT = f"IT-Aman-Daemon/{VERSION}"

# Allowed commands whitelist -- anything not listed is rejected
ALLOWED_COMMANDS = {
    "fix",
    "scan",
    "remove_printer",
    "quick_fix_spooler",
    "network_scan",
    "setup_printer",
    "install_thermal_brand",
    "detect_usb_printers",
    "discover_printers",
    "clear_jobs",
    "test_print",
    "update_all",
    "ping",
    "get_version",
    "get_config",
    "set_language",
    "check_update",
    "list_installed_printers",
    # GUI action aliases (also accepted)
    "diagnose",
    "scan_network",
    "add_network_printer",
    "install_thermal_driver",
    "fix_spooler",
    "detect_usb_printer",
    "list_printers",
    "repair_printer",
    "update",
    "define_driver",
}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure rotating-file logging for the daemon."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("it-aman")
    logger.setLevel(logging.DEBUG)

    # Rotating file handler -- 2 MB per file, keep 5 backups
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=2_000_000, backupCount=5
    )
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Also log to stderr while in foreground
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = setup_logging()

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "version": VERSION,
    "language": "en",
}


def load_config() -> dict:
    """Load config from disk, returning defaults if missing."""
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as fh:
                cfg = json.load(fh)
            # Merge with defaults so new keys appear
            merged = {**DEFAULT_CONFIG, **cfg}
            return merged
    except Exception as exc:
        log.warning("Failed to load config: %s -- using defaults", exc)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    """Persist config to disk (atomic write)."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cfg, fh, indent=2)
        os.replace(tmp, CONFIG_PATH)
        log.info("Config saved to %s", CONFIG_PATH)
    except Exception as exc:
        log.error("Failed to save config: %s", exc)


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd: list, timeout: int = 30, check: bool = False) -> tuple:
    """
    Run a subprocess command and return (returncode, stdout, stderr).
    Decodes output as UTF-8 with replacement for safety.
    """
    log.debug("run_cmd: %s", cmd)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, out, err)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        log.warning("Command timed out: %s", cmd)
        return -1, "", "timeout"
    except FileNotFoundError:
        log.warning("Command not found: %s", cmd[0])
        return -2, "", f"command not found: {cmd[0]}"
    except Exception as exc:
        log.error("run_cmd exception: %s", exc)
        return -3, "", str(exc)


def run_shell(script: str, timeout: int = 60) -> tuple:
    """Run a shell command string and return (returncode, stdout, stderr)."""
    return run_cmd(["bash", "-c", script], timeout=timeout)


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: str, desc: str = "file") -> bool:
    """Download a file from *url* to *dest*. Returns True on success."""
    log.info("Downloading %s from %s", desc, url)
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
        size = os.path.getsize(dest)
        log.info("Downloaded %s (%d bytes) to %s", desc, size, dest)
        return True
    except Exception as exc:
        log.error("Download failed for %s: %s", desc, exc)
        # Clean up partial file
        if os.path.isfile(dest):
            os.remove(dest)
        return False


def download_text(url: str, timeout: int = 30) -> str | None:
    """Download a small text file and return its content, or None on error."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except Exception as exc:
        log.error("download_text failed for %s: %s", url, exc)
        return None


def get_local_subnet() -> str | None:
    """
    Determine the local /24 subnet for scanning.
    Returns something like '192.168.1' or None.
    """
    try:
        # Create a UDP socket to an external address (doesn't actually send)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        # Return first three octets
        parts = local_ip.split(".")
        if len(parts) == 4:
            subnet = ".".join(parts[:3])
            log.info("Detected local subnet: %s.0/24", subnet)
            return subnet
    except Exception as exc:
        log.warning("Could not determine local subnet: %s", exc)
    return None


# ---------------------------------------------------------------------------
# TCP port scanner (used by network_scan)
# ---------------------------------------------------------------------------

def tcp_check(ip: str, port: int, timeout: float = SCAN_TIMEOUT_SEC) -> bool:
    """Return True if *ip:port* accepts a TCP connection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            return result == 0
    except Exception:
        return False


def scan_subnet_tcp(subnet: str) -> list[dict]:
    """
    Scan an entire /24 subnet for SCAN_PORTS using a thread pool.
    Returns list of dicts: {ip, port, open}.
    """
    results = []
    base = subnet

    def _check(host_byte: int):
        ip = f"{base}.{host_byte}"
        for port in SCAN_PORTS:
            if tcp_check(ip, port):
                return {"ip": ip, "port": port, "open": True}
        return None

    with ThreadPoolExecutor(max_workers=SCAN_TCP_WORKERS) as pool:
        futures = {pool.submit(_check, h): h for h in range(1, 255)}
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                results.append(res)

    log.info("TCP scan found %d hosts on %s.0/24", len(results), base)
    return results


# ---------------------------------------------------------------------------
# HTTP model probe (used by network_scan)
# ---------------------------------------------------------------------------

def http_probe_model(ip: str) -> str | None:
    """
    Try to determine the printer model via HTTP/IPP queries.
    Queries:
      1. http://IP:631/ipp/print (CUPS IPP Everywhere resource)
      2. http://IP/index.html    (common printer web UI)
    Returns model string or None.
    """
    urls_to_try = [
        f"http://{ip}:631/ipp/print",
        f"http://{ip}/index.html",
    ]
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _USER_AGENT,
            })
            with urllib.request.urlopen(req, timeout=MODEL_PROBE_TIMEOUT) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                # Look for common model patterns
                for pattern in [
                    r'<title>(.*?)</title>',
                    r'printer-model["\s:]+(["\']?)([^"\']+)\1',
                    r'product\s*=\s*"([^"]+)"',
                    r'Model[^:]*:\s*([^\n<]+)',
                ]:
                    m = re.search(pattern, body, re.IGNORECASE)
                    if m:
                        model = m.group(1 if pattern != r'product\s*=\s*"([^"]+)"' else 1).strip()
                        if model and len(model) < 200:
                            log.info("HTTP probe for %s found model: %s", ip, model)
                            return model
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# CUPS helpers
# ---------------------------------------------------------------------------

def cups_is_running() -> bool:
    """Check if the CUPS service is active."""
    rc, _, _ = run_cmd(["systemctl", "is-active", "--quiet", "cups"])
    return rc == 0


def cups_restart() -> bool:
    """Restart the CUPS service. Returns True on success."""
    rc, _, err = run_cmd(["systemctl", "restart", "cups"])
    if rc == 0:
        log.info("CUPS restarted successfully")
        return True
    log.error("CUPS restart failed: %s", err)
    return False


def cups_start() -> bool:
    """Start the CUPS service. Returns True on success."""
    rc, _, err = run_cmd(["systemctl", "start", "cups"])
    if rc == 0:
        log.info("CUPS started successfully")
        return True
    log.error("CUPS start failed: %s", err)
    return False


def cups_stop() -> bool:
    """Stop the CUPS service. Returns True on success."""
    rc, _, err = run_cmd(["systemctl", "stop", "cups"])
    if rc == 0:
        log.info("CUPS stopped successfully")
        return True
    log.error("CUPS stop failed: %s", err)
    return False


def get_cups_backends() -> list[str]:
    """Return list of URIs from lpinfo -v (existing CUPS backends)."""
    rc, out, _ = run_cmd(["lpinfo", "-v"])
    if rc != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def get_cups_ppd_drivers() -> list[dict]:
    """Return list of available PPD drivers from lpinfo -m."""
    rc, out, _ = run_cmd(["lpinfo", "-m"], timeout=15)
    if rc != 0 or not out:
        return []
    drivers = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "make-and-model  ppd-name"
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            drivers.append({"ppd": parts[0], "description": parts[1]})
        elif len(parts) == 1:
            drivers.append({"ppd": parts[0], "description": parts[0]})
    return drivers


def find_ppd_for_model(model: str) -> str | None:
    """
    Search lpinfo -m output for a PPD matching the given model name.
    Returns the PPD name (e.g. 'manufacturer-PPDs/Kyocera/...') or None.
    """
    drivers = get_cups_ppd_drivers()
    model_lower = model.lower()
    # Score-based matching
    best_match = None
    best_score = 0
    for drv in drivers:
        desc_lower = drv["description"].lower()
        ppd_lower = drv["ppd"].lower()
        # Count how many model keywords appear
        keywords = [w for w in model_lower.split() if len(w) > 2]
        score = sum(1 for kw in keywords if kw in desc_lower or kw in ppd_lower)
        if score > best_score:
            best_score = score
            best_match = drv["ppd"]
    if best_match and best_score >= 2:
        log.info("Found PPD for '%s': %s (score=%d)", model, best_match, best_score)
        return best_match
    return None


def is_printer_exists(name: str) -> bool:
    """Check if a printer with the given name already exists in CUPS."""
    rc, out, _ = run_cmd(["lpstat", "-p", name])
    return rc == 0


def get_usb_uris() -> list[str]:
    """Return list of USB printer URIs from lpinfo -v."""
    backends = get_cups_backends()
    return [b.split(":", 1)[1].strip() for b in backends if b.startswith("usb://")]


def _get_printer_device_uri(name: str) -> str | None:
    """Get the device URI for a given printer name via lpstat -v."""
    rc, out, _ = run_cmd(["lpstat", "-v", name])
    if rc == 0 and out:
        # Format: "device for NAME: URI"
        m = re.search(r'device\s+for\s+\S+:\s*(.+)', out)
        if m:
            return m.group(1).strip()
    return None


def _get_printer_job_count(name: str) -> int:
    """Get the number of queued jobs for a given printer via lpstat -o."""
    rc, out, _ = run_cmd(["lpstat", "-o", name])
    if rc != 0 or not out:
        return 0
    count = 0
    for line in out.splitlines():
        # Lines like: "NAME-123  user  size  date"
        parts = line.strip().split()
        if parts and parts[0].startswith(name):
            count += 1
    return count


def _get_default_printer() -> str | None:
    """Get the default printer name via lpstat -d."""
    rc, out, _ = run_cmd(["lpstat", "-d"])
    if rc == 0 and out:
        m = re.search(r'system default destination:\s*(\S+)', out, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Kyocera driver auto-install
# ---------------------------------------------------------------------------

def install_kyocera_driver() -> bool:
    """
    Download and install the Kyocera deb package from Dropbox.
    Returns True on success.
    """
    log.info("Installing Kyocera driver from Dropbox")
    tmp_dir = tempfile.mkdtemp(prefix="kyocera_")
    deb_path = os.path.join(tmp_dir, "kyodialog_9.3-0_amd64.deb")

    try:
        if not download_file(KYOCERA_DEB_URL, deb_path, "Kyocera driver deb"):
            return False

        # Install with dpkg
        rc, out, err = run_cmd(["dpkg", "-i", deb_path], timeout=60)
        if rc != 0:
            log.warning("dpkg -i returned %d: %s", rc, err)
            # Try to fix dependencies
            run_cmd(["apt-get", "install", "-f", "-y"], timeout=120)
        else:
            log.info("Kyocera driver installed successfully")

        # Restart CUPS to pick up new PPDs
        cups_restart()
        return True
    except Exception as exc:
        log.error("Kyocera driver install failed: %s", exc)
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Thermal printer cut-defaults helper
# ---------------------------------------------------------------------------

def _set_thermal_cut_defaults(printer_name: str):
    """
    Set thermal-printer-specific defaults after installation.
    Ensures the printer uses partial cut and sensible paper sizes.
    """
    # Common thermal defaults: 80mm paper, no margins, raw mode
    lpoptions = [
        "media=80mm",
        "orientation-requested=3",   # portrait
    ]
    # Build lpadmin -p NAME -o key=value for each option
    cmd = ["lpadmin", "-p", printer_name]
    for opt in lpoptions:
        cmd.extend(["-o", opt])
    rc, _, err = run_cmd(cmd)
    if rc != 0:
        log.warning("Failed to set thermal defaults for %s: %s", printer_name, err)
    else:
        log.info("Set thermal cut defaults for %s", printer_name)

    # Also try to set DocumentCut and FullCut via lpoptions
    cut_opts = [
        "-o", "DocumentCut=PartialCut",
        "-o", "FullCut=PartialCut",
    ]
    rc2, _, err2 = run_cmd(["lpadmin", "-p", printer_name] + cut_opts)
    if rc2 != 0:
        log.debug("Cut options not supported for %s (non-fatal): %s", printer_name, err2)

    # Enable and accept
    run_cmd(["cupsenable", printer_name])
    run_cmd(["cupsaccept", printer_name])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_ping(params: dict) -> dict:
    """Simple connectivity check."""
    return {"status": "ok", "message": "pong", "version": VERSION}


def handle_get_version(params: dict) -> dict:
    """Return the daemon version."""
    return {"status": "ok", "version": VERSION}


def handle_check_update(params: dict) -> dict:
    """
    Check GitHub for the latest version.
    Returns both the remote version and whether an update is available
    (compared to local VERSION), so the GUI can decide whether to show
    a notification banner.
    """
    version_url = f"{RAW_BASE}/version.json"
    version_text = download_text(version_url, timeout=15)
    if not version_text:
        return {"status": "error", "message": "Cannot reach update server"}
    try:
        remote_info = json.loads(version_text)
        remote_version = remote_info.get("version", "")
        update_available = _compare_versions(remote_version, VERSION) > 0
        return {
            "status": "ok",
            "version": remote_version,
            "local_version": VERSION,
            "update_available": update_available,
        }
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid version info from server"}


def handle_get_config(params: dict) -> dict:
    """Return the current configuration."""
    cfg = load_config()
    return {"status": "ok", "config": cfg}


def handle_set_language(params: dict) -> dict:
    """Set the GUI language in config."""
    lang = params.get("language", "en")
    if not isinstance(lang, str) or len(lang) != 2:
        return {"status": "error", "message": "Invalid language code (expected 2-letter ISO)"}
    cfg = load_config()
    cfg["language"] = lang
    save_config(cfg)
    return {"status": "ok", "language": lang}


# ---- handle_fix (Smart Diagnostic) ----------------------------------------

def handle_fix(params: dict) -> dict:
    """
    Smart diagnostic: check CUPS status, stuck jobs, disabled printers,
    and attempt automatic fixes. Returns a detailed report.
    """
    report = {"status": "ok", "actions": [], "issues_found": 0}

    # 1. Check if CUPS is running
    if not cups_is_running():
        report["issues_found"] += 1
        log.info("CUPS not running -- attempting restart")
        if cups_restart():
            report["actions"].append("CUPS was not running; restarted successfully")
        else:
            report["actions"].append("CUPS was not running; restart FAILED")
            report["status"] = "error"
            return report
    else:
        report["actions"].append("CUPS service is running")

    # 2. Check for stuck jobs
    rc, out, _ = run_cmd(["lpstat", "-o"])
    if rc == 0 and out:
        stuck_printers = set()
        for line in out.splitlines():
            parts = line.strip().split()
            if parts:
                # Format: "printer-name-123  user  size  date"
                printer = "-".join(parts[0].split("-")[:-1]) if "-" in parts[0] else parts[0]
                stuck_printers.add(printer)
        if stuck_printers:
            report["issues_found"] += 1
            for p in stuck_printers:
                log.info("Cancelling stuck jobs on %s", p)
                run_cmd(["cancel", "-a", p])
            report["actions"].append(
                f"Found stuck jobs on: {', '.join(stuck_printers)}; cancelled all"
            )
        else:
            report["actions"].append("No stuck print jobs found")
    else:
        report["actions"].append("No stuck print jobs found")

    # 3. Check for disabled printers
    rc, out, _ = run_cmd(["lpstat", "-p"])
    disabled = []
    if rc == 0 and out:
        for line in out.splitlines():
            if "disabled" in line.lower():
                # Format: "printer NAME disabled since ..."
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    disabled.append(name)

    if disabled:
        report["issues_found"] += 1
        for name in disabled:
            log.info("Enabling disabled printer: %s", name)
            run_cmd(["cupsenable", name])
            run_cmd(["cupsaccept", name])
        report["actions"].append(
            f"Re-enabled disabled printers: {', '.join(disabled)}"
        )
    else:
        report["actions"].append("All printers are enabled")

    # 4. Check CUPS error log for recent errors
    rc, out, _ = run_cmd(
        ["bash", "-c", "tail -50 /var/log/cups/error_log 2>/dev/null | grep -i error | tail -5"]
    )
    if out:
        errors = out.splitlines()
        if errors:
            report["actions"].append(f"Recent CUPS errors: {errors[0][:200]}")

    return report


# ---- handle_scan (discover network printers via CUPS) ----------------------

def handle_scan(params: dict) -> dict:
    """
    Quick scan using CUPS built-in discovery (lpinfo -v and avahi).
    Less thorough than network_scan but faster.
    """
    printers = []

    # 1. lpinfo -v for existing backends
    backends = get_cups_backends()
    for b in backends:
        if b.startswith("ipp://") or b.startswith("ipps://") or b.startswith("lpd://"):
            uri = b.split(":", 1)[1].strip() if ":" in b else b
            printers.append({
                "uri": uri,
                "full_uri": b,
                "source": "lpinfo",
                "type": "network",
            })
        elif b.startswith("usb://"):
            printers.append({
                "uri": b.split(":", 1)[1].strip() if ":" in b else b,
                "full_uri": b,
                "source": "lpinfo",
                "type": "usb",
            })

    # 2. Try avahi-browse for IPP printers
    rc, out, _ = run_cmd(
        ["avahi-browse", "-rt", "_ipp._tcp"], timeout=15
    )
    if rc == 0 and out:
        for line in out.splitlines():
            # avahi-browse -rt output includes lines like:
            # =   eth0 IPv4 HP LaserJet        Internet Printer     local
            # hostname = [HPxxxx.local]
            # address = [192.168.1.50]
            # port = [631]
            # txt = [...]
            if "address" in line.lower() and "=" in line:
                m = re.search(r'address\s*=\s*\[([^\]]+)\]', line)
                if m:
                    ip = m.group(1)
                    # Check if we already have this IP
                    if not any(p.get("ip") == ip for p in printers):
                        printers.append({
                            "ip": ip,
                            "uri": f"ipp://{ip}:631/ipp/print",
                            "source": "avahi",
                            "type": "network",
                        })

    return {"status": "ok", "printers": printers}


# ---- handle_network_scan (thorough TCP + mDNS + HTTP probe) ---------------

def handle_network_scan(params: dict) -> dict:
    """
    Thorough network scan for printers:
      1. lpinfo -v (existing CUPS backends)
      2. TCP scan on ports 631 + 9100 across /24 subnet (64 threads)
      3. mDNS via avahi-browse _ipp._tcp
      4. HTTP model probe for each discovered IP
    Returns: {status: "ok", printers: [{ip, uri, model, source}, ...]}
    """
    printers = []
    seen_ips = set()

    # --- Phase 1: lpinfo -v backends ---
    backends = get_cups_backends()
    for b in backends:
        if b.startswith("ipp://") or b.startswith("ipps://"):
            uri = b.split(":", 1)[1].strip() if ":" in b else b
            # Try to extract IP
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', uri)
            ip = ip_match.group(1) if ip_match else None
            printers.append({
                "ip": ip,
                "uri": uri,
                "full_uri": b,
                "model": None,
                "source": "lpinfo",
            })
            if ip:
                seen_ips.add(ip)
        elif b.startswith("lpd://"):
            uri = b.split(":", 1)[1].strip() if ":" in b else b
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', uri)
            ip = ip_match.group(1) if ip_match else None
            printers.append({
                "ip": ip,
                "uri": uri,
                "full_uri": b,
                "model": None,
                "source": "lpinfo",
            })
            if ip:
                seen_ips.add(ip)
        elif b.startswith("usb://"):
            printers.append({
                "ip": None,
                "uri": b.split(":", 1)[1].strip() if ":" in b else b,
                "full_uri": b,
                "model": None,
                "source": "lpinfo-usb",
            })

    # --- Phase 2: TCP scan ---
    subnet = params.get("subnet") or get_local_subnet()
    if subnet:
        tcp_results = scan_subnet_tcp(subnet)
        for entry in tcp_results:
            ip = entry["ip"]
            if ip not in seen_ips:
                seen_ips.add(ip)
                printers.append({
                    "ip": ip,
                    "uri": f"ipp://{ip}:631/ipp/print",
                    "model": None,
                    "source": f"tcp-scan:port-{entry['port']}",
                })
    else:
        log.warning("No subnet detected; skipping TCP scan")

    # --- Phase 3: mDNS / avahi-browse ---
    rc, out, _ = run_cmd(
        ["avahi-browse", "-rt", "_ipp._tcp"], timeout=15
    )
    avahi_entries = {}
    if rc == 0 and out:
        current_name = None
        for line in out.splitlines():
            # Parse avahi-browse -rt output
            if "=" in line and "IPv4" in line:
                m_name = re.search(r'IPv4\s+(\S+)\s+', line)
                if m_name:
                    current_name = m_name.group(1)
                    avahi_entries[current_name] = avahi_entries.get(current_name, {})
            if current_name and "address" in line:
                m = re.search(r'address\s*=\s*\[([^\]]+)\]', line)
                if m:
                    avahi_entries.setdefault(current_name, {})["ip"] = m.group(1)
            if current_name and "port" in line:
                m = re.search(r'port\s*=\s*\[([^\]]+)\]', line)
                if m:
                    avahi_entries.setdefault(current_name, {})["port"] = m.group(1)
            if current_name and "txt" in line:
                m = re.search(r'product=([^)\s]+)', line)
                if m:
                    avahi_entries.setdefault(current_name, {})["model"] = urllib.parse.unquote(m.group(1))

    for name, info in avahi_entries.items():
        ip = info.get("ip")
        if not ip:
            continue
        if ip not in seen_ips:
            seen_ips.add(ip)
            port = info.get("port", "631")
            printers.append({
                "ip": ip,
                "uri": f"ipp://{ip}:{port}/ipp/print",
                "model": info.get("model"),
                "source": "avahi-mdns",
            })
        else:
            # Enrich existing entry with model from mDNS
            for p in printers:
                if p.get("ip") == ip and not p.get("model") and info.get("model"):
                    p["model"] = info["model"]

    # --- Phase 4: HTTP model probe for entries without a model ---
    ips_to_probe = [
        p for p in printers
        if p.get("ip") and not p.get("model")
    ]

    if ips_to_probe:
        log.info("Probing %d IPs for model info", len(ips_to_probe))

        def _probe(entry):
            model = http_probe_model(entry["ip"])
            return entry["ip"], model

        with ThreadPoolExecutor(max_workers=SCAN_PROBE_WORKERS) as pool:
            futures = {pool.submit(_probe, e): e for e in ips_to_probe}
            for fut in as_completed(futures):
                ip, model = fut.result()
                if model:
                    for p in printers:
                        if p.get("ip") == ip:
                            p["model"] = model

    log.info("Network scan complete: %d printers found", len(printers))
    return {"status": "ok", "printers": printers}


# ---- handle_setup_printer (IPP Everywhere -> LPD -> PPD -> Kyocera) --------

def handle_setup_printer(params: dict) -> dict:
    """
    Set up a network printer with automatic driver detection.
    Strategy:
      1. Try IPP Everywhere: lpadmin -p NAME -E -v ipp://IP:631/ipp/print -m everywhere
      2. If fails, try LPD: lpadmin -p NAME -E -v lpd://IP/queue -m everywhere
      3. If no driver, auto-detect PPD via lpinfo -m
      4. If still no driver AND model contains Kyocera/ECOSYS, install Kyocera deb
      5. Set defaults: InputSlot=One, Duplex=None
      6. Enable + accept + set default
    """
    name = params.get("name", "").strip()
    ip = params.get("ip", "").strip()
    model = params.get("model", "").strip()
    uri = params.get("uri", "").strip()
    set_default = params.get("set_default", True)

    if not name:
        return {"status": "error", "message": "Printer name is required"}
    if not ip and not uri:
        return {"status": "error", "message": "IP address or URI is required"}

    # Sanitize printer name (CUPS allows letters, digits, hyphens, underscores)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    if safe_name != name:
        log.info("Sanitized printer name: '%s' -> '%s'", name, safe_name)
        name = safe_name

    # Build URIs — handle both ip-only and uri-only cases
    if ip:
        ipp_uri = f"ipp://{ip}:631/ipp/print"
        lpd_uri = f"lpd://{ip}/queue"
    elif uri:
        # Use the provided URI directly for IPP attempt
        ipp_uri = uri
        lpd_uri = None
        # Try to extract IP from URI for LPD fallback
        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', uri)
        if ip_match:
            extracted_ip = ip_match.group(1)
            lpd_uri = f"lpd://{extracted_ip}/queue"
    else:
        ipp_uri = ""
        lpd_uri = None

    setup_report = {"status": "ok", "actions": [], "printer": name}

    # Remove existing printer with same name first
    if is_printer_exists(name):
        log.info("Printer '%s' already exists -- removing first", name)
        run_cmd(["lpadmin", "-x", name])

    # --- Attempt 1: IPP Everywhere ---
    log.info("Attempt 1: IPP Everywhere for %s at %s", name, ipp_uri)
    if not ipp_uri:
        log.warning("No URI available for IPP Everywhere setup")
        rc = -1
        err = "No URI provided"
    else:
        rc, out, err = run_cmd(
            ["lpadmin", "-p", name, "-E", "-v", ipp_uri, "-m", "everywhere"],
            timeout=30,
        )
    if rc == 0:
        setup_report["actions"].append(f"Set up via IPP Everywhere: {ipp_uri}")
        log.info("IPP Everywhere setup succeeded for %s", name)
    else:
        log.warning("IPP Everywhere failed: %s", err)

        # --- Attempt 2: LPD + everywhere ---
        if lpd_uri:
            log.info("Attempt 2: LPD for %s at %s", name, lpd_uri)
            rc, out, err = run_cmd(
                ["lpadmin", "-p", name, "-E", "-v", lpd_uri, "-m", "everywhere"],
                timeout=30,
            )
            if rc == 0:
                setup_report["actions"].append(f"Set up via LPD Everywhere: {lpd_uri}")
                log.info("LPD Everywhere setup succeeded for %s", name)
            else:
                log.warning("LPD Everywhere failed: %s", err)

        # --- Attempt 3: Find PPD via lpinfo ---
        if rc != 0 or not is_printer_exists(name):
            search_model = model or name
            log.info("Attempt 3: Searching PPD for model '%s'", search_model)
            ppd = find_ppd_for_model(search_model)

            if ppd:
                use_uri = ipp_uri
                log.info("Found PPD: %s", ppd)
                rc, out, err = run_cmd(
                    ["lpadmin", "-p", name, "-E", "-v", use_uri, "-m", ppd],
                    timeout=30,
                )
                if rc == 0:
                    setup_report["actions"].append(f"Set up with PPD: {ppd}")
                    log.info("PPD setup succeeded for %s", name)
                else:
                    log.warning("PPD setup failed: %s", err)
            else:
                log.info("No PPD found for '%s'", search_model)

                # --- Attempt 4: Kyocera auto-install ---
                model_lower = (model or name).lower()
                if "kyocera" in model_lower or "ecosys" in model_lower:
                    log.info("Attempt 4: Kyocera driver auto-install")
                    if install_kyocera_driver():
                        # Re-search for PPD after installation
                        time.sleep(2)  # Give CUPS time to pick up new PPDs
                        ppd = find_ppd_for_model(model or name)
                        if ppd:
                            use_uri = ipp_uri
                            rc, out, err = run_cmd(
                                ["lpadmin", "-p", name, "-E", "-v", use_uri, "-m", ppd],
                                timeout=30,
                            )
                            if rc == 0:
                                setup_report["actions"].append(
                                    f"Installed Kyocera driver, set up with PPD: {ppd}"
                                )
                            else:
                                setup_report["actions"].append(
                                    f"Kyocera driver installed but PPD setup failed: {err}"
                                )
                        else:
                            setup_report["actions"].append(
                                "Kyocera driver installed but no matching PPD found"
                            )
                    else:
                        setup_report["actions"].append("Kyocera driver installation failed")

        # Final check -- if still not created, try with raw driver
        if not is_printer_exists(name):
            log.info("Final attempt: raw driver for %s", name)
            use_uri = ipp_uri or lpd_uri
            rc, out, err = run_cmd(
                ["lpadmin", "-p", name, "-E", "-v", use_uri, "-m", "raw"],
                timeout=30,
            )
            if rc == 0:
                setup_report["actions"].append("Set up with raw driver (no PPD)")
            else:
                setup_report["status"] = "error"
                setup_report["actions"].append(f"All setup methods failed: {err}")
                return setup_report

    # Set common defaults
    run_cmd(["lpadmin", "-p", name, "-o", "InputSlot=One"])
    run_cmd(["lpadmin", "-p", name, "-o", "Duplex=None"])
    run_cmd(["lpadmin", "-p", name, "-o", "media=a4"])

    # Enable and accept
    run_cmd(["cupsenable", name])
    run_cmd(["cupsaccept", name])

    # Set as default if requested
    if set_default:
        run_cmd(["lpadmin", "-d", name])
        setup_report["actions"].append("Set as default printer")

    setup_report["actions"].append("Setup complete")
    return setup_report


# ---- handle_install_thermal_brand -----------------------------------------

def handle_install_thermal_brand(params: dict) -> dict:
    """
    Install a thermal printer brand driver.
    Supported brands: "xprinter" (XP-80) and "sprt" (SPRT).

    XPrinter (XP-80):
      - Download binary from Dropbox, chmod +x, run it
      - Find PPD via lpinfo
      - lpadmin with USB URI

    SPRT:
      - Download zip from Dropbox, extract, run install.sh
      - Copy filters (rastertoprinter)
      - Find 80mmSeries.ppd, patch FullCut default
      - lpadmin with USB URI and -P flag
    """
    brand = params.get("brand", "").strip().lower()

    if brand not in ("xprinter", "sprt"):
        return {
            "status": "error",
            "message": f"Unsupported brand '{brand}'. Use 'xprinter' or 'sprt'.",
        }

    # Pass the full params dict to the installers so they can access usb_uri etc.
    if brand == "xprinter":
        return _install_xprinter(params)
    else:
        return _install_sprt(params)


def _install_xprinter(params=None) -> dict:
    """Install XPrinter XP-80 driver and set up the printer."""
    if params is None:
        params = {}
    report = {"status": "ok", "actions": [], "brand": "xprinter"}

    # Check if there's a specific USB URI from the thermal wizard detection
    requested_usb_uri = params.get("usb_uri", "").strip()

    # Remove existing printer first
    if is_printer_exists(XPRINTER_PRINTER_NAME):
        run_cmd(["lpadmin", "-x", XPRINTER_PRINTER_NAME])
        report["actions"].append(f"Removed existing printer '{XPRINTER_PRINTER_NAME}'")

    tmp_dir = tempfile.mkdtemp(prefix="xprinter_")
    try:
        # Download the installer binary
        installer_path = os.path.join(tmp_dir, "install-xp80")
        if not download_file(XPRINTER_DRIVER_URL, installer_path, "XPrinter XP-80 installer"):
            return {"status": "error", "message": "Failed to download XPrinter driver"}

        # Make executable and run
        os.chmod(installer_path, 0o755)
        rc, out, err = run_cmd(["bash", installer_path], timeout=120)
        if rc != 0:
            report["actions"].append(f"Installer returned code {rc}: {err}")
            log.warning("XPrinter installer exit code %d: %s", rc, err)
        else:
            report["actions"].append("XPrinter installer ran successfully")

        # Restart CUPS to pick up new PPDs/filters
        cups_restart()

        # Find USB URIs — prefer the one from wizard detection
        usb_uris = get_usb_uris()
        if requested_usb_uri and requested_usb_uri in usb_uris:
            usb_uri = requested_usb_uri
            report["actions"].append(f"Using detected USB URI: {usb_uri}")
        elif usb_uris:
            # Pick the first USB URI (most likely the XP-80)
            usb_uri = usb_uris[0]
            report["actions"].append(f"Found USB URI: {usb_uri}")
        else:
            report["actions"].append("No USB printer found -- will retry on plug-in")
            usb_uri = "usb://XPrinter/XP-80"  # Placeholder

        # Find PPD via lpinfo
        ppd = find_ppd_for_model("XP-80")
        if not ppd:
            # Broader search
            drivers = get_cups_ppd_drivers()
            for drv in drivers:
                if "xp-80" in drv["description"].lower() or "xprinter" in drv["description"].lower():
                    ppd = drv["ppd"]
                    break

        if ppd:
            rc, _, err = run_cmd(
                ["lpadmin", "-p", XPRINTER_PRINTER_NAME, "-E", "-v", usb_uri, "-m", ppd],
                timeout=30,
            )
            if rc == 0:
                report["actions"].append(f"Printer added with PPD: {ppd}")
            else:
                report["actions"].append(f"lpadmin with PPD failed: {err}")
        else:
            # Try with -m everywhere as fallback
            rc, _, err = run_cmd(
                ["lpadmin", "-p", XPRINTER_PRINTER_NAME, "-E", "-v", usb_uri, "-m", "everywhere"],
                timeout=30,
            )
            if rc == 0:
                report["actions"].append("Printer added with IPP Everywhere driver")
            else:
                report["actions"].append(f"IPP Everywhere also failed: {err}")

        # Enable, accept, set defaults
        run_cmd(["cupsenable", XPRINTER_PRINTER_NAME])
        run_cmd(["cupsaccept", XPRINTER_PRINTER_NAME])
        _set_thermal_cut_defaults(XPRINTER_PRINTER_NAME)

        report["actions"].append("XPrinter XP-80 setup complete")
        return report

    except Exception as exc:
        log.error("XPrinter install error: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _install_sprt(params=None) -> dict:
    """Install SPRT thermal printer driver and set up the printer."""
    if params is None:
        params = {}
    report = {"status": "ok", "actions": [], "brand": "sprt"}

    # Check if there's a specific USB URI from the thermal wizard detection
    requested_usb_uri = params.get("usb_uri", "").strip()

    # Remove existing printer first
    if is_printer_exists(SPRT_PRINTER_NAME):
        run_cmd(["lpadmin", "-x", SPRT_PRINTER_NAME])
        report["actions"].append(f"Removed existing printer '{SPRT_PRINTER_NAME}'")

    tmp_dir = tempfile.mkdtemp(prefix="sprt_")
    try:
        # Download the driver zip
        zip_path = os.path.join(tmp_dir, "sprt_driver.zip")
        if not download_file(SPRT_DRIVER_URL, zip_path, "SPRT driver zip"):
            return {"status": "error", "message": "Failed to download SPRT driver"}

        # Extract
        extract_dir = os.path.join(tmp_dir, "sprt_extracted")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            report["actions"].append("Extracted SPRT driver archive")
        except zipfile.BadZipFile:
            # The Dropbox download might not be a zip -- try running it directly
            os.chmod(zip_path, 0o755)
            rc, out, err = run_cmd(["bash", zip_path], timeout=120)
            report["actions"].append(f"Ran downloaded file directly: rc={rc}")
            extract_dir = tmp_dir

        # Find and run install.sh
        install_sh = None
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.lower() == "install.sh":
                    install_sh = os.path.join(root, f)
                    break
            if install_sh:
                break

        if install_sh:
            os.chmod(install_sh, 0o755)
            rc, out, err = run_cmd(["bash", install_sh], timeout=120)
            if rc == 0:
                report["actions"].append("install.sh ran successfully")
            else:
                report["actions"].append(f"install.sh returned {rc}: {err}")
                log.warning("install.sh exit code %d: %s", rc, err)
        else:
            report["actions"].append("No install.sh found -- continuing manually")
            log.warning("No install.sh found in SPRT driver archive")

        # Copy rastertoprinter filter if present
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if "rastertoprinter" in f.lower():
                    src = os.path.join(root, f)
                    dst = "/usr/lib/cups/filter/rastertoprinter"
                    try:
                        shutil.copy2(src, dst)
                        os.chmod(dst, 0o755)
                        report["actions"].append(f"Copied filter: {src} -> {dst}")
                    except Exception as exc:
                        report["actions"].append(f"Failed to copy filter: {exc}")
                    break

        # Find the PPD file
        ppd_src = None
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.endswith(".ppd") and "80mm" in f.lower():
                    ppd_src = os.path.join(root, f)
                    break
            if ppd_src:
                break

        # If not found in archive, check if install.sh placed it
        if not ppd_src and os.path.isfile(SPRT_PPD_DEST):
            ppd_src = SPRT_PPD_DEST

        # If still not found, do a broader search
        if not ppd_src:
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.endswith(".ppd"):
                        ppd_src = os.path.join(root, f)
                        break
                if ppd_src:
                    break

        if ppd_src:
            # Copy PPD to CUPS model directory
            ppd_dir = os.path.dirname(SPRT_PPD_DEST)
            os.makedirs(ppd_dir, exist_ok=True)
            try:
                shutil.copy2(ppd_src, SPRT_PPD_DEST)
                report["actions"].append(f"Installed PPD: {SPRT_PPD_DEST}")
            except Exception as exc:
                report["actions"].append(f"Failed to copy PPD: {exc}")

            # Patch FullCut default to PartialCut in PPD
            try:
                with open(SPRT_PPD_DEST, "r") as fh:
                    ppd_content = fh.read()
                # Replace FullCut default with PartialCut
                patched = ppd_content.replace(
                    "*DefaultFullCut: True",
                    "*DefaultFullCut: False"
                )
                patched = patched.replace(
                    "*DefaultFullCut: full",
                    "*DefaultFullCut: partial"
                )
                # Also patch DocumentCut if present
                patched = patched.replace(
                    "*DefaultDocumentCut: True",
                    "*DefaultDocumentCut: False"
                )
                if patched != ppd_content:
                    with open(SPRT_PPD_DEST, "w") as fh:
                        fh.write(patched)
                    report["actions"].append("Patched PPD: FullCut -> PartialCut default")
            except Exception as exc:
                report["actions"].append(f"PPD patch failed (non-fatal): {exc}")

        # Restart CUPS to pick up new PPDs/filters
        cups_restart()

        # Find USB URI — prefer the one from wizard detection
        usb_uris = get_usb_uris()
        if requested_usb_uri and requested_usb_uri in usb_uris:
            usb_uri = requested_usb_uri
            report["actions"].append(f"Using detected USB URI: {usb_uri}")
        elif usb_uris:
            usb_uri = usb_uris[0]
            report["actions"].append(f"Found USB URI: {usb_uri}")
        else:
            report["actions"].append("No USB printer found -- will retry on plug-in")
            usb_uri = "usb://SPRT/Printer"

        # Set up printer with -P flag (direct PPD path)
        if os.path.isfile(SPRT_PPD_DEST):
            rc, _, err = run_cmd(
                [
                    "lpadmin", "-p", SPRT_PRINTER_NAME, "-E",
                    "-v", usb_uri,
                    "-P", SPRT_PPD_DEST,
                ],
                timeout=30,
            )
            if rc == 0:
                report["actions"].append(f"Printer added with PPD: {SPRT_PPD_DEST}")
            else:
                report["actions"].append(f"lpadmin -P failed: {err}")
        else:
            # Fallback: try -m everywhere
            rc, _, err = run_cmd(
                [
                    "lpadmin", "-p", SPRT_PRINTER_NAME, "-E",
                    "-v", usb_uri, "-m", "everywhere",
                ],
                timeout=30,
            )
            if rc == 0:
                report["actions"].append("Printer added with IPP Everywhere (fallback)")
            else:
                report["actions"].append(f"All setup methods failed: {err}")

        # Enable, accept, set thermal defaults
        run_cmd(["cupsenable", SPRT_PRINTER_NAME])
        run_cmd(["cupsaccept", SPRT_PRINTER_NAME])
        _set_thermal_cut_defaults(SPRT_PRINTER_NAME)

        report["actions"].append("SPRT printer setup complete")
        return report

    except Exception as exc:
        log.error("SPRT install error: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---- handle_repair_printer (repair a SPECIFIC printer) --------------------

def handle_repair_printer(params: dict) -> dict:
    """
    Repair a SPECIFIC printer by name:
      1. Enable it via cupsenable + cupsaccept
      2. Clear its job queue (cancel -a NAME)
      3. If it's disabled, re-enable it
      4. Verify it's now accepting jobs

    This is different from handle_fix (smart diagnostic) which runs a
    general check on all printers.  The GUI "Repair" button calls this.
    """
    name = params.get("name", "").strip()
    if not name:
        return {"status": "error", "message": "Printer name is required"}

    actions = []

    # Step 1: Check if printer exists
    if not is_printer_exists(name):
        return {"status": "error", "message": f"Printer '{name}' does not exist in CUPS"}

    # Step 2: Enable the printer (cupsenable + cupsaccept)
    rc1, _, err1 = run_cmd(["cupsenable", name])
    if rc1 == 0:
        actions.append(f"Enabled printer '{name}'")
        log.info("Enabled printer: %s", name)
    else:
        actions.append(f"cupsenable failed for '{name}': {err1}")
        log.warning("cupsenable failed for %s: %s", name, err1)

    rc2, _, err2 = run_cmd(["cupsaccept", name])
    if rc2 == 0:
        actions.append(f"Printer '{name}' now accepting jobs")
        log.info("cupsaccept for %s", name)
    else:
        actions.append(f"cupsaccept failed for '{name}': {err2}")
        log.warning("cupsaccept failed for %s: %s", name, err2)

    # Step 3: Clear stuck jobs for this printer only
    rc3, _, err3 = run_cmd(["cancel", "-a", name])
    if rc3 == 0:
        actions.append(f"Cleared all jobs on '{name}'")
        log.info("Cleared jobs on %s", name)
    else:
        actions.append(f"No stuck jobs to clear on '{name}'")

    # Step 4: Verify printer state
    rc4, out4, _ = run_cmd(["lpstat", "-p", name])
    if rc4 == 0 and out4:
        if "enabled" in out4.lower():
            actions.append(f"Printer '{name}' is now ENABLED and ready")
        elif "disabled" in out4.lower():
            # Force re-enable
            run_cmd(["cupsenable", name])
            run_cmd(["cupsaccept", name])
            actions.append(f"Force re-enabled printer '{name}'")
            log.info("Force re-enabled %s", name)
    else:
        actions.append(f"Could not verify state of '{name}'")

    # Step 5: Restart CUPS if printer still not working
    # This is a safety net — only if the above didn't help
    rc5, out5, _ = run_cmd(["lpstat", "-p", name])
    if rc5 == 0 and "disabled" in out5.lower():
        log.warning("Printer %s still disabled after enable — restarting CUPS", name)
        cups_restart()
        time.sleep(2)
        run_cmd(["cupsenable", name])
        run_cmd(["cupsaccept", name])
        actions.append("Restarted CUPS and re-enabled printer")

    log.info("Repair complete for printer '%s'", name)
    return {"status": "ok", "actions": actions, "printer": name}


# ---- handle_define_driver (install PPD driver for a printer) ---------------

def handle_define_driver(params: dict) -> dict:
    """
    Define/install a driver (PPD) for an existing printer.
    Params:
      - name: printer name
      - model: model name to search for PPD
    Steps:
      1. Search for matching PPD via lpinfo -m
      2. Apply the PPD to the printer with lpadmin -p NAME -m PPD
      3. Enable and accept
    """
    name = params.get("name", "").strip()
    model = params.get("model", "").strip()

    if not name:
        return {"status": "error", "message": "Printer name is required"}

    if not is_printer_exists(name):
        return {"status": "error", "message": f"Printer '{name}' does not exist in CUPS"}

    actions = []
    search_model = model or name

    # Step 1: Find matching PPD
    log.info("Searching PPD for printer '%s' model '%s'", name, search_model)
    ppd = find_ppd_for_model(search_model)

    if not ppd:
        # Try IPP Everywhere as fallback
        log.info("No specific PPD found — trying IPP Everywhere")
        rc, _, err = run_cmd(
            ["lpadmin", "-p", name, "-m", "everywhere"],
            timeout=30,
        )
        if rc == 0:
            actions.append(f"Set IPP Everywhere driver for '{name}'")
        else:
            # Try raw driver
            rc2, _, err2 = run_cmd(
                ["lpadmin", "-p", name, "-m", "raw"],
                timeout=30,
            )
            if rc2 == 0:
                actions.append(f"Set raw driver for '{name}' (no PPD)")
            else:
                return {
                    "status": "error",
                    "message": f"No driver found for '{search_model}' and fallback drivers also failed",
                    "actions": actions,
                }
    else:
        # Step 2: Apply the PPD
        log.info("Found PPD: %s — applying to %s", ppd, name)
        rc, _, err = run_cmd(
            ["lpadmin", "-p", name, "-m", ppd],
            timeout=30,
        )
        if rc == 0:
            actions.append(f"Installed driver PPD: {ppd}")
        else:
            return {
                "status": "error",
                "message": f"Failed to install PPD '{ppd}': {err}",
                "actions": actions,
            }

    # Step 3: Enable and accept
    run_cmd(["cupsenable", name])
    run_cmd(["cupsaccept", name])
    actions.append(f"Printer '{name}' enabled and accepting jobs")

    return {"status": "ok", "actions": actions, "printer": name}


# ---- handle_remove_printer ------------------------------------------------

def handle_remove_printer(params: dict) -> dict:
    """
    Remove a printer from CUPS:
      1. Cancel all its jobs
      2. Delete it with lpadmin -x

    Note: We do NOT cupsdisable before removal, because if lpadmin -x
    fails, the printer would be left in a disabled state.  Cancelling
    jobs and removing directly is safer.
    """
    name = params.get("name", "").strip()
    if not name:
        return {"status": "error", "message": "Printer name is required"}

    actions = []

    # Cancel all jobs
    rc, _, err = run_cmd(["cancel", "-a", name])
    if rc == 0:
        actions.append(f"Cancelled all jobs on '{name}'")
    else:
        actions.append(f"No jobs to cancel (or cancel failed): {err}")

    # Remove printer directly (no cupsdisable first)
    rc, _, err = run_cmd(["lpadmin", "-x", name])
    if rc == 0:
        actions.append(f"Removed printer '{name}' successfully")
        log.info("Printer '%s' removed", name)
    else:
        return {"status": "error", "message": f"Failed to remove printer: {err}", "actions": actions}

    return {"status": "ok", "actions": actions}


# ---- handle_quick_fix_spooler ---------------------------------------------

def handle_quick_fix_spooler(params: dict) -> dict:
    """
    Quick fix for a stuck spooler.
    Safer approach:
      1. Restart CUPS (not stop -- so it stays running even if cleanup fails)
      2. Cancel all stuck jobs via cancel -a
      3. Ensure CUPS is running
      4. Only clear the spool directory as a last resort if the above
         didn't resolve the issue
    """
    actions = []

    # Step 1: Restart CUPS (safer than stopping -- keeps it running)
    log.info("Quick fix: restarting CUPS")
    if cups_restart():
        actions.append("CUPS restarted")
    else:
        actions.append("CUPS restart failed -- will try to continue")

    # Step 2: Cancel only STUCK jobs (held/error state), not ALL jobs
    # Using cancel -a -x removes ALL completed jobs too which is too aggressive
    # Instead, find held/stuck jobs and cancel only those
    rc, out, _ = run_cmd(["lpstat", "-o"])
    if rc == 0 and out:
        stuck_count = 0
        for line in out.splitlines():
            parts = line.strip().split()
            if parts:
                # Each line: "printer-name-123  user  size  date"
                job_id = parts[0]
                # Cancel individual stuck jobs
                rc_cancel, _, _ = run_cmd(["cancel", job_id])
                if rc_cancel == 0:
                    stuck_count += 1
        if stuck_count > 0:
            actions.append(f"Cancelled {stuck_count} stuck print job(s)")
        else:
            actions.append("No stuck print jobs found")
    else:
        actions.append("No print jobs in queue")

    # Step 3: Ensure CUPS is running (but do NOT cancel all jobs)
    if not cups_is_running():
        log.warning("CUPS not running after restart -- attempting start")
        # Try starting CUPS multiple times before resorting to spool clear
        started = False
        for attempt in range(3):
            log.info("CUPS start attempt %d/3", attempt + 1)
            if cups_start():
                started = True
                actions.append("CUPS started")
                break
            time.sleep(2)

        if not started:
            # CUPS won't start -- last resort: clear ONLY temp files (cNNNNNN),
            # NOT data files (dNNNNNN) which are active print jobs
            actions.append("CUPS failed to start -- cleaning spool temp files")
            spool_dir = "/var/spool/cups"
            try:
                cleared = 0
                for entry in os.listdir(spool_dir):
                    # Only clear control/temp files (start with 'c'), NOT data files (start with 'd')
                    if entry.startswith('c') and not entry.startswith('d'):
                        path = os.path.join(spool_dir, entry)
                        try:
                            if os.path.isfile(path) or os.path.islink(path):
                                os.remove(path)
                                cleared += 1
                        except Exception as exc:
                            log.warning("Could not remove %s: %s", path, exc)
                actions.append(f"Cleared {cleared} spool temp files (preserved active jobs)")
            except FileNotFoundError:
                actions.append(f"Spool directory {spool_dir} does not exist (ok)")
            except Exception as exc:
                actions.append(f"Error clearing spool: {exc}")

            # Try to start CUPS again after clearing spool temps
            time.sleep(1)
            if cups_start():
                actions.append("CUPS started after spool temp clear")
            else:
                return {
                    "status": "error",
                    "message": "Failed to start CUPS even after clearing spool",
                    "actions": actions,
                }

    log.info("Quick fix spooler complete")
    return {"status": "ok", "actions": actions}


# ---- handle_detect_usb_printers -------------------------------------------

def handle_detect_usb_printers(params: dict) -> dict:
    """
    Detect USB printers connected to the system.
    Uses multiple detection methods for thoroughness:
      1. lpinfo -v for USB URIs (CUPS-known devices)
      2. lsusb for USB device descriptions (recently plugged devices)
      3. /dev/usb/lp* device nodes (kernel-level USB printer devices)
      4. udevadm info for usb_printer_id on each /dev/usb/lp* device

    Returns list of {uri, full_uri, description, type, device, bus_info}.
    """
    printers = []
    seen_uris = set()

    # --- Method 1: lpinfo -v for USB URIs ---
    backends = get_cups_backends()
    usb_entries = [b for b in backends if b.startswith("usb://")]

    # Get lsusb output for descriptions
    rc, lsusb_out, _ = run_cmd(["lsusb"])
    lsusb_lines = lsusb_out.splitlines() if rc == 0 and lsusb_out else []

    for entry in usb_entries:
        # Parse USB URI: usb://Vendor/Model?serial=XXX
        uri = entry.split(":", 1)[1].strip() if ":" in entry else entry

        # Avoid duplicates
        if uri in seen_uris:
            continue
        seen_uris.add(uri)

        # Try to match with lsusb description
        description = "USB Printer"
        uri_lower = uri.lower()
        vendor_match = re.search(r'usb://([^/?]+)', uri)
        if vendor_match:
            vendor = vendor_match.group(1).lower()
            for line in lsusb_lines:
                line_lower = line.lower()
                if vendor in line_lower:
                    description = line.strip()
                    break

        printers.append({
            "uri": uri,
            "full_uri": entry,
            "description": description,
            "type": "usb",
            "device": None,
            "source": "lpinfo",
        })

    # --- Method 2: lsusb parsing for printer-class devices ---
    # USB printer class is 07 (USB_CLASS_PRINTER)
    rc, lsusb_v_out, _ = run_cmd(
        ["lsusb", "-v", "-d", ":0701,"],
        timeout=10,
    )
    if rc == 0 and lsusb_v_out:
        # Parse verbose lsusb for printer devices
        current_device = {}
        for line in lsusb_v_out.splitlines():
            # New device header: "Bus 001 Device 005: ID 0416:5011 ..."
            m = re.search(r'Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s+(.*)', line)
            if m:
                if current_device.get("bus"):
                    # Store previous device if it had printer info
                    _add_lsusb_printer(current_device, printers, seen_uris, lsusb_lines)
                current_device = {
                    "bus": m.group(1),
                    "dev": m.group(2),
                    "vid": m.group(3),
                    "pid": m.group(4),
                    "desc": m.group(5).strip(),
                }
            # Look for iProduct or iManufacturer
            if current_device.get("bus"):
                m_prod = re.search(r'iProduct\s+\d+\s+(.*)', line)
                if m_prod:
                    current_device["product"] = m_prod.group(1).strip()
                m_mfg = re.search(r'iManufacturer\s+\d+\s+(.*)', line)
                if m_mfg:
                    current_device["manufacturer"] = m_mfg.group(1).strip()
                m_serial = re.search(r'iSerial\s+\d+\s+(.*)', line)
                if m_serial:
                    current_device["serial"] = m_serial.group(1).strip()

        # Don't forget the last device
        if current_device.get("bus"):
            _add_lsusb_printer(current_device, printers, seen_uris, lsusb_lines)

    # --- Method 3: /dev/usb/lp* device nodes ---
    lp_glob = "/dev/usb/lp*"
    import glob as _glob
    lp_devices = _glob.glob(lp_glob)

    for lp_dev in lp_devices:
        # Check if this device is already covered by a known URI
        # /dev/usb/lp0 typically maps to usb://Vendor/Model?serial=...
        description = f"USB printer device ({lp_dev})"
        bus_info = None

        # Try to get usb_printer_id via udevadm
        rc_udev, udev_out, _ = run_cmd(
            ["udevadm", "info", "--query=property", "--name", lp_dev],
            timeout=5,
        )
        vendor_name = None
        model_name = None
        serial = None
        usb_vid = None
        usb_pid = None

        if rc_udev == 0 and udev_out:
            for prop_line in udev_out.splitlines():
                if "=" in prop_line:
                    key, _, val = prop_line.partition("=")
                    if key == "ID_VENDOR_FROM_DATABASE":
                        vendor_name = val.strip()
                    elif key == "ID_MODEL_FROM_DATABASE":
                        model_name = val.strip()
                    elif key == "ID_SERIAL_SHORT":
                        serial = val.strip()
                    elif key == "ID_VENDOR_ID":
                        usb_vid = val.strip()
                    elif key == "ID_MODEL_ID":
                        usb_pid = val.strip()
                    elif key == "ID_BUS":
                        bus_info = val.strip()

        # Try usb_printer_id for IEEE 1284 device ID
        rc_pid, pid_out, _ = run_cmd(
            ["usb_printerid", lp_dev],
            timeout=5,
        )
        ieee_mfg = None
        ieee_mdl = None
        ieee_serial = None
        if rc_pid == 0 and pid_out:
            m_mfg = re.search(r'MFG:([^;]+)', pid_out)
            if m_mfg:
                ieee_mfg = m_mfg.group(1).strip()
            m_mdl = re.search(r'MDL:([^;]+)', pid_out)
            if m_mdl:
                ieee_mdl = m_mdl.group(1).strip()
            m_srl = re.search(r'SERN:([^;]+)', pid_out)
            if m_srl:
                ieee_serial = m_srl.group(1).strip()

        # Build a USB URI from collected info
        mfg = ieee_mfg or vendor_name or "Unknown"
        mdl = ieee_mdl or model_name or "Printer"
        ser = ieee_serial or serial or ""

        # Construct CUPS-style USB URI
        usb_uri = f"usb://{mfg}/{mdl}"
        if ser:
            usb_uri += f"?serial={ser}"

        # Check if already known
        if usb_uri in seen_uris:
            continue
        seen_uris.add(usb_uri)

        # Build description
        if vendor_name and model_name:
            description = f"{vendor_name} {model_name}"
        elif ieee_mfg and ieee_mdl:
            description = f"{ieee_mfg} {ieee_mdl}"
        else:
            # Try to match lsusb line
            if usb_vid and usb_pid:
                for line in lsusb_lines:
                    if usb_vid in line.lower() and usb_pid in line.lower():
                        description = line.strip()
                        break

        printers.append({
            "uri": usb_uri,
            "full_uri": f"usb://{mfg}/{mdl}" + (f"?serial={ser}" if ser else ""),
            "description": description,
            "type": "usb",
            "device": lp_dev,
            "source": "dev-node",
            "bus_info": bus_info,
        })

    # --- Method 4: Thorough scan of usb:// URIs from lpinfo ---
    # Re-check lpinfo in case new devices appeared
    rc2, lpinfo_out2, _ = run_cmd(["lpinfo", "-v", "--timeout", "5"])
    if rc2 == 0 and lpinfo_out2:
        for line in lpinfo_out2.splitlines():
            line = line.strip()
            if line.startswith("usb://"):
                uri = line.split(":", 1)[1].strip() if ":" in line else line
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    description = "USB Printer"
                    # Try lsusb match
                    vendor_match = re.search(r'usb://([^/?]+)', uri)
                    if vendor_match:
                        vendor = vendor_match.group(1).lower()
                        for ls_line in lsusb_lines:
                            if vendor in ls_line.lower():
                                description = ls_line.strip()
                                break
                    printers.append({
                        "uri": uri,
                        "full_uri": line,
                        "description": description,
                        "type": "usb",
                        "device": None,
                        "source": "lpinfo-refresh",
                    })

    log.info("Detected %d USB printers", len(printers))
    # Return error status when no USB printers found so the GUI thermal
    # wizard can correctly show "not detected" instead of "detected".
    if not printers:
        return {"status": "error", "message": "No USB printers detected", "printers": []}
    return {"status": "ok", "printers": printers}


def _add_lsusb_printer(device_info: dict, printers: list, seen_uris: set,
                        lsusb_lines: list):
    """
    Helper for handle_detect_usb_printers: add a printer found via lsusb -v
    to the printers list if its URI is not already known.
    """
    vid = device_info.get("vid", "")
    pid = device_info.get("pid", "")
    mfg = device_info.get("manufacturer", "")
    mdl = device_info.get("product", "")
    serial = device_info.get("serial", "")

    if not mfg:
        mfg = "Unknown"
    if not mdl:
        mdl = "Printer"

    # Build a CUPS-style USB URI
    usb_uri = f"usb://{mfg}/{mdl}"
    if serial:
        usb_uri += f"?serial={serial}"

    if usb_uri in seen_uris:
        return
    seen_uris.add(usb_uri)

    # Build description from lsusb short listing
    description = device_info.get("desc", "")
    if not description and vid and pid:
        for line in lsusb_lines:
            if vid in line and pid in line:
                description = line.strip()
                break
    if not description:
        description = f"{mfg} {mdl}"

    printers.append({
        "uri": usb_uri,
        "full_uri": usb_uri,
        "description": description,
        "type": "usb",
        "device": None,
        "source": "lsusb",
        "bus_info": f"Bus {device_info.get('bus', '?')} Device {device_info.get('dev', '?')}",
    })


# ---- handle_discover_printers (all installed printers with consistent format) ----

def handle_discover_printers(params: dict) -> dict:
    """
    Discover all installed printers using lpstat -p.
    Returns a consistent data format where each printer entry has:
      - name (string): the CUPS printer queue name
      - state (string): "enabled" or "disabled"
      - device (string): the device URI
      - jobs (int): number of queued jobs

    Also includes USB printers detected via detect_usb_printers for
    devices that may not yet be installed in CUPS.
    """
    printers = []
    seen_names = set()

    # --- Primary source: lpstat -p for all installed printers ---
    rc, out, _ = run_cmd(["lpstat", "-p"])
    if rc == 0 and out:
        for line in out.splitlines():
            # Format: "printer NAME enabled since ..." or "printer NAME disabled since ..."
            m = re.match(r'printer\s+(\S+)\s+(enabled|disabled)', line, re.IGNORECASE)
            if m:
                name = m.group(1)
                state = m.group(2).lower()
                seen_names.add(name)

                device_uri = _get_printer_device_uri(name) or ""
                job_count = _get_printer_job_count(name)

                printers.append({
                    "name": name,
                    "state": state,
                    "device": device_uri,
                    "jobs": job_count,
                })

    # --- Supplement: also detect USB printers not yet installed ---
    usb_result = handle_detect_usb_printers(params)
    if usb_result.get("status") == "ok":
        for usb_printer in usb_result.get("printers", []):
            uri = usb_printer.get("uri", "")
            # Only add if this USB device is NOT already in the installed list
            already_known = any(
                p.get("device", "").startswith("usb://") and uri in p.get("device", "")
                for p in printers
            )
            if not already_known and uri:
                printers.append({
                    "name": usb_printer.get("description", "Unknown USB Printer"),
                    "state": "not-installed",
                    "device": usb_printer.get("full_uri", f"usb://{uri}"),
                    "jobs": 0,
                })

    # --- Supplement: network printers from quick scan ---
    scan_result = handle_scan(params)
    if scan_result.get("status") == "ok":
        for net_printer in scan_result.get("printers", []):
            uri = net_printer.get("uri", "")
            net_type = net_printer.get("type", "network")
            if net_type == "network" and uri:
                already_known = any(
                    uri in p.get("device", "") for p in printers
                )
                if not already_known:
                    printers.append({
                        "name": net_printer.get("ip", uri),
                        "state": "network",
                        "device": net_printer.get("full_uri", uri),
                        "jobs": 0,
                    })

    log.info("Discovered %d printers total", len(printers))
    return {"status": "ok", "printers": printers}


# ---- handle_list_installed_printers (new handler for GUI) ------------------

def handle_list_installed_printers(params: dict) -> dict:
    """
    List ALL installed printers with their status, device URI, and job count.
    Uses lpstat -p -d for comprehensive info.
    This is what the GUI needs for Repair, Status, and Remove screens.

    Returns: {status: "ok", printers: [{name, state, device, jobs, is_default}, ...]}
    """
    printers = []
    default_printer = _get_default_printer()

    # Get all printers via lpstat -p
    rc, out, _ = run_cmd(["lpstat", "-p"])
    if rc != 0 or not out:
        return {"status": "ok", "printers": [], "default": None}

    for line in out.splitlines():
        # Format: "printer NAME enabled since ..." or "printer NAME disabled since ..."
        m = re.match(r'printer\s+(\S+)\s+(enabled|disabled)', line, re.IGNORECASE)
        if m:
            name = m.group(1)
            state = m.group(2).lower()
            device_uri = _get_printer_device_uri(name) or ""
            job_count = _get_printer_job_count(name)
            is_default = (name == default_printer)

            printers.append({
                "name": name,
                "state": state,
                "device": device_uri,
                "jobs": job_count,
                "is_default": is_default,
            })

    log.info("Listed %d installed printers (default: %s)", len(printers), default_printer)
    return {"status": "ok", "printers": printers, "default": default_printer}


# ---- handle_clear_jobs ----------------------------------------------------

def handle_clear_jobs(params: dict) -> dict:
    """
    Clear print jobs for a specific printer or all printers.
    Params: name (optional) -- if omitted, clears all jobs.
    """
    name = params.get("name", "").strip()

    if name:
        rc, out, err = run_cmd(["cancel", "-a", name])
        if rc == 0:
            log.info("Cleared all jobs on '%s'", name)
            return {"status": "ok", "message": f"All jobs cleared on '{name}'"}
        else:
            return {"status": "error", "message": f"Failed to clear jobs: {err}"}
    else:
        rc, out, err = run_cmd(["cancel", "-a"])
        if rc == 0:
            log.info("Cleared all print jobs")
            return {"status": "ok", "message": "All print jobs cleared"}
        else:
            return {"status": "error", "message": f"Failed to clear all jobs: {err}"}


# ---- handle_test_print ----------------------------------------------------

def handle_test_print(params: dict) -> dict:
    """
    Send a test page to the specified printer.
    Uses CUPS test page via lp command.
    """
    name = params.get("name", "").strip()

    if not name:
        return {"status": "error", "message": "Printer name is required"}

    # Check printer exists
    if not is_printer_exists(name):
        return {"status": "error", "message": f"Printer '{name}' does not exist"}

    # Try to print the CUPS test page
    test_page = "/usr/share/cups/data/testprint"
    if not os.path.isfile(test_page):
        # Generate a simple test page
        tmp_dir = tempfile.mkdtemp(prefix="testprint_")
        test_page = os.path.join(tmp_dir, "test.txt")
        with open(test_page, "w") as fh:
            fh.write("=" * 60 + "\n")
            fh.write("  IT Aman Printer Daemon -- Test Page\n")
            fh.write(f"  Printer: {name}\n")
            fh.write(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            fh.write(f"  Version: {VERSION}\n")
            fh.write("=" * 60 + "\n")

    rc, out, err = run_cmd(
        ["lp", "-d", name, "-o", "fit-to-page", test_page],
        timeout=30,
    )

    if rc == 0:
        # Extract job ID from output
        job_id = out.strip() if out else "unknown"
        log.info("Test print sent to '%s': %s", name, job_id)
        return {"status": "ok", "message": f"Test page sent to '{name}'", "job_id": job_id}
    else:
        return {"status": "error", "message": f"Test print failed: {err}"}


# ---- handle_update_all (self-update from public GitHub) -------------------

def handle_update_all(params: dict) -> dict:
    """
    Check for and apply updates from the public GitHub repository.
    NO token needed -- repo is public, uses raw.githubusercontent.com URLs.

    Update process (with Ed25519 signature verification):
      1. Download version.json from raw.githubusercontent.com
      2. Compare versions
      3. Download update_manifest.json, verify Ed25519 signature
      4. Download new files (SHA256 verified), replace, restart daemon

    To release an update:
      1. Edit files locally
      2. Change VERSION in daemon.py
      3. Change version in version.json
      4. Run: python3 generate_manifest.py
      5. git add -A && git commit -m "v3.8" && git push
    """
    report = {"status": "ok", "actions": []}

    # --- Step 1: Fetch remote version ---
    version_url = f"{RAW_BASE}/version.json"
    log.info("Checking for updates at %s", version_url)
    version_text = download_text(version_url)
    if not version_text:
        return {"status": "error", "message": "Failed to fetch version.json from GitHub"}

    try:
        remote_info = json.loads(version_text)
    except json.JSONDecodeError as exc:
        return {"status": "error", "message": f"Invalid version.json: {exc}"}

    remote_version = remote_info.get("version", "")
    if not remote_version:
        return {"status": "error", "message": "version.json missing 'version' field"}

    report["actions"].append(f"Remote version: {remote_version}, Local version: {VERSION}")

    # Compare versions
    if _compare_versions(remote_version, VERSION) <= 0:
        report["actions"].append("Already up to date")
        return report

    log.info("Update available: %s -> %s", VERSION, remote_version)

    # --- Step 2: Fetch update manifest ---
    manifest_url = f"{RAW_BASE}/update_manifest.json"
    manifest_text = download_text(manifest_url)
    if not manifest_text:
        return {"status": "error", "message": "Failed to fetch update_manifest.json"}

    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        return {"status": "error", "message": f"Invalid update_manifest.json: {exc}"}

    # --- Step 3: Verify Ed25519 signature ---
    signature_b64 = manifest.get("signature", "")
    public_key_b64 = manifest.get("public_key", "")
    files_list = manifest.get("files", [])

    if not signature_b64 or not public_key_b64:
        return {"status": "error", "message": "Update manifest missing signature or public_key -- update rejected for security"}

    if not files_list:
        return {"status": "error", "message": "Update manifest has no files to update"}

    try:
        sig_valid = _verify_ed25519_signature(
            public_key_b64, signature_b64, files_list
        )
        if not sig_valid:
            return {"status": "error", "message": "Ed25519 signature verification FAILED -- update rejected"}
        report["actions"].append("Ed25519 signature verified")
    except Exception as exc:
        return {"status": "error", "message": f"Signature verification error: {exc}"}

    # --- Step 4: Download and replace files ---
    install_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(install_dir)  # /opt/it-aman
    backup_dir = base_dir + ".backup"

    # Create backup of current files
    try:
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.copytree(base_dir, backup_dir)
        report["actions"].append(f"Backed up current files to {backup_dir}")
    except Exception as exc:
        return {"status": "error", "message": f"Failed to create backup: {exc}"}

    # Download each file
    updated_files = []
    for file_info in files_list:
        remote_path = file_info.get("path", "")
        expected_sha256 = file_info.get("sha256", "")
        if not remote_path:
            continue

        download_url = f"{RAW_BASE}/{remote_path}"
        dest_path = os.path.join(base_dir, remote_path)

        log.info("Downloading update: %s -> %s", download_url, dest_path)

        tmp_dest = dest_path + ".new"
        if not download_file(download_url, tmp_dest, remote_path):
            report["actions"].append(f"Failed to download {remote_path}")
            continue

        # Verify SHA256 if provided
        if expected_sha256:
            actual_sha256 = _sha256_file(tmp_dest)
            if actual_sha256 != expected_sha256:
                log.error(
                    "SHA256 mismatch for %s: expected %s, got %s",
                    remote_path, expected_sha256, actual_sha256,
                )
                os.remove(tmp_dest)
                report["actions"].append(f"SHA256 mismatch for {remote_path} -- skipped")
                continue

        # Replace the file
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            os.replace(tmp_dest, dest_path)
            updated_files.append(remote_path)
            report["actions"].append(f"Updated: {remote_path}")
        except Exception as exc:
            log.error("Failed to replace %s: %s", remote_path, exc)
            report["actions"].append(f"Failed to replace {remote_path}: {exc}")
            if os.path.isfile(tmp_dest):
                os.remove(tmp_dest)

    if not updated_files:
        # Restore backup since nothing was updated
        try:
            shutil.rmtree(base_dir)
            shutil.copytree(backup_dir, base_dir)
        except Exception:
            pass
        return {"status": "error", "message": "No files were successfully updated", "actions": report["actions"]}

    # --- Step 5: Update config with new version ---
    cfg = load_config()
    cfg["version"] = remote_version
    save_config(cfg)

    # --- Step 6: Restart daemon ---
    report["actions"].append(f"Updated {len(updated_files)} file(s)")
    report["actions"].append("Daemon will restart to apply updates")
    report["new_version"] = remote_version

    # Schedule restart in a separate thread so we can send the response first
    def _restart_daemon():
        time.sleep(2)
        log.info("Restarting daemon after update...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_restart_daemon, daemon=True).start()

    return report


def _compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    Returns: 1 if v1 > v2, 0 if equal, -1 if v1 < v2.
    """
    def _parse(v):
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return parts

    p1 = _parse(v1)
    p2 = _parse(v2)
    # Pad to same length
    maxlen = max(len(p1), len(p2))
    p1.extend([0] * (maxlen - len(p1)))
    p2.extend([0] * (maxlen - len(p2)))

    for a, b in zip(p1, p2):
        if a > b:
            return 1
        elif a < b:
            return -1
    return 0


def _sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _verify_ed25519_signature(public_key_b64: str, signature_b64: str, files_list: list) -> bool:
    """
    Verify the Ed25519 signature of the update manifest's file list.
    Uses the PyNaCl library (nacl) if available, otherwise falls back
    to a manual verification attempt.
    """
    try:
        import nacl.signing
        import nacl.encoding
    except ImportError:
        log.warning(
            "PyNaCl not installed -- attempting Ed25519 verification with openssl"
        )
        return _verify_ed25519_openssl(public_key_b64, signature_b64, files_list)

    try:
        # Decode the public key
        public_key_bytes = __import__("base64").b64decode(public_key_b64)
        verify_key = nacl.signing.VerifyKey(public_key_bytes)

        # The signed data is the canonical JSON of the files list
        data = json.dumps(files_list, sort_keys=True, separators=(",", ":")).encode("utf-8")

        # Decode and verify signature
        sig_bytes = __import__("base64").b64decode(signature_b64)
        verify_key.verify(data, sig_bytes)
        log.info("Ed25519 signature verified (PyNaCl)")
        return True
    except Exception as exc:
        log.error("Ed25519 verification failed (PyNaCl): %s", exc)
        return False


def _verify_ed25519_openssl(public_key_b64: str, signature_b64: str, files_list: list) -> bool:
    """
    Fallback: verify Ed25519 signature using the openssl CLI.
    """
    import base64

    tmp_dir = tempfile.mkdtemp(prefix="ed25519_")
    try:
        # Write public key in DER format, then convert to PEM
        pub_der = os.path.join(tmp_dir, "pub.der")
        pub_pem = os.path.join(tmp_dir, "pub.pem")
        sig_file = os.path.join(tmp_dir, "sig.bin")
        data_file = os.path.join(tmp_dir, "data.bin")

        with open(pub_der, "wb") as fh:
            fh.write(base64.b64decode(public_key_b64))
        with open(sig_file, "wb") as fh:
            fh.write(base64.b64decode(signature_b64))
        with open(data_file, "wb") as fh:
            fh.write(json.dumps(files_list, sort_keys=True, separators=(",", ":")).encode("utf-8"))

        # Convert DER public key to PEM
        rc, _, err = run_cmd([
            "openssl", "pkey", "-pubin", "-inform", "DER",
            "-in", pub_der, "-outform", "PEM", "-out", pub_pem,
        ])
        if rc != 0:
            # Try as raw Ed25519 key (32 bytes)
            # Need to wrap in ASN.1 structure
            raw_key = base64.b64decode(public_key_b64)
            if len(raw_key) == 32:
                # Create a minimal Ed25519 public key PEM
                # OpenSSL Ed25519 public key DER: 30 2a 30 05 06 03 2b 65 70 03 21 00 <32 bytes>
                der_prefix = bytes.fromhex("302a300506032b6570032100")
                full_der = der_prefix + raw_key
                b64_der = base64.b64encode(full_der).decode()
                pem_content = (
                    "-----BEGIN PUBLIC KEY-----\n"
                    + "\n".join(b64_der[i:i+64] for i in range(0, len(b64_der), 64))
                    + "\n-----END PUBLIC KEY-----\n"
                )
                with open(pub_pem, "w") as fh:
                    fh.write(pem_content)
            else:
                log.error("Cannot create Ed25519 PEM from key of length %d", len(raw_key))
                return False

        # Verify
        rc, out, err = run_cmd([
            "openssl", "dgst", "-sha512", "-verify", pub_pem,
            "-signature", sig_file, data_file,
        ])
        if rc == 0 and "Verified OK" in (out or ""):
            log.info("Ed25519 signature verified (openssl)")
            return True
        else:
            log.error("OpenSSL verification failed: %s %s", out, err)
            return False

    except Exception as exc:
        log.error("Ed25519 openssl verification error: %s", exc)
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "ping": handle_ping,
    "get_version": handle_get_version,
    "get_config": handle_get_config,
    "set_language": handle_set_language,
    "fix": handle_fix,
    "scan": handle_scan,
    "remove_printer": handle_remove_printer,
    "repair_printer": handle_repair_printer,
    "define_driver": handle_define_driver,
    "quick_fix_spooler": handle_quick_fix_spooler,
    "network_scan": handle_network_scan,
    "setup_printer": handle_setup_printer,
    "install_thermal_brand": handle_install_thermal_brand,
    "detect_usb_printers": handle_detect_usb_printers,
    "discover_printers": handle_discover_printers,
    "list_installed_printers": handle_list_installed_printers,
    "clear_jobs": handle_clear_jobs,
    "test_print": handle_test_print,
    "update_all": handle_update_all,
    "check_update": handle_check_update,
}


# Action name aliases -- GUI sends "action", daemon expects "command"
ACTION_ALIASES = {
    "diagnose": "fix",
    "scan_network": "network_scan",
    "add_network_printer": "setup_printer",
    "install_thermal_driver": "install_thermal_brand",
    "fix_spooler": "quick_fix_spooler",
    "detect_usb_printer": "detect_usb_printers",
    "list_printers": "discover_printers",
    "update": "update_all",
}


def process_command(data: dict) -> dict:
    """
    Process a single JSON command from the GUI.
    Accepts both "action" and "command" keys.
    Validates the command against ALLOWED_COMMANDS and dispatches to handler.

    IMPORTANT: The GUI sends parameters at the top level of the JSON dict
    (e.g. {"action": "repair_printer", "name": "HP"}), but handlers expect
    them under the "params" key. This function merges top-level keys into
    params so both formats work.
    """
    # Accept both "action" (from GUI) and "command" (internal)
    command = data.get("action", "") or data.get("command", "")

    # Apply aliases so GUI action names map to daemon commands
    command = ACTION_ALIASES.get(command, command)

    if not command:
        return {"status": "error", "message": "No command specified"}

    if command not in ALLOWED_COMMANDS:
        log.warning("Rejected unknown command: %s", command)
        return {"status": "error", "message": f"Unknown command: {command}"}

    handler = HANDLERS.get(command)
    if not handler:
        return {"status": "error", "message": f"No handler for command: {command}"}

    # Extract params from the "params" key first
    params = data.get("params", {})
    if not isinstance(params, dict):
        params = {}

    # CRITICAL FIX: Merge top-level keys (except reserved ones) into params.
    # The GUI sends parameters like {"action": "repair_printer", "name": "HP"}
    # but handlers expect params = {"name": "HP"}. Without this merge,
    # ALL parameterized commands (repair, remove, setup, thermal) fail silently.
    reserved_keys = {"action", "command", "params"}
    for key, value in data.items():
        if key not in reserved_keys and key not in params:
            params[key] = value

    try:
        log.info("Handling command: %s (params: %s)", command, list(params.keys()))
        result = handler(params)
        log.info("Command %s completed: %s", command, result.get("status", "unknown"))

        # SAFETY: After any CUPS-modifying command, ensure CUPS is still running.
        # This prevents the daemon from accidentally leaving CUPS in a stopped state.
        cups_modifying_commands = {
            "fix", "quick_fix_spooler", "setup_printer", "remove_printer",
            "repair_printer", "install_thermal_brand", "clear_jobs",
        }
        if command in cups_modifying_commands:
            if not cups_is_running():
                log.warning("CUPS not running after '%s' -- restarting", command)
                cups_start()

        return result
    except Exception as exc:
        log.error("Exception in handler %s: %s", command, exc, exc_info=True)
        # Ensure CUPS is still running even after handler errors
        if not cups_is_running():
            log.warning("CUPS not running after handler error -- restarting")
            cups_start()
        return {"status": "error", "message": f"Handler error: {exc}"}


# ---------------------------------------------------------------------------
# Unix socket server
# ---------------------------------------------------------------------------

def recv_message(conn: socket.socket) -> bytes | None:
    """
    Receive a newline-delimited JSON message from the socket.
    Protocol: read until newline (\n), then return the payload without it.
    Returns None on connection close or error.
    """
    data = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            return None if not data else data
        data += chunk
        if b"\n" in data:
            # Return everything up to the first newline
            line, _ = data.split(b"\n", 1)
            return line


def send_message(conn: socket.socket, data: bytes):
    """
    Send a newline-delimited message to the socket.
    Protocol: payload + newline (\n).
    """
    conn.sendall(data + b"\n")


def handle_client(conn: socket.socket, addr):
    """
    Handle a single client connection.
    Reads one JSON command, processes it, and sends back the result.
    """
    try:
        conn.settimeout(30)  # Client must send within 30 seconds
        raw = recv_message(conn)
        if raw is None:
            return

        # Decode JSON
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            log.warning("Invalid JSON from client: %s", exc)
            response = {"status": "error", "message": f"Invalid JSON: {exc}"}
            send_message(conn, json.dumps(response).encode("utf-8"))
            return

        # Process the command
        result = process_command(data)

        # Send response
        send_message(conn, json.dumps(result).encode("utf-8"))

    except socket.timeout:
        log.warning("Client connection timed out")
    except ConnectionResetError:
        log.debug("Client disconnected")
    except Exception as exc:
        log.error("Error handling client: %s", exc, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_socket_server():
    """
    Main socket server loop.
    Listens on SOCKET_PATH and spawns threads for each connection.
    """
    # Ensure socket directory exists
    socket_dir = os.path.dirname(SOCKET_PATH)
    os.makedirs(socket_dir, exist_ok=True)

    # Remove stale socket file
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    # Create Unix socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o660)  # Root group only
    server.listen(10)
    log.info("Listening on %s", SOCKET_PATH)

    # Write PID file
    os.makedirs(os.path.dirname(PID_PATH), exist_ok=True)
    with open(PID_PATH, "w") as fh:
        fh.write(str(os.getpid()))

    try:
        while True:
            try:
                conn, _ = server.accept()
                # Handle each client in a separate thread
                t = threading.Thread(target=handle_client, args=(conn, None), daemon=True)
                t.start()
            except OSError as exc:
                if exc.errno == 4:  # Interrupted system call
                    continue
                raise
    except KeyboardInterrupt:
        log.info("Received KeyboardInterrupt -- shutting down")
    finally:
        server.close()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        if os.path.exists(PID_PATH):
            os.remove(PID_PATH)
        log.info("Socket server stopped")


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

def _signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name
    log.info("Received signal %s -- shutting down", sig_name)

    # Clean up socket
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    if os.path.exists(PID_PATH):
        os.remove(PID_PATH)

    sys.exit(0)


def setup_signal_handlers():
    """Register signal handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    # Ignore SIGHUP (don't die if terminal closes)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)


# ---------------------------------------------------------------------------
# Daemonization
# ---------------------------------------------------------------------------

def daemonize():
    """
    Double-fork to daemonize the process.
    Detaches from terminal, redirects stdio to /dev/null.
    """
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as exc:
        log.error("First fork failed: %s", exc)
        sys.exit(1)

    # Create new session
    os.setsid()

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as exc:
        log.error("Second fork failed: %s", exc)
        sys.exit(1)

    # Redirect standard file descriptors to /dev/null
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)  # stdin
    os.dup2(devnull, 1)  # stdout
    os.dup2(devnull, 2)  # stderr
    os.close(devnull)

    # Ensure we don't create files with world-readable permissions
    os.umask(0o022)


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def preflight_checks():
    """Run pre-flight checks before starting the daemon."""
    # Must run as root
    if os.geteuid() != 0:
        print("ERROR: This daemon must run as root", file=sys.stderr)
        sys.exit(1)

    # Ensure CUPS is installed
    rc, _, _ = run_cmd(["which", "cupsd"])
    if rc != 0:
        log.warning("cupsd not found -- CUPS may not be installed")

    # Create necessary directories
    for path in [CONFIG_DIR, LOG_DIR, os.path.dirname(SOCKET_PATH)]:
        os.makedirs(path, exist_ok=True)

    # Initialize config if not present
    if not os.path.isfile(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)

    log.info("Pre-flight checks passed")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auto-update background checker
# ---------------------------------------------------------------------------

_auto_update_stop = threading.Event()


def _auto_update_loop():
    """
    Background thread that periodically checks GitHub for updates.
    When a newer version is found, it logs it but does NOT auto-install.
    The GUI will detect the new version via check_update and show a
    notification banner for the user to click and install.

    The check interval is controlled by AUTO_UPDATE_INTERVAL (default 60s).
    Set AUTO_UPDATE_ENABLED = False to disable.
    """
    log.info("Auto-update check loop started -- checking every %d seconds", AUTO_UPDATE_INTERVAL)

    # Wait a bit on first start so the daemon settles before checking
    _auto_update_stop.wait(30)

    while not _auto_update_stop.is_set():
        try:
            version_url = f"{RAW_BASE}/version.json"
            version_text = download_text(version_url, timeout=15)

            if version_text:
                try:
                    remote_info = json.loads(version_text)
                    remote_version = remote_info.get("version", "")

                    if remote_version and _compare_versions(remote_version, VERSION) > 0:
                        log.info(
                            "Update available: %s -> %s (GUI will notify user)",
                            VERSION, remote_version,
                        )
                    else:
                        log.debug("Update check: already up to date (local=%s, remote=%s)", VERSION, remote_version)

                except json.JSONDecodeError:
                    log.debug("Update check: invalid version.json from GitHub")
            else:
                log.debug("Update check: could not reach GitHub")

        except Exception as exc:
            log.debug("Update check error (non-fatal): %s", exc)

        # Wait for the next check interval (or stop signal)
        _auto_update_stop.wait(AUTO_UPDATE_INTERVAL)


def start_auto_update_checker():
    """Start the auto-update background thread."""
    t = threading.Thread(target=_auto_update_loop, daemon=True, name="auto-update")
    t.start()


def main():
    """Main entry point for the IT Aman Printer Daemon."""
    import argparse

    parser = argparse.ArgumentParser(description=f"IT Aman Printer Daemon v{VERSION}")
    parser.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging to console",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("IT Aman Printer Daemon v%s starting", VERSION)
    log.info("=" * 60)

    # Pre-flight checks
    preflight_checks()

    # Setup signal handlers
    setup_signal_handlers()

    # Daemonize unless foreground mode
    if not args.foreground:
        daemonize()
        log.info("Daemonized -- PID %d", os.getpid())

    # If verbose, increase console log level
    if args.verbose:
        for handler in log.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(logging.DEBUG)

    # Start the auto-update background checker
    if AUTO_UPDATE_ENABLED:
        start_auto_update_checker()
        log.info("Auto-update checker started (interval: %ds)", AUTO_UPDATE_INTERVAL)
    else:
        log.info("Auto-update checker disabled")

    # Start the socket server (blocking)
    try:
        run_socket_server()
    except Exception as exc:
        log.critical("Fatal error in socket server: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
