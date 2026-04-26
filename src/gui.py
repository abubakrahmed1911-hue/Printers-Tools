#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IT Aman Printer Support Tool v3.4 — GTK3 Frontend

Communicates with it-aman daemon via Unix socket.
Language is selected once at startup and locked for the session.
No branch selection — works directly with network printers.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk, Gio, Pango
import json
import socket
import threading
import os
import sys
import subprocess

# ──────────────────────────── Constants ────────────────────────────

SOCKET_PATH = "/run/it-aman/it-aman.sock"
CONFIG_PATH = "/etc/it-aman/config.json"
APP_VERSION = "3.7"
APP_NAME = "IT Aman - Printer Support Tool"
DEVELOPER = "Developed by: IT Helpdesk Operation"

VIDEO_URL_GDRIVE = (
    "https://drive.google.com/file/d/1e3-7J6hr5yd3uyXSSu8rPJkFwMw8s-My/view?usp=sharing"
)
VIDEO_URL_DROPBOX = (
    "https://www.dropbox.com/scl/fi/pg75dydlchtpju7j65kr2/"
    "Remove-paper-jam-inside-keyocera-UK-TECH-720p-h264.mp4"
    "?rlkey=obb9ghb14yq5l19dv4fdllwfd&st=mw2bixwi&dl=0"
)

ICON_PATH = "/usr/local/share/it-aman/icons/icon-printer.png"

# ──────────────────────────── Translations ────────────────────────────

TRANSLATIONS = {
    "ar": {
        "welcome_title": "IT Aman — أداة دعم الطابعات",
        "welcome_version": "الإصدار {}",
        "welcome_dev": "تطوير: قسم تقنية المعلومات",
        "welcome_company": "شركة أمان للحراسات",
        "welcome_lang_prompt": "اختر اللغة",
        "welcome_arabic": "العربية",
        "welcome_english": "English",
        "welcome_checkbox": "أوافق على المتابعة وأتحمل مسؤولية التغييرات",
        "welcome_continue": "متابعة",
        "welcome_select_lang": "يرجى اختيار اللغة أولاً",
        "welcome_agree": "يرجى الموافقة على الشروط أولاً",
        "main_title": "القائمة الرئيسية",
        "menu_paper_jam": "دليل ازالة ورقة عالقة",
        "menu_paper_jam_desc": "خطوات وفيديو لازالة الورقة العالقة من الطابعة",
        "menu_diagnostic": "تشخيص ذكي (إصلاح تلقائي)",
        "menu_diagnostic_desc": "فحص تلقائي وإصلاح مشاكل الطابعة الشائعة",
        "menu_network": "طابعة شبكية (إضافة/حذف)",
        "menu_network_desc": "البحث عن طابعات الشبكة وإضافتها أو حذفها",
        "menu_thermal": "طابعة حرارية (إضافة/حذف)",
        "menu_thermal_desc": "إعداد طابعة حرارية USB أو حذفها",
        "menu_repair": "إصلاح طابعة (تفعيل + تنظيف)",
        "menu_repair_desc": "تفعيل طابعة معطلة وتنظيف قائمة الطباعة",
        "menu_spooler": "إصلاح سريع لخدمة الطباعة",
        "menu_spooler_desc": "إعادة تشغيل خدمة الطباعة وإصلاحها",
        "menu_status": "حالة الطابعات",
        "menu_status_desc": "عرض حالة جميع الطابعات المتصلة",
        "menu_exit": "خروج",
        "menu_exit_desc": "إغلاق الأداة",
        "back": "رجوع",
        "next": "التالي",
        "cancel": "إلغاء",
        "add": "إضافة",
        "remove": "حذف",
        "close": "إغلاق",
        "confirm": "تأكيد",
        "install": "تثبيت",
        "scanning": "جاري البحث...",
        "installing": "جاري التثبيت...",
        "success": "تم بنجاح!",
        "error": "خطأ",
        "no_printers": "لم يتم العثور على طابعات",
        "select_printer": "يرجى اختيار طابعة",
        "daemon_error": "خطأ في الاتصال بالخادم. تأكد من أن الخدمة تعمل.",
        "step": "الخطوة",
        "of": "من",
        "add_or_remove": "إضافة أو حذف؟",
        "add_printer": "إضافة طابعة",
        "remove_printer": "حذف طابعة",
        "please_wait": "يرجى الانتظار...",
        "yes": "نعم",
        "no": "لا",
        "done": "تم",
        "retry": "إعادة المحاولة",
        "paper_jam_title": "دليل ازالة الورقة العالقة",
        "paper_jam_step1": "1. افتح الغطاء العلوي للطابعة",
        "paper_jam_step2": "2. أخرج خرطوشة الحبر (التنر)",
        "paper_jam_step3": "3. اسحب الورقة العالقة ببطء وعناية",
        "paper_jam_step4": "4. تأكد من عدم بقاء أي قطع صغيرة بالداخل",
        "paper_jam_step5": "5. أعد خرطوشة الحبر وأغلق الغطاء",
        "paper_jam_step6": "6. أعد تشغيل الطابعة",
        "paper_jam_video": "فيديو توضيحي",
        "paper_jam_gdrive": "مشاهدة من Google Drive",
        "paper_jam_dropbox": "مشاهدة من Dropbox",
        "diag_title": "التشخيص الذكي",
        "diag_scanning": "جاري فحص الطابعات وإصلاح المشاكل...",
        "diag_done": "اكتمل التشخيص",
        "diag_nothing": "لم يتم العثور على مشاكل — كل شيء يعمل بشكل طبيعي!",
        "diag_fixed": "تم إصلاح المشاكل التالية:",
        "net_title": "طابعة شبكية",
        "net_scan": "بحث عن طابعات",
        "net_scanning": "جاري البحث عن طابعات الشبكة...",
        "net_found": "تم العثور على طابعة",
        "net_found_plural": "تم العثور على {} طابعات",
        "net_protocol": "البروتوكول",
        "net_driver_needed": "يحتاج تعريف",
        "net_no_driver": "بدون تعريف (تلقائي)",
        "net_adding": "جاري إضافة الطابعة...",
        "net_added": "تمت إضافة الطابعة بنجاح!",
        "net_select_remove": "اختر الطابعة للحذف:",
        "net_confirm_remove": "هل أنت متأكد من حذف هذه الطابعة؟",
        "net_removing": "جاري حذف الطابعة...",
        "net_removed": "تم حذف الطابعة بنجاح!",
        "net_ipp": "IPP Everywhere",
        "net_lpd": "LPD",
        "net_model": "الموديل",
        "thermal_title": "طابعة حرارية",
        "thermal_step1_title": "تحقق من نوع الطابعة",
        "thermal_step1_text": "تأكد أن الطابعة المتصلة هي طابعة حرارية (ثرمال) وليست طابعة ليزر أو نافثة حبر.\n\nالطابعات الحرارية تستخدم ورق حراري فقط وليس ورق عادي.",
        "thermal_step2_title": "اختر العلامة التجارية",
        "thermal_step2_xprinter": "X-Printer XP-80",
        "thermal_step2_xprinter_desc": "طابعة حرارية 80mm",
        "thermal_step2_sprt": "SPRT",
        "thermal_step2_sprt_desc": "طابعة حرارية SPRT",
        "thermal_step3_title": "اتصال USB",
        "thermal_step3_detecting": "جاري التحقق من اتصال USB...",
        "thermal_step3_found": "تم اكتشاف الطابعة على USB!",
        "thermal_step3_not_found": "لم يتم اكتشاف طابعة. تأكد من توصيل USB.",
        "thermal_step4_title": "تحميل وتثبيت التعريف",
        "thermal_step4_downloading": "جاري تحميل التعريف...",
        "thermal_step4_installing": "جاري تثبيت التعريف...",
        "thermal_step5_title": "النتيجة",
        "thermal_step5_success": "تم تثبيت الطابعة الحرارية بنجاح!",
        "thermal_step5_fail": "فشل تثبيت الطابعة الحرارية.",
        "repair_title": "إصلاح طابعة",
        "repair_select": "اختر الطابعة:",
        "repair_enabling": "جاري تفعيل الطابعة...",
        "repair_clearing": "جاري تنظيف قائمة الطباعة...",
        "repair_done": "تم تفعيل الطابعة وتنظيف القائمة!",
        "repair_no_printers": "لا توجد طابعات للإصلاح",
        "spooler_title": "إصلاح خدمة الطباعة",
        "spooler_fixing": "جاري إصلاح خدمة الطباعة...",
        "spooler_done": "تم إصلاح خدمة الطباعة بنجاح!",
        "spooler_fail": "فشل إصلاح خدمة الطباعة.",
        "status_title": "حالة الطابعات",
        "status_name": "الاسم",
        "status_state": "الحالة",
        "status_enabled": "مفعلة",
        "status_disabled": "معطلة",
        "status_jobs": "مهام الطباعة",
        "status_no_jobs": "لا توجد مهام",
        "status_no_printers": "لا توجد طابعات مثبتة",
        "status_refresh": "تحديث",
        "update_available": "تحديث متوفر!",
        "update_current": "الإصدار الحالي: {}",
        "update_new": "الإصدار الجديد: {}",
        "update_download": "تحميل وتثبيت",
        "update_downloading": "جاري تحميل التحديث...",
        "update_installing": "جاري تثبيت التحديث...",
        "update_done": "تم التحديث بنجاح! سيتم إعادة التشغيل.",
        "update_fail": "فشل التحديث.",
        "update_up_to_date": "أنت تستخدم أحدث إصدار",
        "warning": "تحذير",
        "info": "معلومات",
    },
    "en": {
        "welcome_title": "IT Aman — Printer Support Tool",
        "welcome_version": "Version {}",
        "welcome_dev": "Developed by: IT Department",
        "welcome_company": "Aman Security Company",
        "welcome_lang_prompt": "Choose Language",
        "welcome_arabic": "العربية",
        "welcome_english": "English",
        "welcome_checkbox": "I agree to proceed and accept responsibility for changes",
        "welcome_continue": "Continue",
        "welcome_select_lang": "Please select a language first",
        "welcome_agree": "Please agree to the terms first",
        "main_title": "Main Menu",
        "menu_paper_jam": "Paper Jam Guide",
        "menu_paper_jam_desc": "Steps and video to remove paper jam from printer",
        "menu_diagnostic": "Smart Diagnostic (Auto Fix)",
        "menu_diagnostic_desc": "Automatic check and fix for common printer issues",
        "menu_network": "Network Printer (Add/Remove)",
        "menu_network_desc": "Search, add or remove network printers",
        "menu_thermal": "Thermal Printer (Add/Remove)",
        "menu_thermal_desc": "Setup or remove USB thermal printer",
        "menu_repair": "Repair Printer (Enable + Clear)",
        "menu_repair_desc": "Enable disabled printer and clear print queue",
        "menu_spooler": "Quick Fix Spooler",
        "menu_spooler_desc": "Restart and repair the printing service",
        "menu_status": "Printer Status",
        "menu_status_desc": "View status of all connected printers",
        "menu_exit": "Exit",
        "menu_exit_desc": "Close the application",
        "back": "Back",
        "next": "Next",
        "cancel": "Cancel",
        "add": "Add",
        "remove": "Remove",
        "close": "Close",
        "confirm": "Confirm",
        "install": "Install",
        "scanning": "Scanning...",
        "installing": "Installing...",
        "success": "Success!",
        "error": "Error",
        "no_printers": "No printers found",
        "select_printer": "Please select a printer",
        "daemon_error": "Error communicating with daemon. Make sure the service is running.",
        "step": "Step",
        "of": "of",
        "add_or_remove": "Add or Remove?",
        "add_printer": "Add Printer",
        "remove_printer": "Remove Printer",
        "please_wait": "Please wait...",
        "yes": "Yes",
        "no": "No",
        "done": "Done",
        "retry": "Retry",
        "paper_jam_title": "Paper Jam Removal Guide",
        "paper_jam_step1": "1. Open the printer top cover",
        "paper_jam_step2": "2. Remove the toner cartridge",
        "paper_jam_step3": "3. Slowly and carefully pull out the jammed paper",
        "paper_jam_step4": "4. Make sure no small pieces remain inside",
        "paper_jam_step5": "5. Reinstall the toner cartridge and close the cover",
        "paper_jam_step6": "6. Restart the printer",
        "paper_jam_video": "Video Tutorial",
        "paper_jam_gdrive": "Watch on Google Drive",
        "paper_jam_dropbox": "Watch on Dropbox",
        "diag_title": "Smart Diagnostic",
        "diag_scanning": "Scanning printers and fixing issues...",
        "diag_done": "Diagnostic Complete",
        "diag_nothing": "No issues found — everything is working normally!",
        "diag_fixed": "The following issues were fixed:",
        "net_title": "Network Printer",
        "net_scan": "Scan for Printers",
        "net_scanning": "Scanning for network printers...",
        "net_found": "Found 1 printer",
        "net_found_plural": "Found {} printers",
        "net_protocol": "Protocol",
        "net_driver_needed": "Driver needed",
        "net_no_driver": "Driverless (auto)",
        "net_adding": "Adding printer...",
        "net_added": "Printer added successfully!",
        "net_select_remove": "Select printer to remove:",
        "net_confirm_remove": "Are you sure you want to remove this printer?",
        "net_removing": "Removing printer...",
        "net_removed": "Printer removed successfully!",
        "net_ipp": "IPP Everywhere",
        "net_lpd": "LPD",
        "net_model": "Model",
        "thermal_title": "Thermal Printer",
        "thermal_step1_title": "Verify Printer Type",
        "thermal_step1_text": (
            "Make sure the connected printer is a thermal printer, not a laser or inkjet.\n\n"
            "Thermal printers use thermal paper only, not regular paper."
        ),
        "thermal_step2_title": "Select Brand",
        "thermal_step2_xprinter": "X-Printer XP-80",
        "thermal_step2_xprinter_desc": "80mm thermal printer",
        "thermal_step2_sprt": "SPRT",
        "thermal_step2_sprt_desc": "SPRT thermal printer",
        "thermal_step3_title": "USB Connection",
        "thermal_step3_detecting": "Checking USB connection...",
        "thermal_step3_found": "Printer detected on USB!",
        "thermal_step3_not_found": "No printer detected. Make sure USB is connected.",
        "thermal_step4_title": "Download & Install Driver",
        "thermal_step4_downloading": "Downloading driver...",
        "thermal_step4_installing": "Installing driver...",
        "thermal_step5_title": "Result",
        "thermal_step5_success": "Thermal printer installed successfully!",
        "thermal_step5_fail": "Thermal printer installation failed.",
        "repair_title": "Repair Printer",
        "repair_select": "Select printer:",
        "repair_enabling": "Enabling printer...",
        "repair_clearing": "Clearing print queue...",
        "repair_done": "Printer enabled and queue cleared!",
        "repair_no_printers": "No printers to repair",
        "spooler_title": "Fix Printing Service",
        "spooler_fixing": "Fixing printing service...",
        "spooler_done": "Printing service fixed successfully!",
        "spooler_fail": "Failed to fix printing service.",
        "status_title": "Printer Status",
        "status_name": "Name",
        "status_state": "State",
        "status_enabled": "Enabled",
        "status_disabled": "Disabled",
        "status_jobs": "Print Jobs",
        "status_no_jobs": "No jobs",
        "status_no_printers": "No printers installed",
        "status_refresh": "Refresh",
        "update_available": "Update Available!",
        "update_current": "Current version: {}",
        "update_new": "New version: {}",
        "update_download": "Download & Install",
        "update_downloading": "Downloading update...",
        "update_installing": "Installing update...",
        "update_done": "Update successful! Restarting.",
        "update_fail": "Update failed.",
        "update_up_to_date": "You are running the latest version",
        "warning": "Warning",
        "info": "Info",
    }
}

