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


class PositionChangeMarket(BaseModel):
    threshold: float | None = None


class PositionChangesConfig(BaseModel):
    interval_seconds: int = 3600
    default_threshold: float = 0.1
    per_market: dict[str, PositionChangeMarket] = {}


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
    web_port: int = 8888


def _default_config_path() -> Path:
    return Path(__file__).parent.parent / "config.yaml"


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from config.yaml."""
    path = Path(config_path) if config_path is not None else _default_config_path()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)


_MONITOR_KEYS = ("price_monitor", "position_changes", "account_tracker")


def load_monitors_override(state_dir: str | Path) -> dict:
    """Load monitor config overrides from {state_dir}/monitors.yaml if it exists."""
    path = Path(state_dir) / "monitors.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return {k: v for k, v in raw.items() if k in _MONITOR_KEYS}


def save_monitors(config: AppConfig, state_dir: str | Path) -> None:
    """Write only the three monitor sections to {state_dir}/monitors.yaml."""
    path = Path(state_dir) / "monitors.yaml"
    data = config.model_dump(mode="json")
    monitors = {k: data[k] for k in _MONITOR_KEYS}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(monitors, f, default_flow_style=False, sort_keys=False)
