# Polymonitor

Personal Polymarket trading monitor. Tracks your positions, alerts on price changes, summarizes P&L, and watches other accounts — all via Telegram.

## Features

- **Price Alerts** — Monitor your positions and get notified when prices move beyond a configurable threshold (default 5%), with per-market above/below levels for stop loss and take profit
- **Position Changes** — Periodic reports of only the positions whose value changed since last check, including detection of closed positions
- **Account Tracker** — Watch specific wallets (whales, smart traders) and get notified when they trade

## Setup

### Prerequisites
- Python 3.11+
- A Telegram bot (create one via [@BotFather](https://t.me/BotFather))

### Install

```bash
uv venv && uv pip install -e "."
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Telegram credentials, wallets, and thresholds. See [`config.example.yaml`](config.example.yaml) for all available options.

> To get your Telegram chat ID: send any message to your bot, then visit
> `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id`.

### Run

```bash
.venv/bin/python -m src.main
```

## State Persistence

Monitor state is saved to timestamped CSV files in `data/` every 60 seconds and on shutdown. On restart, state is reloaded if the file is younger than `state_max_age_seconds` (default 1 hour), preventing duplicate alerts. Configure via `state_dir` and `state_max_age_seconds` in `config.yaml`.

## How It Works

The service runs as a long-lived process using APScheduler to periodically:

1. Fetch your positions from the Polymarket Data API
2. Check current prices via the CLOB API
3. Compare against previous values and send Telegram alerts on significant changes
4. Poll tracked accounts for new trading activity

All Polymarket endpoints used are public and require no authentication.