# ──────────────────────────── CSS ────────────────────────────

CSS = """
@define-color primary #2196F3;
@define-color primary_dark #1976D2;
@define-color primary_light #BBDEFB;
@define-color accent #FF9800;
@define-color bg #F5F5F5;
@define-color card_bg #FFFFFF;
@define-color text_primary #212121;
@define-color text_secondary #757575;
@define-color success #4CAF50;
@define-color error_color #F44336;
@define-color warning_color #FF9800;

window {
    background-color: @bg;
}

.header-bar {
    background: linear-gradient(135deg, @primary, @primary_dark);
    color: white;
    padding: 16px 24px;
    border-radius: 0 0 12px 12px;
}

.header-bar .title-label {
    color: white;
    font-size: 20px;
    font-weight: bold;
}

.header-bar .subtitle-label {
    color: rgba(255,255,255,0.85);
    font-size: 13px;
}

.header-bar .dev-label {
    color: rgba(255,255,255,0.6);
    font-size: 11px;
}

.update-banner {
    background: linear-gradient(135deg, #FFF3E0, #FFE0B2);
    border: 2px solid #FF9800;
    border-radius: 8px;
    padding: 8px 12px;
}

.update-banner label {
    color: #E65100;
    font-weight: bold;
    font-size: 13px;
}

.card {
    background-color: @card_bg;
    border-radius: 12px;
    padding: 18px;
    margin: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.card-clickable {
    background-color: @card_bg;
    border-radius: 12px;
    padding: 18px;
    margin: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: all 150ms ease;
}

.card-clickable:hover {
    background-color: #E3F2FD;
    box-shadow: 0 4px 16px rgba(0,0,0,0.14);
}

.card-clickable:active {
    background-color: @primary_light;
}

.card-title {
    font-size: 16px;
    font-weight: bold;
    color: @text_primary;
}

.card-desc {
    font-size: 13px;
    color: @text_secondary;
    margin-top: 4px;
}

.card-icon {
    font-size: 32px;
    color: @primary;
}

.btn-primary {
    background: linear-gradient(135deg, @primary, @primary_dark);
    color: white;
    border-radius: 8px;
    padding: 10px 28px;
    font-weight: bold;
    font-size: 14px;
    border: none;
    box-shadow: 0 2px 6px rgba(33,150,243,0.3);
}

.btn-primary:hover {
    background: linear-gradient(135deg, @primary_dark, #1565C0);
}

.btn-primary:disabled {
    background: #BDBDBD;
    box-shadow: none;
}

.btn-secondary {
    background-color: white;
    color: @primary;
    border: 2px solid @primary;
    border-radius: 8px;
    padding: 8px 24px;
    font-weight: bold;
    font-size: 14px;
}

.btn-secondary:hover {
    background-color: @primary_light;
}

.btn-danger {
    background: linear-gradient(135deg, @error_color, #D32F2F);
    color: white;
    border-radius: 8px;
    padding: 10px 28px;
    font-weight: bold;
    font-size: 14px;
    border: none;
}

.btn-danger:hover {
    background: linear-gradient(135deg, #D32F2F, #B71C1C);
}

.btn-success {
    background: linear-gradient(135deg, @success, #388E3C);
    color: white;
    border-radius: 8px;
    padding: 10px 28px;
    font-weight: bold;
    font-size: 14px;
    border: none;
}

.btn-warning {
    background: linear-gradient(135deg, @warning_color, #F57C00);
    color: white;
    border-radius: 8px;
    padding: 10px 28px;
    font-weight: bold;
    font-size: 14px;
    border: none;
}

.lang-card {
    background-color: @card_bg;
    border-radius: 16px;
    padding: 32px 24px;
    margin: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: all 200ms ease;
    border: 3px solid transparent;
}

.lang-card:hover {
    box-shadow: 0 6px 20px rgba(33,150,243,0.25);
    border-color: @primary;
}

.lang-card.selected {
    background-color: @primary_light;
    border-color: @primary;
    border-width: 3px;
}

.progress-bar trough {
    border-radius: 6px;
    background-color: #E0E0E0;
    min-height: 10px;
}

.progress-bar progress {
    border-radius: 6px;
    background: linear-gradient(90deg, @primary, @primary_dark);
    min-height: 10px;
}

.step-indicator {
    font-size: 14px;
    color: @primary;
    font-weight: bold;
}

.status-enabled {
    color: @success;
    font-weight: bold;
}

.status-disabled {
    color: @error_color;
    font-weight: bold;
}

.printer-result-card {
    background-color: @card_bg;
    border-radius: 12px;
    padding: 16px;
    margin: 8px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    border-left: 4px solid @primary;
}

.brand-card {
    background-color: @card_bg;
    border-radius: 16px;
    padding: 24px;
    margin: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    border: 3px solid transparent;
    transition: all 200ms ease;
}

.brand-card:hover {
    border-color: @primary;
    box-shadow: 0 4px 16px rgba(33,150,243,0.2);
}

.brand-card.selected {
    background-color: @primary_light;
    border-color: @primary;
}

.scrolled-window, .scrolled-window viewport {
    background-color: transparent;
}

.wizard-content {
    padding: 24px;
    min-height: 300px;
}
"""


