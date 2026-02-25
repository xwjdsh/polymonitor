from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class TrackedAccount(BaseModel):
    address: str
    label: str


class PriceAlert(BaseModel):
    above: float | None = None
    below: float | None = None
    threshold: float | None = None


class PriceMonitorConfig(BaseModel):
    interval_seconds: int = 60
    default_threshold: float = 0.05
    per_market: dict[str, PriceAlert] = {}


class PositionChangesConfig(BaseModel):
    interval_seconds: int = 3600


class AccountTrackerConfig(BaseModel):
    interval_seconds: int = 120
    accounts: list[TrackedAccount] = []


class AppConfig(BaseModel):
    telegram: TelegramConfig = TelegramConfig()
    my_wallets: list[str] = []
    price_monitor: PriceMonitorConfig = PriceMonitorConfig()
    position_changes: PositionChangesConfig = PositionChangesConfig()
    account_tracker: AccountTrackerConfig = AccountTrackerConfig()
    state_dir: str = "data"


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig(**raw)
