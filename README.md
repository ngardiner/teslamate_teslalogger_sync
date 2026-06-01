# TeslaLogger and TeslaMate Sync Tool

## Overview

This tool provides a robust synchronization mechanism between TeslaLogger and TeslaMate databases, allowing seamless data reconciliation and merge capabilities.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running with Docker](#running-with-docker)
- [Sync Modes](#sync-modes)
- [Logging](#logging)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

### Features

- Bidirectional sync for:
  - Positions
  - Drives
  - Charging Sessions
  - Vehicle States
- Dry run mode for safe testing
- Configurable sync parameters
- Comprehensive logging
- Secure, containerized deployment

## Prerequisites

- Docker
- Docker Compose (optional)
- TeslaLogger Database
- TeslaMate Database

## Configuration

### Environment Variables

Create a `.env` file with the following configuration:

```bash
# TeslaLogger Database Configuration
TESLALOGGER_DB_HOST=localhost  # Hostname or IP of the TeslaLogger database
TESLALOGGER_DB_PORT=3306       # Port number for the TeslaLogger database
TESLALOGGER_DB_NAME=teslalogger  # Name of the TeslaLogger database
TESLALOGGER_DB_USER=root       # Username for the TeslaLogger database
TESLALOGGER_DB_PASSWORD=       # Password for the TeslaLogger database

# TeslaMate Database Configuration
TESLAMATE_DB_HOST=localhost
TESLAMATE_DB_PORT=5432
TESLAMATE_DB_NAME=teslamate
TESLAMATE_DB_USER=teslamate
TESLAMATE_DB_PASSWORD=

# Sync Configuration
DRYRUN=1              # Set to 0 to apply actual changes
TEST_POSITION=0       # Enable detailed position testing
SYNC_POSITIONS=0      # Enable position sync
SYNC_DRIVES=0         # Enable drive sync
SYNC_CHARGING=0       # Enable charging sync
SYNC_STATES=0         # Enable state sync

# Logging
LOG_LEVEL=INFO
```

## Running with Docker
### Build the Docker Image
```docker build -t tesla-sync .```

### Run the Sync Tool

```
# Dry Run Mode (Default)
docker run --env-file .env tesla-sync

# Enable Specific Syncs
docker run --env-file .env \
    -e DRYRUN=0 \
    -e SYNC_POSITIONS=1 \
    -e SYNC_DRIVES=1 \
    tesla-sync
```

### Sync Modes
- **`DRYRUN=1` (Default):** Logs potential merges and delta stats without writing any data to either database. Highly recommended for safe initial runs.
- **`DRYRUN=0`:** Applies actual database merges/writes to reconcile the systems.
- **Granular Toggles:** `SYNC_POSITIONS`, `SYNC_DRIVES`, `SYNC_CHARGING`, and `SYNC_STATES` allow you to enable or disable sync routines individually.

## How It Works: Sync Mechanics & Matching Rules

This tool utilizes an optimized **Sliding-Window Sorted Merge-Join** algorithm to stream and align records chronologically from both databases. Because of this streaming layout, the tool maintains a tiny memory footprint (typically under 50 MB) and will not choke on large tables.

Here is exactly how the script compares and merges each data type:

| Data Type / Sync Module | TeslaLogger Table | TeslaMate Table | Time Window Tolerance | Matching Criteria | Merge / Resolution Rule |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Positions** (`SYNC_POSITIONS`) | `pos` | `positions` | `30 seconds` | Car ID matches **AND** GPS distance is $\le$ `10 meters` (calculated via Haversine formula). | Exact identical matches (same time, car, coordinates) are skipped. Delta rows are identified for addition. |
| **Drives** (`SYNC_DRIVES`) | `drivestate` | `drives` | `5 minutes` | Car ID matches **AND** total driving distance difference is $\le$ `1.0 km`. | Merges the two rows: takes `min` start date, `max` end date, and the `maximum` of both distance and max speed. |
| **Charging** (`SYNC_CHARGING`) | `charging` | `charging_processes` | `5 minutes` | Car ID matches **AND** start timestamps are within window. | Merges the two rows: takes `min` start date, `max` charge energy, and overlays TeslaLogger power/levels on top of TeslaMate cost and battery state. |
| **States** (`SYNC_STATES`) | `state` | `states` | `5 minutes` | Car ID matches **AND** status values match (e.g. `online`, `asleep`). | Merges the two rows: takes `min` start date, `max` end date, and the unified state string. |

### Timezone Safety
* **TeslaLogger** stores naive local timestamps in the database.
* **TeslaMate** stores standard UTC timestamps.
* The script automatically converts TeslaLogger naive times to UTC using the configurable `TESLALOGGER_TIMEZONE` (defaults to `Australia/Melbourne`) before running the matching logic, ensuring perfect alignment.

### Logging
Logs are output to:

   * Console
   * tesla_sync.log file

### Security Considerations
   * Runs as a non-root user to minimize potential damage from exploits.
   * Minimal system dependencies reduce the attack surface.
   * Environment variable-based configuration ensures sensitive data is not hardcoded.
   * **Recommendations**:
     - Use a `.dockerignore` file to exclude sensitive files (e.g., `.env`, `.git`).
     - Avoid committing `.env` files to version control. Use secrets management tools like AWS Secrets Manager, HashiCorp Vault, or Docker secrets for production environments.
     - Regularly update dependencies to patch known vulnerabilities.

### Helm Chart

#### One-time sync
helm install tesla-sync ./helm-chart \
  --set secrets.teslaloggerDbPassword=your_teslalogger_password \
  --set secrets.teslamateDbPassword=your_teslamate_password

#### Scheduled sync
helm install tesla-sync ./helm-chart \
  --set schedule.enabled=true \
  --set schedule.cron="0 2 * * *" \
  --set sync.positions=true \
  --set sync.drives=true \
  --set secrets.teslaloggerDbPassword=your_teslalogger_password \
  --set secrets.teslamateDbPassword=your_teslamate_password


### Troubleshooting
   * Check tesla_sync.log for detailed sync information
   * Verify database connection parameters
   * Ensure sufficient permissions for database access