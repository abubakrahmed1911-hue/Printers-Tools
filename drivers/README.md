# Thermal Printer Drivers

Place the following driver files in this directory:

## Required Files

| File | Install Destination | Description |
|------|-------------------|-------------|
| `rastertoprinter` | `/usr/lib/cups/filter/rastertoprinter` | Main CUPS raster filter |
| `rastertoprintercm` | `/usr/lib/cups/filter/rastertoprintercm` | Color mode raster filter variant |
| `rastertoprinterlm` | `/usr/lib/cups/filter/rastertoprinterlm` | Logo mode raster filter variant |
| `80mmSeries.ppd` | `/usr/share/cups/model/80mmSeries.ppd` | PPD file for 80mm thermal printers |

## How to Add Files

1. Copy the binary filter files and PPD file into this `drivers/` directory
2. Commit and push to GitHub
3. The `install.sh` script will automatically download and install them on all devices

## Supported Printers

- XPrinter XP-80 (80mm thermal)
- SPRT (80mm thermal)
- Other 80mm-series thermal printers
