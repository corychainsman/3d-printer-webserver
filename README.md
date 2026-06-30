# 3D Printer Webserver

Phone-friendly LAN web app for uploading STL files, previewing the arranged build plate, choosing simple slicing settings, selecting a Bambu AMS tray, and sending the sliced job to a Bambu printer.

## What It Does

1. Reads AMS tray status from the printer over local MQTT.
2. Lets you add one or more STL files, with per-file copies and X/Y/Z rotation.
3. Shows a 3D preview of the arranged plate.
4. Slices to a 3MF with Bambu Studio, OrcaSlicer, or a compatible CLI wrapper.
5. Uploads the 3MF to the printer over local FTPS.
6. Starts the print over local MQTT with the selected AMS tray.

This does not log in to Bambu Cloud, modify your Bambu account, or replace Bambu Handy. Handy can remain installed and connected. The only printer state this changes is the same intentional state a print job would change: it uploads a job and starts printing.

## UI Themes

The app includes a bottom `Interface` selector with two external CSS themes:

- Macintosh System style: [system.css](https://sakofchit.github.io/system.css/) by Sakofchit.
- Windows 98 style: [98.css](https://jdan.github.io/98.css/) by Jordan Scales.

The selected theme is stored in browser `localStorage`.

## Printer Requirements

On the printer, enable LAN access and collect:

- Printer IP address or hostname
- Printer serial number
- LAN access code

The container uses local printer credentials only:

- MQTT TLS: `8883`
- FTPS implicit TLS: `990`
- Username: `bblp`
- Password: your LAN access code

## Required Configuration

Secrets and machine-specific values are intentionally supplied through environment variables, either with Portainer stack variables or a local `.env` file.

Required:

```text
BAMBU_HOST
BAMBU_SERIAL
BAMBU_ACCESS_CODE
CONFIG_DIR
DATA_DIR
SLICER_DIR
```

Common optional values:

```text
WEB_PORT=8088
APP_IMAGE=3d-printer-webserver:local
CONTAINER_NAME=3d-printer-webserver
BAMBU_MQTT_PORT=8883
BAMBU_FTPS_PORT=990
DEFAULT_INFILL_DENSITY=15
DEFAULT_WALL_LOOPS=2
DEFAULT_PLATE_INDEX=1
SLICER_BIN=/slicer/BambuStudio.AppImage
SLICER_USE_XVFB=true
SLICER_PLATE_INDEX=0
SLICER_TIMEOUT_SECONDS=900
MACHINE_PROFILE=/config/machine.json
PROCESS_PROFILE=/config/process.json
FILAMENT_PROFILE_DIR=/config/filaments
FALLBACK_FILAMENT_PROFILE=/config/filaments/generic.json
```

## Slicer Requirements

The printer cannot print raw STL files. This app must run Bambu Studio, OrcaSlicer, or a wrapper script that accepts Bambu Studio-compatible CLI flags.

Create host directories and pass them into the container as Portainer variables:

```text
CONFIG_DIR=/path/to/3d-printer/config
DATA_DIR=/path/to/3d-printer/data
SLICER_DIR=/path/to/3d-printer/slicer
```

Expected files:

```text
${SLICER_DIR}/BambuStudio.AppImage
${CONFIG_DIR}/machine.json
${CONFIG_DIR}/process.json
${CONFIG_DIR}/filaments/generic.json
```

Recommended profile setup:

1. In Bambu Studio, configure the printer, nozzle, plate, process preset, and filament presets you actually use.
2. Export the machine/printer profile to `${CONFIG_DIR}/machine.json`.
3. Export the process profile to `${CONFIG_DIR}/process.json`.
4. Export filament profiles into `${CONFIG_DIR}/filaments/`.
5. Name exact material profiles after the AMS-reported material type when possible.

Examples:

```text
${CONFIG_DIR}/filaments/PLA.json
${CONFIG_DIR}/filaments/PETG.json
${CONFIG_DIR}/filaments/ABS.json
${CONFIG_DIR}/filaments/generic.json
```

If an AMS material type has no exact profile file, the app uses `generic.json`.

## Local Docker Compose

```bash
cp .env.example .env
```

Edit `.env` with your printer credentials and local directories, then run:

```bash
docker compose up -d --build
```

Open from your phone:

```text
http://<linux-machine-ip>:8088
```

## Portainer Stack

Use `docker-compose.yml` as the stack file. Set all required values in Portainer stack environment variables rather than hardcoding them into the compose file.

Example non-secret stack variables:

```text
WEB_PORT=8088
CONFIG_DIR=/srv/3d-printer/config
DATA_DIR=/srv/3d-printer/data
SLICER_DIR=/srv/3d-printer/slicer
```

Example secret stack variables:

```text
BAMBU_HOST=<printer-ip-or-hostname>
BAMBU_SERIAL=<printer-serial>
BAMBU_ACCESS_CODE=<lan-access-code>
```

## Git Hygiene

The repo excludes local secrets and bulky/local runtime files:

- `.env`
- `data/`
- `slicer/`
- exported config/profile JSON under `config/`

Commit only code, examples, and documentation. Keep printer credentials, profile exports, slicer binaries, and generated jobs in Portainer variables or local ignored directories.

## Notes

- Job-level `Infill %` maps to Bambu's `sparse_infill_density`.
- Job-level `Walls` maps to Bambu's `wall_loops`.
- The app sends the selected flattened AMS slot reported by the printer.
- Some recent Bambu firmware has tightened local print-command validation. If status and upload work but print start is rejected, capture the `/api/print` `printer_result` and compare the MQTT payload against a print started by Bambu Studio on your firmware.
