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
DRYRUN=1: Logs potential merges without modifying data
DRYRUN=0: Applies actual database merges
Individual sync toggles allow granular control

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

### Troubleshooting
   * Check tesla_sync.log for detailed sync information
   * Verify database connection parameters
   * Ensure sufficient permissions for database access