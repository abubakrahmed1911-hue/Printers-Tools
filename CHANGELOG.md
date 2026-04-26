# IT Aman Changelog

## v3.9 — Critical Bug Fixes

### Fixed
- **Repair Printer now works**: Created dedicated `handle_repair_printer` that enables a SPECIFIC printer (cupsenable + cupsaccept + clear jobs), instead of mapping to general diagnostic
- **CUPS no longer cancelled by tool**: `handle_quick_fix_spooler` now only cancels STUCK jobs (individual job IDs), not ALL jobs with `cancel -a`
- **Define Driver now works**: Added `handle_define_driver` that searches and installs PPD drivers for existing printers
- **GUI freeze reduced**: Socket cleanup guaranteed with `finally` block; update checks reduced from every 60s to every 5 minutes
- **Version display fixed**: Version 3.9 now correctly shown in all components (daemon, GUI, version.json, install.sh)
- **Branding**: "Developed by: IT Helpdesk Operation" displayed in header

### Improved
- Auto-update check interval changed from 60 seconds to 5 minutes (less network traffic, less CPU)
- `repair_printer` is now its own handler instead of alias to `fix`
- `ACTION_ALIASES` cleaned up — `repair_printer` no longer maps to `fix`
- Socket error handling improved — always closes socket in `finally` block

## v3.8 — Previous Release

### Fixed
- Removed duplicate entries in ALLOWED_COMMANDS set
- Fixed handle_discover_printers to query lpstat -p for all installed printers
- Fixed handle_quick_fix_spooler: safer approach — restart CUPS first
- Fixed handle_remove_printer: removed dangerous cupsdisable before lpadmin -x
- Enhanced handle_detect_usb_printers: added lsusb parsing, /dev/usb/lp* device check
- Fixed handle_check_update to return both remote version and update availability
- User-Agent strings now use VERSION constant instead of hardcoded "3.4"
- Added handle_list_installed_printers for GUI Repair/Status/Remove screens

## v3.4 — Major Refactor

### Fixed
- Language switching no longer freezes the UI (selected at startup only)
- GITHUB_REPO corrected to Printers-Tools
- Update system works without GitHub token (public repo)

### Improved
- Network printer: IPP Everywhere tried first (no driver needed), then LPD fallback
- Thermal printer: 5-step wizard with brand image cards
- Removed branch system (unnecessary complexity)
- Removed data.json dependency
- Cleaner CSS design with RTL support
- All daemon communication is threaded (no UI freezes)

### Security
- No token stored in script
- Ed25519 manifest verification for updates
- private.pem excluded via .gitignore

## v3.3 — Initial Python Port
- Ported from bash script to Python GTK3
- Added daemon + GUI architecture
- Added branch management
- Added Ed25519 signing

## v1.3 — Final Bash Version
- Original bash + zenity script
- Network scan + Kyocera + XP-80 + SPRT support
- Token-based GitHub updates
