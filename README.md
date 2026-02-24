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

Edit `config.yaml`:
```yaml
telegram:
  bot_token: "your-bot-token"
  chat_id: "your-chat-id"

my_wallets:
  - "0xYourPolymarketWallet"

price_monitor:
  interval_seconds: 60
  default_threshold: 0.05       # alert on 5%+ moves
  per_market:
    # "conditionId":
    #   above: 0.80             # take profit — alert when price >= 0.80
    #   below: 0.30             # stop loss — alert when price <= 0.30
    #   threshold: 0.10         # override default change threshold

position_changes:
  interval_seconds: 3600        # hourly

account_tracker:
  interval_seconds: 120
  accounts:
    - address: "0xSomeWhale"
      label: "Whale A"
```

> To get your Telegram chat ID: send any message to your bot, then visit
> `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id`.

### Run

```bash
.venv/bin/python -m src.main
```

## How It Works

The service runs as a long-lived process using APScheduler to periodically:

1. Fetch your positions from the Polymarket Data API
2. Check current prices via the CLOB API
3. Compare against previous values and send Telegram alerts on significant changes
4. Poll tracked accounts for new trading activity

All Polymarket endpoints used are public and require no authentication.