# ──────────────────────────── Daemon Client ────────────────────────────

class DaemonClient:
    """Communicates with it-aman daemon via Unix socket."""

    def __init__(self, socket_path=SOCKET_PATH):
        self.socket_path = socket_path

    def send_command(self, command_dict, timeout=30):
        """Send a JSON command to the daemon and return the response dict.
        Protocol: newline-delimited JSON (send payload + \\n, receive until \\n).
        """
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(self.socket_path)
            # Send: JSON + newline
            payload = json.dumps(command_dict) + "\n"
            sock.sendall(payload.encode("utf-8"))
            # Receive: read until newline
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            sock.close()
            text = data.decode("utf-8").strip()
            if not text:
                return {"status": "error", "message": "Empty response from daemon"}
            return json.loads(text)
        except socket.timeout:
            return {"status": "error", "message": "Daemon connection timed out"}
        except ConnectionRefusedError:
            return {"status": "error", "message": "Daemon refused connection. Is it running?"}
        except FileNotFoundError:
            return {"status": "error", "message": "Daemon socket not found. Start the service."}
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Invalid response: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def send_threaded(self, command_dict, callback, timeout=30):
        """Send command in a background thread; invoke callback via GLib.idle_add."""

        def _worker():
            result = self.send_command(command_dict, timeout)
            GLib.idle_add(callback, result)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t


# ──────────────────────────── Helpers ────────────────────────────

def t(key, lang):
    """Return translation for *key* in the given language."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


def open_url(url):
    """Open a URL in the default browser."""
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def icon_button(icon_name, label_text, css_class="btn-primary"):
    """Return a Gtk.Button containing an icon and a label."""
    btn = Gtk.Button()
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
    lbl = Gtk.Label(label=label_text)
    hbox.pack_start(icon, False, False, 0)
    hbox.pack_start(lbl, False, False, 0)
    btn.add(hbox)
    btn.get_style_context().add_class(css_class)
    return btn


def pulse_loop(progress_bar):
    """Repeatedly pulse a progress bar until the bar is destroyed."""
    try:
        progress_bar.pulse()
        GLib.timeout_add(100, pulse_loop, progress_bar)
    except Exception:
        pass


# ──────────────────────────── Screen: Welcome ────────────────────────────

class WelcomeScreen(Gtk.Box):
    """Welcome / language-selection screen. Language is chosen ONCE here."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.app = app
        self.selected_lang = None
        self._build()

    # ── build ──

    def _build(self):
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)

        # Title
        title_lbl = Gtk.Label()
        title_lbl.set_markup(
            f"<span size='x-large' weight='bold'>{APP_NAME} v{APP_VERSION}</span>"
        )
        title_lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(title_lbl, False, False, 0)

        # Developer info
        dev_lbl = Gtk.Label(DEVELOPER)
        dev_lbl.get_style_context().add_class("card-desc")
        dev_lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(dev_lbl, False, False, 0)

        self.pack_start(Gtk.Separator(), False, False, 12)

        # Language prompt
        lang_prompt = Gtk.Label()
        lang_prompt.set_markup(
            "<span size='large' weight='bold'>Choose Language / اختر اللغة</span>"
        )
        lang_prompt.set_halign(Gtk.Align.CENTER)
        self.pack_start(lang_prompt, False, False, 8)

        # Language cards
        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        lang_box.set_halign(Gtk.Align.CENTER)

        self.ar_card = self._make_lang_card("العربية", "preferences-desktop-locale", "ar")
        self.en_card = self._make_lang_card("English", "preferences-desktop-locale", "en")
        lang_box.pack_start(self.ar_card, False, False, 0)
        lang_box.pack_start(self.en_card, False, False, 0)
        self.pack_start(lang_box, False, False, 8)

        # Checkbox
        self.agree_check = Gtk.CheckButton()
        self.agree_check.set_halign(Gtk.Align.CENTER)
        self.agree_check.set_margin_top(12)
        self.pack_start(self.agree_check, False, False, 0)

        # Continue
        self.continue_btn = Gtk.Button(label="Continue →")
        self.continue_btn.get_style_context().add_class("btn-primary")
        self.continue_btn.set_halign(Gtk.Align.CENTER)
        self.continue_btn.set_size_request(200, 44)
        self.continue_btn.set_sensitive(False)
        self.continue_btn.connect("clicked", self._on_continue)
        self.pack_start(self.continue_btn, False, False, 16)

    def _make_lang_card(self, text, icon_name, lang_id):
        btn = Gtk.Button()
        btn.get_style_context().add_class("lang-card")
        btn.set_size_request(180, 140)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        lbl = Gtk.Label()
        lbl.set_markup(f"<span size='x-large' weight='bold'>{text}</span>")
        inner.pack_start(icon, False, False, 0)
        inner.pack_start(lbl, False, False, 0)
        btn.add(inner)
        btn.connect("clicked", self._on_lang, lang_id)
        return btn

    # ── callbacks ──

    def _on_lang(self, _btn, lang_id):
        self.selected_lang = lang_id
        # Visual selection
        for card in (self.ar_card, self.en_card):
            card.get_style_context().remove_class("selected")
        target = self.ar_card if lang_id == "ar" else self.en_card
        target.get_style_context().add_class("selected")
        # Update checkbox / button text
        self.agree_check.set_label(t("welcome_checkbox", lang_id))
        self.continue_btn.set_label(t("welcome_continue", lang_id))
        self.continue_btn.set_sensitive(True)

    def _on_continue(self, _btn):
        if not self.selected_lang:
            self.app.show_info(t("welcome_select_lang", "en"))
            return
        if not self.agree_check.get_active():
            self.app.show_info(t("welcome_agree", self.selected_lang))
            return
        self.app.lang = self.selected_lang
        self.app.apply_rtl()
        self.app.show_main_menu()


# ──────────────────────────── Screen: Main Menu ────────────────────────────

class MainMenuScreen(Gtk.Box):
    """Main menu with 8 option cards."""

    MENU_ITEMS = [
        ("paper-jam",      "document-print-preview", "menu_paper_jam",  "menu_paper_jam_desc"),
        ("diagnostic",     "system-run",             "menu_diagnostic", "menu_diagnostic_desc"),
        ("network",        "network-workgroup",      "menu_network",    "menu_network_desc"),
        ("thermal",        "computer",               "menu_thermal",    "menu_thermal_desc"),
        ("repair",         "preferences-system",     "menu_repair",     "menu_repair_desc"),
        ("spooler",        "view-refresh",           "menu_spooler",    "menu_spooler_desc"),
        ("status",         "dialog-information",     "menu_status",     "menu_status_desc"),
        ("exit",           "application-exit",       "menu_exit",       "menu_exit_desc"),
    ]

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang
        grid = Gtk.FlowBox()
        grid.set_homogeneous(True)
        grid.set_min_children_per_line(2)
        grid.set_max_children_per_line(4)
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_margin_top(8)

        for action_id, icon_name, title_key, desc_key in self.MENU_ITEMS:
            card = self._make_card(icon_name, t(title_key, lang), t(desc_key, lang))
            card.connect("clicked", self._on_item, action_id)
            grid.add(card)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(grid)
        self.pack_start(scrolled, True, True, 0)

    def _make_card(self, icon_name, title, desc):
        btn = Gtk.Button()
        btn.get_style_context().add_class("card-clickable")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class("card-icon")
        vbox.pack_start(icon, False, False, 0)
        title_lbl = Gtk.Label()
        title_lbl.set_markup(f"<span weight='bold' size='medium'>{title}</span>")
        title_lbl.set_line_wrap(True)
        title_lbl.set_max_width_chars(20)
        title_lbl.set_justify(Gtk.Justification.CENTER)
        vbox.pack_start(title_lbl, False, False, 0)
        desc_lbl = Gtk.Label(desc)
        desc_lbl.get_style_context().add_class("card-desc")
        desc_lbl.set_line_wrap(True)
        desc_lbl.set_max_width_chars(22)
        desc_lbl.set_justify(Gtk.Justification.CENTER)
        vbox.pack_start(desc_lbl, False, False, 0)
        btn.add(vbox)
        return btn

    def _on_item(self, _btn, action_id):
        dispatch = {
            "paper-jam":  self.app.show_paper_jam,
            "diagnostic": self.app.show_diagnostic,
            "network":    self.app.show_network_printer,
            "thermal":    self.app.show_thermal_printer,
            "repair":     self.app.show_repair,
            "spooler":    self.app.show_spooler,
            "status":     self.app.show_status,
            "exit":       Gtk.main_quit,
        }
        handler = dispatch.get(action_id)
        if handler:
            handler()


