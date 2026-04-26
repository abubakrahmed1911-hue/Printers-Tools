# IT Aman Changelog

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
