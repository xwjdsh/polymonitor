# Polymonitor — Polymarket Personal Trading Monitor

## Overview
A Python long-running service that monitors Polymarket positions and sends Telegram notifications.

### Three core monitors:
1. **Price Monitor** — Polls positions, alerts on price change threshold or above/below level crossings (stop loss / take profit)
2. **Position Changes** — Periodically reports only positions whose value changed since last check
3. **Account Tracker** — Watches specified wallets for new trading activity

## Project Structure
```
src/
├── main.py                  # Entry point, APScheduler setup, signal handling
├── config.py                # Loads config.yaml (Pydantic models)
├── notifier.py              # Telegram bot sender with console fallback
├── state.py                 # StateManager — CSV-based state persistence
├── polymarket/
│   ├── client.py            # Async httpx client for Polymarket public APIs
│   └── models.py            # Pydantic models (Position, Market, Activity)
└── monitors/
    ├── price_monitor.py     # Price change detection + above/below level alerts
    ├── position_changes.py  # Reports only changed position values
    └── account_tracker.py   # Tracked account activity alerts
data/                        # State CSV files (gitignored, created at runtime)
```

## APIs Used (all public, no auth required)
- `data-api.polymarket.com` — positions, activity, trades
- `gamma-api.polymarket.com` — market metadata
- `clob.polymarket.com` — live prices, midpoints

## Development

### Setup
```bash
uv venv && uv pip install -e "."
```

### Run
```bash
.venv/bin/python -m src.main
```

### Configuration
- `config.yaml` — all settings (Telegram credentials, wallets, thresholds, intervals, tracked accounts)
- `config.example.yaml` — template to copy from

### State Persistence
Monitor state is saved to timestamped CSV files in `data/` (one file per monitor, overwritten each save). On restart, state is reloaded if the file is younger than `state_max_age_seconds` (default 3600s), preventing duplicate alerts. State is saved every 60s and on shutdown.

## Key Dependencies
- `httpx` — async HTTP
- `pydantic` — data models & config validation
- `python-telegram-bot` — notifications
- `apscheduler` — job scheduling
- `pyyaml` — config loading