# ──────────────────────────── Screen: Paper Jam ────────────────────────────

class PaperJamScreen(Gtk.Box):
    """Paper-jam removal guide with step cards and video links."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang
        align_start = lang != "ar"
        xalign = 0.0 if align_start else 1.0

        # Steps card
        steps_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        steps_card.get_style_context().add_class("card")
        for key in (f"paper_jam_step{i}" for i in range(1, 7)):
            lbl = Gtk.Label()
            lbl.set_markup(f"<span size='medium'>  {t(key, lang)}</span>")
            lbl.set_xalign(xalign)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            steps_card.pack_start(lbl, False, False, 0)
        self.pack_start(steps_card, False, False, 0)

        # Video section
        video_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        video_card.get_style_context().add_class("card")
        vid_title = Gtk.Label()
        vid_title.set_markup(
            f"<span weight='bold' size='medium'>  {t('paper_jam_video', lang)}</span>"
        )
        vid_title.set_xalign(xalign)
        video_card.pack_start(vid_title, False, False, 0)

        for label_key, url, css in [
            ("paper_jam_gdrive", VIDEO_URL_GDRIVE, "btn-primary"),
            ("paper_jam_dropbox", VIDEO_URL_DROPBOX, "btn-secondary"),
        ]:
            btn = icon_button("media-playback-start", t(label_key, lang), css)
            btn.set_halign(Gtk.Align.START if align_start else Gtk.Align.END)
            btn.connect("clicked", lambda _, u=url: open_url(u))
            video_card.pack_start(btn, False, False, 4)

        self.pack_start(video_card, False, False, 0)


# ──────────────────────────── Screen: Diagnostic ────────────────────────────

class DiagnosticScreen(Gtk.Box):
    """Smart diagnostic with progress and result report."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang

        self.status_lbl = Gtk.Label()
        self.status_lbl.set_markup(
            f"<span size='large'>{t('diag_scanning', lang)}</span>"
        )
        self.status_lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(self.status_lbl, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("progress-bar")
        self.pack_start(self.progress, False, False, 16)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        self.pack_start(self.spinner, False, False, 8)

        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.pack_start(self.results_box, False, False, 0)

        # Start pulse & request
        pulse_loop(self.progress)
        self.app.daemon.send_threaded({"action": "diagnose"}, self._on_result)

    def _on_result(self, result):
        try:
            self.spinner.stop()
            self.progress.set_fraction(1.0)
        except Exception:
            pass

        lang = self.app.lang
        status = result.get("status", "error")

        if status == "ok":
            fixes = result.get("fixes", [])
            if not fixes:
                self.status_lbl.set_markup(
                    f"<span size='large' weight='bold' color='#4CAF50'>"
                    f"{t('diag_nothing', lang)}</span>"
                )
            else:
                self.status_lbl.set_markup(
                    f"<span size='large' weight='bold' color='#4CAF50'>"
                    f"{t('diag_fixed', lang)}</span>"
                )
                xalign = 0.0 if lang != "ar" else 1.0
                for fix in fixes:
                    lbl = Gtk.Label()
                    lbl.set_markup(f"  ✓ {fix}")
                    lbl.set_xalign(xalign)
                    self.results_box.pack_start(lbl, False, False, 2)
        else:
            msg = result.get("message", t("error", lang))
            self.status_lbl.set_markup(
                f"<span size='large' weight='bold' color='#F44336'>{msg}</span>"
            )

        try:
            self.results_box.show_all()
        except Exception:
            pass


# ──────────────────────────── Screen: Network Printer ────────────────────────────

class NetworkPrinterScreen(Gtk.Box):
    """Network printer: Add (scan → cards → install) or Remove."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang

        prompt = Gtk.Label()
        prompt.set_markup(
            f"<span size='x-large' weight='bold'>{t('add_or_remove', lang)}</span>"
        )
        prompt.set_halign(Gtk.Align.CENTER)
        self.pack_start(prompt, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        btn_box.set_halign(Gtk.Align.CENTER)

        add_btn = icon_button("list-add", t("add_printer", lang), "btn-success")
        add_btn.set_size_request(200, 60)
        add_btn.connect("clicked", lambda _: self._show_add())
        btn_box.pack_start(add_btn, False, False, 0)

        remove_btn = icon_button("list-remove", t("remove_printer", lang), "btn-danger")
        remove_btn.set_size_request(200, 60)
        remove_btn.connect("clicked", lambda _: self._show_remove())
        btn_box.pack_start(remove_btn, False, False, 0)

        self.pack_start(btn_box, False, False, 0)
        self.set_valign(Gtk.Align.CENTER)

    # ── Add sub-screen ──

    def _show_add(self):
        """Replace content with the scan + results view."""
        lang = self.app.lang
        for child in self.get_children():
            self.remove(child)

        self.scan_btn = icon_button("edit-find", t("net_scan", lang), "btn-primary")
        self.scan_btn.set_halign(Gtk.Align.CENTER)
        self.scan_btn.connect("clicked", lambda _: self._start_scan())
        self.pack_start(self.scan_btn, False, False, 8)

        self.scan_status = Gtk.Label()
        self.scan_status.set_halign(Gtk.Align.CENTER)
        self.pack_start(self.scan_status, False, False, 0)

        self.scan_spinner = Gtk.Spinner()
        self.scan_spinner.set_size_request(32, 32)
        self.pack_start(self.scan_spinner, False, False, 0)

        self.scan_progress = Gtk.ProgressBar()
        self.scan_progress.get_style_context().add_class("progress-bar")
        self.pack_start(self.scan_progress, False, False, 8)

        self.results_scroll = Gtk.ScrolledWindow()
        self.results_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.results_scroll.add(self.results_box)
        self.pack_start(self.results_scroll, True, True, 0)

        self.show_all()

    def _start_scan(self):
        lang = self.app.lang
        self.scan_btn.set_sensitive(False)
        self.scan_status.set_text(t("net_scanning", lang))
        self.scan_spinner.start()
        pulse_loop(self.scan_progress)
        for child in self.results_box.get_children():
            self.results_box.remove(child)
        self.app.daemon.send_threaded({"action": "scan_network"}, self._on_scan_result)

    def _on_scan_result(self, result):
        lang = self.app.lang
        try:
            self.scan_spinner.stop()
            self.scan_progress.set_fraction(1.0)
            self.scan_btn.set_sensitive(True)
        except Exception:
            pass

        if result.get("status") != "ok":
            self.scan_status.set_markup(
                f"<span color='#F44336'>{result.get('message', t('daemon_error', lang))}</span>"
            )
            return

        printers = result.get("printers", [])
        if not printers:
            self.scan_status.set_markup(
                f"<span color='#FF9800'>{t('no_printers', lang)}</span>"
            )
            return

        n = len(printers)
        txt = t("net_found", lang) if n == 1 else t("net_found_plural", lang).format(n)
        self.scan_status.set_markup(f"<span color='#4CAF50' weight='bold'>{txt}</span>")

        for prn in printers:
            self.results_box.pack_start(self._printer_card(prn), False, False, 4)
        try:
            self.results_box.show_all()
        except Exception:
            pass

    def _printer_card(self, prn):
        """Create a result card for a discovered network printer."""
        lang = self.app.lang
        xalign = 0.0 if lang != "ar" else 1.0

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("printer-result-card")

        model = prn.get("model", prn.get("name", "Unknown"))
        model_lbl = Gtk.Label()
        model_lbl.set_markup(f"<span size='x-large' weight='bold'>{model}</span>")
        model_lbl.set_xalign(xalign)
        card.pack_start(model_lbl, False, False, 0)

        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        ip = prn.get("ip", "N/A")
        ip_lbl = Gtk.Label()
        ip_lbl.set_markup(f"<span size='medium'>IP: <b>{ip}</b></span>")
        details.pack_start(ip_lbl, False, False, 0)

        proto_raw = prn.get("protocol", "ipp-everywhere")
        proto = t("net_ipp", lang) if "ipp" in proto_raw.lower() else t("net_lpd", lang)
        proto_lbl = Gtk.Label()
        proto_lbl.set_markup(f"<span size='medium'>{t('net_protocol', lang)}: <b>{proto}</b></span>")
        details.pack_start(proto_lbl, False, False, 0)

        needs_driver = prn.get("needs_driver", False)
        drv_txt = t("net_driver_needed", lang) if needs_driver else t("net_no_driver", lang)
        drv_clr = "#FF9800" if needs_driver else "#4CAF50"
        drv_lbl = Gtk.Label()
        drv_lbl.set_markup(f"<span size='medium' color='{drv_clr}'>{drv_txt}</span>")
        details.pack_start(drv_lbl, False, False, 0)

        card.pack_start(details, False, False, 4)

        add_btn = Gtk.Button(label=t("add", lang))
        add_btn.get_style_context().add_class("btn-success")
        add_btn.set_halign(Gtk.Align.END if lang != "ar" else Gtk.Align.START)
        add_btn.set_size_request(120, 36)

        printer_data = dict(
            name=prn.get("name", model),
            ip=ip,
            model=model,
            protocol=proto_raw,
            needs_driver=needs_driver,
        )

        def _add(btn, data=printer_data):
            btn.set_sensitive(False)
            btn.set_label(t("installing", lang))

            def on_result(res):
                if res.get("status") == "ok":
                    btn.set_label(f"✓ {t('success', lang)}")
                else:
                    btn.set_label(t("retry", lang))
                    btn.set_sensitive(True)
                    self.app.show_error(res.get("message", t("error", lang)))

            self.app.daemon.send_threaded(
                {
                    "action": "add_network_printer",
                    "name": data["name"],
                    "ip": data["ip"],
                    "model": data["model"],
                    "protocol": data["protocol"],
                },
                on_result,
            )

        add_btn.connect("clicked", _add)
        card.pack_start(add_btn, False, False, 0)
        return card

    # ── Remove sub-screen ──

    def _show_remove(self):
        lang = self.app.lang
        for child in self.get_children():
            self.remove(child)

        lbl = Gtk.Label()
        lbl.set_markup(
            f"<span size='medium' weight='bold'>{t('net_select_remove', lang)}</span>"
        )
        lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(lbl, False, False, 8)

        self.remove_spinner = Gtk.Spinner()
        self.remove_spinner.set_size_request(32, 32)
        self.pack_start(self.remove_spinner, False, False, 0)

        self.remove_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.remove_list)
        self.pack_start(scrolled, True, True, 0)
        self.show_all()

        self.remove_spinner.start()
        self.app.daemon.send_threaded({"action": "list_printers"}, self._on_remove_list)

    def _on_remove_list(self, result):
        lang = self.app.lang
        try:
            self.remove_spinner.stop()
        except Exception:
            pass

        if result.get("status") != "ok":
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#F44336'>{result.get('message', t('daemon_error', lang))}</span>"
            )
            self.remove_list.pack_start(lbl, False, False, 0)
            try:
                self.remove_list.show_all()
            except Exception:
                pass
            return

        printers = result.get("printers", [])
        if not printers:
            lbl = Gtk.Label()
            lbl.set_markup(f"<span color='#FF9800'>{t('no_printers', lang)}</span>")
            self.remove_list.pack_start(lbl, False, False, 0)
            try:
                self.remove_list.show_all()
            except Exception:
                pass
            return

        for prn in printers:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.get_style_context().add_class("printer-result-card")
            name = prn.get("name", "Unknown")
            name_lbl = Gtk.Label()
            name_lbl.set_markup(f"<span size='medium' weight='bold'>{name}</span>")
            card.pack_start(name_lbl, True, True, 0)

            rm_btn = Gtk.Button(label=t("remove", lang))
            rm_btn.get_style_context().add_class("btn-danger")
            rm_btn.set_size_request(100, 36)

            def _remove(btn, pname=name):
                dialog = Gtk.MessageDialog(
                    parent=self.app,
                    flags=Gtk.DialogFlags.MODAL,
                    type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    message_format=t("net_confirm_remove", lang),
                )
                resp = dialog.run()
                dialog.destroy()
                if resp == Gtk.ResponseType.YES:
                    btn.set_sensitive(False)
                    btn.set_label("...")

                    def on_res(res):
                        if res.get("status") == "ok":
                            btn.set_label(f"✓ {t('done', lang)}")
                            parent = btn.get_parent()
                            if parent:
                                self.remove_list.remove(parent)
                        else:
                            btn.set_label(t("retry", lang))
                            btn.set_sensitive(True)
                            self.app.show_error(
                                res.get("message", t("error", lang))
                            )

                    self.app.daemon.send_threaded(
                        {"action": "remove_printer", "name": pname}, on_res
                    )

            rm_btn.connect("clicked", _remove)
            card.pack_start(rm_btn, False, False, 0)
            self.remove_list.pack_start(card, False, False, 0)

        try:
            self.remove_list.show_all()
        except Exception:
            pass


# ──────────────────────────── Screen: Thermal Printer (Wizard) ──────────────

class ThermalPrinterScreen(Gtk.Box):
    """Thermal printer wizard: 5-step add, or remove."""

    TOTAL_STEPS = 5

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.app = app
        self.brand = None
        self.usb_detected = False
        self.install_result = None
        self.wizard_step = 0
        self._build_choice()

    # ── Add / Remove choice ──

    def _build_choice(self):
        lang = self.app.lang

        prompt = Gtk.Label()
        prompt.set_markup(
            f"<span size='x-large' weight='bold'>{t('add_or_remove', lang)}</span>"
        )
        prompt.set_halign(Gtk.Align.CENTER)
        self.pack_start(prompt, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        btn_box.set_halign(Gtk.Align.CENTER)

        add_btn = icon_button("list-add", t("add_printer", lang), "btn-success")
        add_btn.set_size_request(200, 60)
        add_btn.connect("clicked", lambda _: self._start_wizard())
        btn_box.pack_start(add_btn, False, False, 0)

        remove_btn = icon_button("list-remove", t("remove_printer", lang), "btn-danger")
        remove_btn.set_size_request(200, 60)
        remove_btn.connect("clicked", lambda _: self._show_remove())
        btn_box.pack_start(remove_btn, False, False, 0)

        self.pack_start(btn_box, False, False, 0)
        self.set_valign(Gtk.Align.CENTER)

    # ── Wizard ──

    def _start_wizard(self):
        self.brand = None
        self.usb_detected = False
        self.install_result = None
        self.wizard_step = 1
        self._show_step()

    def _show_step(self):
        """Rebuild content for current wizard step."""
        for child in self.get_children():
            self.remove(child)

        step = self.wizard_step
        lang = self.app.lang

        # Step indicator
        indicator = Gtk.Label()
        indicator.set_markup(
            f"<span size='large' weight='bold' color='#2196F3'>"
            f"{t('step', lang)} {step} {t('of', lang)} {self.TOTAL_STEPS}</span>"
        )
        indicator.set_halign(Gtk.Align.CENTER)
        self.pack_start(indicator, False, False, 8)

        # Progress bar
        pbar = Gtk.ProgressBar()
        pbar.get_style_context().add_class("progress-bar")
        pbar.set_fraction(step / self.TOTAL_STEPS)
        self.pack_start(pbar, False, False, 0)

        # Content area
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.get_style_context().add_class("wizard-content")
        content.set_valign(Gtk.Align.CENTER)

        builders = {
            1: self._step1_verify,
            2: self._step2_brand,
            3: self._step3_usb,
            4: self._step4_driver,
            5: self._step5_result,
        }
        builders[step](content)
        self.pack_start(content, True, True, 0)

        # Navigation
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav.set_halign(Gtk.Align.CENTER)

        if 1 < step < 5:
            back_btn = Gtk.Button(label=t("back", lang))
            back_btn.get_style_context().add_class("btn-secondary")
            back_btn.connect("clicked", lambda _: self._prev_step())
            nav.pack_start(back_btn, False, False, 0)

        if step < 5:
            self.next_btn = Gtk.Button(label=t("next", lang))
            self.next_btn.get_style_context().add_class("btn-primary")
            self.next_btn.set_size_request(120, 40)
            self.next_btn.connect("clicked", lambda _: self._next_step())
            nav.pack_start(self.next_btn, False, False, 0)

        self.pack_start(nav, False, False, 12)
        self.show_all()

    def _next_step(self):
        if self.wizard_step == 2 and not self.brand:
            self.app.show_info(t("thermal_step2_title", self.app.lang) + " — " + t("select_printer", self.app.lang))
            return
        if self.wizard_step < 5:
            self.wizard_step += 1
            self._show_step()

    def _prev_step(self):
        if self.wizard_step > 1:
            self.wizard_step -= 1
            self._show_step()

    # ── Step 1: Verify printer type ──

    def _step1_verify(self, content):
        warn_icon = Gtk.Image.new_from_icon_name("dialog-warning", Gtk.IconSize.DIALOG)
        warn_icon.set_halign(Gtk.Align.CENTER)
        content.pack_start(warn_icon, False, False, 0)

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('thermal_step1_title', self.app.lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        content.pack_start(title, False, False, 8)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class("card")
        lbl = Gtk.Label()
        lbl.set_markup(f"<span size='medium'>{t('thermal_step1_text', self.app.lang)}</span>")
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(60)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_halign(Gtk.Align.CENTER)
        card.pack_start(lbl, False, False, 0)
        content.pack_start(card, False, False, 0)

    # ── Step 2: Brand selection ──

    def _step2_brand(self, content):
        lang = self.app.lang

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('thermal_step2_title', lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        content.pack_start(title, False, False, 8)

        brand_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        brand_box.set_halign(Gtk.Align.CENTER)

        self.xprinter_card = self._brand_card(
            "printer", t("thermal_step2_xprinter", lang),
            t("thermal_step2_xprinter_desc", lang), "xprinter"
        )
        self.sprt_card = self._brand_card(
            "printer", t("thermal_step2_sprt", lang),
            t("thermal_step2_sprt_desc", lang), "sprt"
        )

        brand_box.pack_start(self.xprinter_card, False, False, 0)
        brand_box.pack_start(self.sprt_card, False, False, 0)
        content.pack_start(brand_box, False, False, 12)

        # Restore visual selection if brand already chosen
        if self.brand:
            target = self.xprinter_card if self.brand == "xprinter" else self.sprt_card
            target.get_style_context().add_class("selected")

    def _brand_card(self, icon_name, name, desc, brand_id):
        btn = Gtk.Button()
        btn.get_style_context().add_class("brand-card")
        btn.set_size_request(200, 200)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.set_pixel_size(64)
        icon.get_style_context().add_class("card-icon")
        vbox.pack_start(icon, False, False, 0)
        name_lbl = Gtk.Label()
        name_lbl.set_markup(f"<span weight='bold' size='large'>{name}</span>")
        name_lbl.set_line_wrap(True)
        name_lbl.set_max_width_chars(16)
        name_lbl.set_justify(Gtk.Justification.CENTER)
        vbox.pack_start(name_lbl, False, False, 0)
        desc_lbl = Gtk.Label(desc)
        desc_lbl.get_style_context().add_class("card-desc")
        desc_lbl.set_line_wrap(True)
        desc_lbl.set_max_width_chars(18)
        desc_lbl.set_justify(Gtk.Justification.CENTER)
        vbox.pack_start(desc_lbl, False, False, 0)
        btn.add(vbox)
        btn.connect("clicked", self._select_brand, brand_id)
        return btn

    def _select_brand(self, btn, brand_id):
        self.brand = brand_id
        for card in (self.xprinter_card, self.sprt_card):
            card.get_style_context().remove_class("selected")
        btn.get_style_context().add_class("selected")

    # ── Step 3: USB detection ──

    def _step3_usb(self, content):
        lang = self.app.lang

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('thermal_step3_title', lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        content.pack_start(title, False, False, 8)

        self.usb_status = Gtk.Label()
        self.usb_status.set_text(t("thermal_step3_detecting", lang))
        self.usb_status.set_halign(Gtk.Align.CENTER)
        content.pack_start(self.usb_status, False, False, 0)

        self.usb_spinner = Gtk.Spinner()
        self.usb_spinner.set_size_request(32, 32)
        self.usb_spinner.start()
        content.pack_start(self.usb_spinner, False, False, 8)

        self.usb_icon = Gtk.Image()
        content.pack_start(self.usb_icon, False, False, 0)

        self.app.daemon.send_threaded(
            {"action": "detect_usb_printer", "brand": self.brand or "xprinter"},
            self._on_usb,
        )

    def _on_usb(self, result):
        lang = self.app.lang
        try:
            self.usb_spinner.stop()
        except Exception:
            pass

        if result.get("status") == "ok":
            self.usb_detected = True
            self.usb_status.set_markup(
                f"<span size='large' weight='bold' color='#4CAF50'>"
                f"{t('thermal_step3_found', lang)}</span>"
            )
            self.usb_icon.set_from_icon_name("emblem-default", Gtk.IconSize.DIALOG)
        else:
            self.usb_detected = False
            self.usb_status.set_markup(
                f"<span size='large' weight='bold' color='#F44336'>"
                f"{t('thermal_step3_not_found', lang)}</span>"
            )
            self.usb_icon.set_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)

    # ── Step 4: Driver download & install ──

    def _step4_driver(self, content):
        lang = self.app.lang

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('thermal_step4_title', lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        content.pack_start(title, False, False, 8)

        self.driver_status = Gtk.Label()
        self.driver_status.set_text(t("thermal_step4_downloading", lang))
        self.driver_status.set_halign(Gtk.Align.CENTER)
        content.pack_start(self.driver_status, False, False, 0)

        self.driver_progress = Gtk.ProgressBar()
        self.driver_progress.get_style_context().add_class("progress-bar")
        content.pack_start(self.driver_progress, False, False, 12)

        self.driver_spinner = Gtk.Spinner()
        self.driver_spinner.set_size_request(32, 32)
        self.driver_spinner.start()
        content.pack_start(self.driver_spinner, False, False, 0)

        pulse_loop(self.driver_progress)
        self.app.daemon.send_threaded(
            {"action": "install_thermal_driver", "brand": self.brand or "xprinter"},
            self._on_driver,
            timeout=120,
        )

    def _on_driver(self, result):
        self.install_result = result
        try:
            self.driver_spinner.stop()
            self.driver_progress.set_fraction(1.0)
        except Exception:
            pass
        # Auto-advance after short delay
        GLib.timeout_add(500, self._auto_advance)

    def _auto_advance(self):
        self.wizard_step = 5
        self._show_step()
        return False

    # ── Step 5: Result ──

    def _step5_result(self, content):
        lang = self.app.lang
        result = self.install_result or {"status": "error", "message": "No result"}

        if result.get("status") == "ok":
            icon = Gtk.Image.new_from_icon_name("emblem-default", Gtk.IconSize.DIALOG)
            icon.set_pixel_size(96)
            icon.set_halign(Gtk.Align.CENTER)
            content.pack_start(icon, False, False, 12)

            title = Gtk.Label()
            title.set_markup(
                f"<span size='x-large' weight='bold' color='#4CAF50'>"
                f"{t('thermal_step5_success', lang)}</span>"
            )
            title.set_halign(Gtk.Align.CENTER)
            content.pack_start(title, False, False, 8)
        else:
            icon = Gtk.Image.new_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)
            icon.set_pixel_size(96)
            icon.set_halign(Gtk.Align.CENTER)
            content.pack_start(icon, False, False, 12)

            title = Gtk.Label()
            title.set_markup(
                f"<span size='x-large' weight='bold' color='#F44336'>"
                f"{t('thermal_step5_fail', lang)}</span>"
            )
            title.set_halign(Gtk.Align.CENTER)
            content.pack_start(title, False, False, 8)

            msg = result.get("message", "")
            if msg:
                msg_lbl = Gtk.Label()
                msg_lbl.set_markup(f"<span color='#757575'>{msg}</span>")
                msg_lbl.set_line_wrap(True)
                msg_lbl.set_max_width_chars(50)
                msg_lbl.set_halign(Gtk.Align.CENTER)
                content.pack_start(msg_lbl, False, False, 4)

        done_btn = Gtk.Button(label=t("done", lang))
        done_btn.get_style_context().add_class("btn-primary")
        done_btn.set_size_request(160, 44)
        done_btn.set_halign(Gtk.Align.CENTER)
        done_btn.connect("clicked", lambda _: self.app.show_main_menu())
        content.pack_start(done_btn, False, False, 16)

    # ── Remove sub-screen ──

    def _show_remove(self):
        lang = self.app.lang
        for child in self.get_children():
            self.remove(child)

        lbl = Gtk.Label()
        lbl.set_markup(
            f"<span size='medium' weight='bold'>{t('net_select_remove', lang)}</span>"
        )
        lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(lbl, False, False, 8)

        self.rm_spinner = Gtk.Spinner()
        self.rm_spinner.set_size_request(32, 32)
        self.pack_start(self.rm_spinner, False, False, 0)

        self.rm_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.rm_list)
        self.pack_start(scrolled, True, True, 0)
        self.show_all()

        self.rm_spinner.start()
        self.app.daemon.send_threaded({"action": "list_printers"}, self._on_rm_list)

    def _on_rm_list(self, result):
        lang = self.app.lang
        try:
            self.rm_spinner.stop()
        except Exception:
            pass

        if result.get("status") != "ok":
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#F44336'>{result.get('message', t('daemon_error', lang))}</span>"
            )
            self.rm_list.pack_start(lbl, False, False, 0)
            try:
                self.rm_list.show_all()
            except Exception:
                pass
            return

        printers = result.get("printers", [])
        if not printers:
            lbl = Gtk.Label()
            lbl.set_markup(f"<span color='#FF9800'>{t('no_printers', lang)}</span>")
            self.rm_list.pack_start(lbl, False, False, 0)
            try:
                self.rm_list.show_all()
            except Exception:
                pass
            return

        for prn in printers:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.get_style_context().add_class("printer-result-card")
            name = prn.get("name", "Unknown")
            name_lbl = Gtk.Label()
            name_lbl.set_markup(f"<span size='medium' weight='bold'>{name}</span>")
            card.pack_start(name_lbl, True, True, 0)

            rm_btn = Gtk.Button(label=t("remove", lang))
            rm_btn.get_style_context().add_class("btn-danger")
            rm_btn.set_size_request(100, 36)

            def _do_remove(btn, pname=name):
                dlg = Gtk.MessageDialog(
                    parent=self.app,
                    flags=Gtk.DialogFlags.MODAL,
                    type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    message_format=t("net_confirm_remove", lang),
                )
                resp = dlg.run()
                dlg.destroy()
                if resp == Gtk.ResponseType.YES:
                    btn.set_sensitive(False)
                    btn.set_label("...")

                    def on_res(res):
                        if res.get("status") == "ok":
                            btn.set_label(f"✓ {t('done', lang)}")
                            parent = btn.get_parent()
                            if parent:
                                self.rm_list.remove(parent)
                        else:
                            btn.set_label(t("retry", lang))
                            btn.set_sensitive(True)
                            self.app.show_error(
                                res.get("message", t("error", lang))
                            )

                    self.app.daemon.send_threaded(
                        {"action": "remove_printer", "name": pname}, on_res
                    )

            rm_btn.connect("clicked", _do_remove)
            card.pack_start(rm_btn, False, False, 0)
            self.rm_list.pack_start(card, False, False, 0)

        try:
            self.rm_list.show_all()
        except Exception:
            pass


# ──────────────────────────── Screen: Repair ────────────────────────────

class RepairScreen(Gtk.Box):
    """Select a printer → enable + clear jobs."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang

        lbl = Gtk.Label()
        lbl.set_markup(
            f"<span size='medium' weight='bold'>{t('repair_select', lang)}</span>"
        )
        lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(lbl, False, False, 8)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.pack_start(self.spinner, False, False, 0)

        self.printer_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.printer_list)
        self.pack_start(scrolled, True, True, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("progress-bar")
        self.pack_start(self.progress, False, False, 4)

        self.status_lbl = Gtk.Label()
        self.status_lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(self.status_lbl, False, False, 0)

        self.spinner.start()
        self.app.daemon.send_threaded({"action": "list_printers"}, self._on_list)

    def _on_list(self, result):
        lang = self.app.lang
        try:
            self.spinner.stop()
        except Exception:
            pass

        if result.get("status") != "ok":
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#F44336'>{result.get('message', t('daemon_error', lang))}</span>"
            )
            self.printer_list.pack_start(lbl, False, False, 0)
            try:
                self.printer_list.show_all()
            except Exception:
                pass
            return

        printers = result.get("printers", [])
        if not printers:
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#FF9800'>{t('repair_no_printers', lang)}</span>"
            )
            self.printer_list.pack_start(lbl, False, False, 0)
            try:
                self.printer_list.show_all()
            except Exception:
                pass
            return

        for prn in printers:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.get_style_context().add_class("printer-result-card")
            name = prn.get("name", "Unknown")
            state = prn.get("state", "unknown")

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name_lbl = Gtk.Label()
            name_lbl.set_markup(f"<span size='medium' weight='bold'>{name}</span>")
            name_lbl.set_xalign(0.0 if lang != "ar" else 1.0)
            info.pack_start(name_lbl, False, False, 0)

            if state in ("disabled", "stopped"):
                state_lbl = Gtk.Label()
                state_lbl.set_markup(
                    f"<span color='#F44336'>{t('status_disabled', lang)}</span>"
                )
                state_lbl.set_xalign(0.0 if lang != "ar" else 1.0)
                info.pack_start(state_lbl, False, False, 0)

            card.pack_start(info, True, True, 0)

            fix_btn = Gtk.Button(label=t("menu_repair", lang))
            fix_btn.get_style_context().add_class("btn-primary")
            fix_btn.set_size_request(120, 36)

            def _fix(btn, pname=name):
                btn.set_sensitive(False)
                self.status_lbl.set_text(t("repair_enabling", lang))
                pulse_loop(self.progress)

                def on_res(res):
                    try:
                        self.progress.set_fraction(1.0)
                    except Exception:
                        pass
                    if res.get("status") == "ok":
                        self.status_lbl.set_markup(
                            f"<span color='#4CAF50' weight='bold'>"
                            f"{t('repair_done', lang)}</span>"
                        )
                        btn.set_label(f"✓ {t('done', lang)}")
                        btn.get_style_context().add_class("btn-success")
                    else:
                        self.status_lbl.set_markup(
                            f"<span color='#F44336'>"
                            f"{res.get('message', t('error', lang))}</span>"
                        )
                        btn.set_label(t("retry", lang))
                        btn.set_sensitive(True)

                self.app.daemon.send_threaded(
                    {"action": "repair_printer", "name": pname}, on_res
                )

            fix_btn.connect("clicked", _fix)
            card.pack_start(fix_btn, False, False, 0)
            self.printer_list.pack_start(card, False, False, 0)

        try:
            self.printer_list.show_all()
        except Exception:
            pass


# ──────────────────────────── Screen: Spooler ────────────────────────────

class SpoolerScreen(Gtk.Box):
    """One-click spooler fix with progress bar."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang

        icon = Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(72)
        icon.set_halign(Gtk.Align.CENTER)
        self.pack_start(icon, False, False, 0)

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('spooler_title', lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        self.pack_start(title, False, False, 8)

        self.status_lbl = Gtk.Label()
        self.status_lbl.set_halign(Gtk.Align.CENTER)
        self.pack_start(self.status_lbl, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("progress-bar")
        self.pack_start(self.progress, False, False, 12)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.pack_start(self.spinner, False, False, 8)

        self.fix_btn = icon_button("system-run", t("menu_spooler", lang), "btn-primary")
        self.fix_btn.set_halign(Gtk.Align.CENTER)
        self.fix_btn.set_size_request(200, 50)
        self.fix_btn.connect("clicked", lambda _: self._fix())
        self.pack_start(self.fix_btn, False, False, 0)

        self.set_valign(Gtk.Align.CENTER)

    def _fix(self):
        lang = self.app.lang
        self.fix_btn.set_sensitive(False)
        self.status_lbl.set_text(t("spooler_fixing", lang))
        self.spinner.start()
        pulse_loop(self.progress)

        def on_result(result):
            try:
                self.spinner.stop()
                self.progress.set_fraction(1.0)
                self.fix_btn.set_sensitive(True)
            except Exception:
                pass

            if result.get("status") == "ok":
                self.status_lbl.set_markup(
                    f"<span color='#4CAF50' weight='bold' size='large'>"
                    f"{t('spooler_done', lang)}</span>"
                )
                self.fix_btn.set_label(f"✓ {t('done', lang)}")
            else:
                msg = result.get("message", t("spooler_fail", lang))
                self.status_lbl.set_markup(
                    f"<span color='#F44336' weight='bold' size='large'>{msg}</span>"
                )

        self.app.daemon.send_threaded({"action": "fix_spooler"}, on_result, timeout=60)


# ──────────────────────────── Screen: Status ────────────────────────────

class StatusScreen(Gtk.Box):
    """Show all printers with enabled/disabled state and job counts."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app = app
        self._build()

    def _build(self):
        lang = self.app.lang

        refresh_btn = icon_button("view-refresh", t("status_refresh", lang), "btn-secondary")
        refresh_btn.set_halign(Gtk.Align.END if lang != "ar" else Gtk.Align.START)
        refresh_btn.connect("clicked", lambda _: self.app.show_status())
        self.pack_start(refresh_btn, False, False, 0)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.pack_start(self.spinner, False, False, 0)

        self.printer_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.printer_list)
        self.pack_start(scrolled, True, True, 0)

        self.spinner.start()
        self.app.daemon.send_threaded({"action": "list_printers"}, self._on_list)

    def _on_list(self, result):
        lang = self.app.lang
        try:
            self.spinner.stop()
        except Exception:
            pass

        if result.get("status") != "ok":
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#F44336'>{result.get('message', t('daemon_error', lang))}</span>"
            )
            self.printer_list.pack_start(lbl, False, False, 0)
            try:
                self.printer_list.show_all()
            except Exception:
                pass
            return

        printers = result.get("printers", [])
        if not printers:
            lbl = Gtk.Label()
            lbl.set_markup(
                f"<span color='#FF9800'>{t('status_no_printers', lang)}</span>"
            )
            self.printer_list.pack_start(lbl, False, False, 0)
            try:
                self.printer_list.show_all()
            except Exception:
                pass
            return

        for prn in printers:
            self.printer_list.pack_start(self._status_card(prn), False, False, 0)

        try:
            self.printer_list.show_all()
        except Exception:
            pass

    def _status_card(self, prn):
        lang = self.app.lang
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("printer-result-card")

        name = prn.get("name", "Unknown")
        state = prn.get("state", "unknown")
        jobs = prn.get("jobs", 0)
        device = prn.get("device", "")

        # Name row
        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_lbl = Gtk.Label()
        name_lbl.set_markup(f"<span size='large' weight='bold'>{name}</span>")
        name_row.pack_start(name_lbl, False, False, 0)

        if state in ("enabled", "idle", "processing"):
            state_lbl = Gtk.Label()
            state_lbl.set_markup(
                f"<span weight='bold' color='#4CAF50'>  {t('status_enabled', lang)}  </span>"
            )
        else:
            state_lbl = Gtk.Label()
            state_lbl.set_markup(
                f"<span weight='bold' color='#F44336'>  {t('status_disabled', lang)}  </span>"
            )
        name_row.pack_start(state_lbl, False, False, 0)
        card.pack_start(name_row, False, False, 0)

        # Details row
        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        if device:
            dev_lbl = Gtk.Label()
            dev_lbl.set_markup(f"<span size='small' color='#757575'>{device}</span>")
            details.pack_start(dev_lbl, False, False, 0)

        jobs_txt = (
            f"{t('status_jobs', lang)}: {jobs}" if jobs > 0 else t("status_no_jobs", lang)
        )
        jobs_lbl = Gtk.Label()
        jobs_lbl.set_markup(f"<span size='small'>{jobs_txt}</span>")
        details.pack_start(jobs_lbl, False, False, 0)
        card.pack_start(details, False, False, 0)

        return card


# ──────────────────────────── Screen: Update ────────────────────────────

class UpdateDialog:
    """Modal dialog shown when a newer version is available."""

    def __init__(self, app, new_version):
        self.app = app
        self.new_version = new_version
        self._show()

    def _show(self):
        lang = self.app.lang

        self.dialog = Gtk.Dialog(
            title=t("update_available", lang),
            parent=self.app,
            flags=Gtk.DialogFlags.MODAL,
        )
        self.dialog.set_default_size(400, 300)

        content = self.dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)

        icon = Gtk.Image.new_from_icon_name(
            "software-update-available", Gtk.IconSize.DIALOG
        )
        icon.set_halign(Gtk.Align.CENTER)
        content.pack_start(icon, False, False, 0)

        title = Gtk.Label()
        title.set_markup(
            f"<span size='x-large' weight='bold'>{t('update_available', lang)}</span>"
        )
        title.set_halign(Gtk.Align.CENTER)
        content.pack_start(title, False, False, 0)

        cur = Gtk.Label(t("update_current", lang).format(APP_VERSION))
        cur.set_halign(Gtk.Align.CENTER)
        content.pack_start(cur, False, False, 0)

        new = Gtk.Label()
        new.set_markup(
            f"<span weight='bold' color='#2196F3'>"
            f"{t('update_new', lang).format(self.new_version)}</span>"
        )
        new.set_halign(Gtk.Align.CENTER)
        content.pack_start(new, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("progress-bar")
        content.pack_start(self.progress, False, False, 0)

        self.status_lbl = Gtk.Label()
        self.status_lbl.set_halign(Gtk.Align.CENTER)
        content.pack_start(self.status_lbl, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        dl_btn = Gtk.Button(label=t("update_download", lang))
        dl_btn.get_style_context().add_class("btn-success")
        dl_btn.set_size_request(160, 40)
        dl_btn.connect("clicked", self._do_update)

        later_btn = Gtk.Button(label=t("cancel", lang))
        later_btn.get_style_context().add_class("btn-secondary")
        later_btn.set_size_request(100, 40)
        later_btn.connect("clicked", lambda _: self.dialog.response(Gtk.ResponseType.CANCEL))

        btn_box.pack_start(dl_btn, False, False, 0)
        btn_box.pack_start(later_btn, False, False, 0)
        content.pack_start(btn_box, False, False, 0)

        content.show_all()
        self.dialog.run()
        self.dialog.destroy()

    def _do_update(self, btn):
        lang = self.app.lang
        btn.set_sensitive(False)
        self.status_lbl.set_text(t("update_downloading", lang))
        pulse_loop(self.progress)

        def on_result(result):
            try:
                self.progress.set_fraction(1.0)
            except Exception:
                pass
            if result.get("status") == "ok":
                self.status_lbl.set_markup(
                    f"<span color='#4CAF50' weight='bold'>"
                    f"{t('update_done', lang)}</span>"
                )
                GLib.timeout_add_seconds(2, Gtk.main_quit)
            else:
                msg = result.get("message", t("update_fail", lang))
                self.status_lbl.set_markup(
                    f"<span color='#F44336'>{msg}</span>"
                )
                btn.set_sensitive(True)

        self.app.daemon.send_threaded(
            {"action": "update"}, on_result, timeout=300
        )


# ──────────────────────────── Main Application Window ────────────────────────────

class ITAmanApp(Gtk.Window):
    """Top-level window that hosts screen widgets."""

    def __init__(self):
        super().__init__(title=APP_NAME)
        self.lang = None
        self.daemon = DaemonClient()

        self._setup_window()
        self._load_css()
        self._build_ui()

        self.show_welcome()

        # Update notification banner (hidden by default)
        self._update_banner = None
        self._update_available_version = None
        self._update_dismissed_version = None  # track dismissed updates so we don't re-show

        # Background update check: first after 3s, then every 60s
        GLib.timeout_add_seconds(3, self._periodic_update_check)

    # ── setup ──

    def _setup_window(self):
        display = Gdk.Display.get_default()
        if display:
            monitor = display.get_primary_monitor()
            if monitor:
                geom = monitor.get_geometry()
                self.set_default_size(int(geom.width * 0.85), int(geom.height * 0.85))
            else:
                self.set_default_size(1100, 750)
        else:
            self.set_default_size(1100, 750)

        self.set_position(Gtk.WindowPosition.CENTER)

        if os.path.exists(ICON_PATH):
            try:
                self.set_icon_from_file(ICON_PATH)
            except Exception:
                self.set_icon_name("printer")
        else:
            self.set_icon_name("printer")

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.main_box)

        # Header
        self.header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header.get_style_context().add_class("header-bar")
        self.main_box.pack_start(self.header, False, False, 0)

        self.header_title = Gtk.Label()
        self.header_title.get_style_context().add_class("title-label")
        self.header_title.set_halign(Gtk.Align.CENTER)
        self.header.pack_start(self.header_title, True, True, 4)

        self.header_sub = Gtk.Label()
        self.header_sub.get_style_context().add_class("subtitle-label")
        self.header_sub.set_halign(Gtk.Align.CENTER)
        self.header.pack_start(self.header_sub, True, True, 4)

        # Developer branding in header
        dev_label = Gtk.Label(label=DEVELOPER)
        dev_label.get_style_context().add_class("dev-label")
        dev_label.set_halign(Gtk.Align.CENTER)
        self.header.pack_start(dev_label, True, True, 2)

        # Content
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.set_margin_start(24)
        self.content.set_margin_end(24)
        self.content.set_margin_top(16)
        self.content.set_margin_bottom(16)
        self.main_box.pack_start(self.content, True, True, 0)

        # Footer (back button)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.footer.set_margin_start(24)
        self.footer.set_margin_end(24)
        self.footer.set_margin_bottom(12)
        self.main_box.pack_start(self.footer, False, False, 0)

    # ── helpers ──

    def set_header(self, title, subtitle=""):
        self.header_title.set_text(title)
        self.header_sub.set_text(subtitle)

    def apply_rtl(self):
        direction = Gtk.TextDirection.RTL if self.lang == "ar" else Gtk.TextDirection.LTR
        self.set_direction(direction)
        self._apply_dir_recursive(self.main_box, direction)

    def _apply_dir_recursive(self, widget, direction):
        widget.set_direction(direction)
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                self._apply_dir_recursive(child, direction)

    def clear_content(self):
        for child in self.content.get_children():
            self.content.remove(child)
        for child in self.footer.get_children():
            self.footer.remove(child)

    def set_screen(self, widget, header_title, header_subtitle="",
                   show_back=True, back_callback=None):
        """Install a screen widget."""
        self.clear_content()
        self.set_header(header_title, header_subtitle)
        self.apply_rtl()
        self.content.pack_start(widget, True, True, 0)
        widget.show_all()

        if show_back and back_callback:
            back_btn = icon_button("go-previous", t("back", self.lang), "btn-secondary")
            back_btn.connect("clicked", lambda _: back_callback())
            self.footer.pack_start(back_btn, False, False, 0)
            self.footer.show_all()

    # ── screen dispatchers ──

    def show_welcome(self):
        self.clear_content()
        self.set_header(APP_NAME, f"v{APP_VERSION}")
        screen = WelcomeScreen(self)
        self.content.pack_start(screen, True, True, 0)
        screen.show_all()
        # No back button on welcome

    def show_main_menu(self):
        screen = MainMenuScreen(self)
        self.set_screen(screen, t("main_title", self.lang), f"v{APP_VERSION}",
                         show_back=False)

    def show_paper_jam(self):
        screen = PaperJamScreen(self)
        self.set_screen(screen, t("paper_jam_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_diagnostic(self):
        screen = DiagnosticScreen(self)
        self.set_screen(screen, t("diag_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_network_printer(self):
        screen = NetworkPrinterScreen(self)
        self.set_screen(screen, t("net_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_thermal_printer(self):
        screen = ThermalPrinterScreen(self)
        self.set_screen(screen, t("thermal_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_repair(self):
        screen = RepairScreen(self)
        self.set_screen(screen, t("repair_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_spooler(self):
        screen = SpoolerScreen(self)
        self.set_screen(screen, t("spooler_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    def show_status(self):
        screen = StatusScreen(self)
        self.set_screen(screen, t("status_title", self.lang),
                         show_back=True, back_callback=self.show_main_menu)

    # ── update check ──

    def _periodic_update_check(self):
        """Check for updates every 60 seconds. Show banner if update found."""
        self.daemon.send_threaded({"action": "check_update"}, self._on_update_check_result, timeout=15)
        return True  # keep the timer running

    def _on_update_check_result(self, result):
        if result.get("status") == "ok":
            latest = result.get("version", APP_VERSION)
            if latest != APP_VERSION:
                # Only show if user hasn't already dismissed this version
                if latest != self._update_dismissed_version:
                    self._show_update_banner(latest)
            else:
                # Up to date — hide banner if showing
                self._hide_update_banner()

    def _show_update_banner(self, new_version):
        """Show a non-intrusive update banner at the top of the window."""
        if self._update_banner is not None:
            # Already showing — update the version text if needed
            if self._update_available_version == new_version:
                return
            # Remove old banner
            self._hide_update_banner()

        self._update_available_version = new_version
        lang = self.lang or "en"

        banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        banner.get_style_context().add_class("update-banner")
        banner.set_margin_start(12)
        banner.set_margin_end(12)
        banner.set_margin_top(4)
        banner.set_margin_bottom(4)

        icon = Gtk.Image.new_from_icon_name("software-update-available", Gtk.IconSize.MENU)
        banner.pack_start(icon, False, False, 0)

        msg = t("update_available", lang) + f"  ({APP_VERSION} → {new_version})"
        msg_lbl = Gtk.Label(label=msg)
        msg_lbl.set_halign(Gtk.Align.START)
        banner.pack_start(msg_lbl, True, True, 0)

        update_btn = Gtk.Button(label=t("update_download", lang))
        update_btn.get_style_context().add_class("btn-success")
        update_btn.set_size_request(120, 30)
        update_btn.connect("clicked", self._do_banner_update)
        banner.pack_start(update_btn, False, False, 0)

        dismiss_btn = Gtk.Button(label="✕")
        dismiss_btn.set_size_request(30, 30)
        dismiss_btn.connect("clicked", self._dismiss_update_banner)
        banner.pack_start(dismiss_btn, False, False, 0)

        banner.show_all()

        # Insert at top of the main container
        main_box = self.get_child()
        if main_box:
            main_box.pack_start(banner, False, False, 0)
            main_box.reorder_child(banner, 0)

        self._update_banner = banner

    def _hide_update_banner(self):
        """Remove the update banner from the window."""
        if self._update_banner is not None:
            main_box = self.get_child()
            if main_box:
                main_box.remove(self._update_banner)
            self._update_banner = None
            self._update_available_version = None

    def _dismiss_update_banner(self, btn=None):
        """User dismissed the update — remember so we don't re-show for this version."""
        self._update_dismissed_version = self._update_available_version
        self._hide_update_banner()

    def _do_banner_update(self, btn):
        """User clicked Update — show the update dialog."""
        if self._update_available_version:
            UpdateDialog(self, self._update_available_version)

    # ── dialogs ──

    def show_info(self, message):
        dlg = Gtk.MessageDialog(
            parent=self, flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
            message_format=message,
        )
        dlg.run()
        dlg.destroy()

    def show_error(self, message):
        dlg = Gtk.MessageDialog(
            parent=self, flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
            message_format=message,
        )
        dlg.run()
        dlg.destroy()


# ──────────────────────────── Entry Point ────────────────────────────

def main():
    app = ITAmanApp()
    app.connect("destroy", lambda _: Gtk.main_quit())
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
