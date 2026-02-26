from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from .config_manager import ConfigManager
    from .polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)

app = FastAPI(title="Polymonitor Config")

_config_mgr: ConfigManager | None = None
_client: PolymarketClient | None = None


def init_app(config_mgr: ConfigManager, client: PolymarketClient) -> FastAPI:
    global _config_mgr, _client
    _config_mgr = config_mgr
    _client = client
    return app


_MONITOR_KEYS = ("price_monitor", "position_changes", "account_tracker")


@app.get("/api/config")
async def get_config():
    assert _config_mgr is not None
    full = _config_mgr.config.model_dump(mode="json")
    return {k: full[k] for k in _MONITOR_KEYS}


@app.put("/api/config")
async def put_config(request: Request):
    assert _config_mgr is not None
    try:
        raw = await request.json()
        # Merge submitted monitor sections into the current full config
        full = _config_mgr.config.model_dump(mode="json")
        for k in _MONITOR_KEYS:
            if k in raw:
                full[k] = raw[k]
        new_config = await _config_mgr.update(full)
        result = new_config.model_dump(mode="json")
        return {k: result[k] for k in _MONITOR_KEYS}
    except Exception as exc:
        logger.exception("Config update failed")
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/api/positions")
async def get_positions():
    assert _config_mgr is not None and _client is not None
    wallets = _config_mgr.config.my_wallets
    seen: dict[str, dict] = {}
    for wallet in wallets:
        try:
            positions = await _client.get_positions(wallet)
            for p in positions:
                if p.condition_id and p.condition_id not in seen:
                    seen[p.condition_id] = {
                        "condition_id": p.condition_id,
                        "title": p.title,
                        "outcome": p.outcome,
                        "event_title": p.event_title,
                    }
        except Exception:
            logger.exception("Failed to fetch positions for wallet %s", wallet)
    return list(seen.values())


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymonitor Config</title>
<style>
  :root { --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a; --text: #e1e4eb; --muted: #8b8fa3; --accent: #6366f1; --accent-hover: #818cf8; --success: #22c55e; --error: #ef4444; --danger: #dc2626; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; max-width: 800px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: 1.5rem; }
  h2 { font-size: 1.1rem; color: var(--muted); margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.25rem; }
  input, select { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; color: var(--text); padding: 0.5rem 0.75rem; font-size: 0.9rem; margin-bottom: 0.75rem; font-family: inherit; }
  select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b8fa3' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 0.75rem center; padding-right: 2rem; }
  select option { background: var(--card); color: var(--text); }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  button { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 0.6rem 1.5rem; font-size: 0.95rem; cursor: pointer; transition: background 0.15s; }
  button:hover { background: var(--accent-hover); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .actions { display: flex; gap: 0.75rem; align-items: center; margin-top: 0.5rem; }
  #status { font-size: 0.85rem; transition: opacity 0.3s; }
  .success { color: var(--success); }
  .error { color: var(--error); }
  .override-row { display: flex; gap: 0.5rem; align-items: flex-end; margin-bottom: 0.5rem; }
  .override-row select { flex: 2; margin-bottom: 0; }
  .override-row input { flex: 1; margin-bottom: 0; min-width: 0; }
  .override-row .remove-btn { flex: 0 0 auto; background: var(--danger); padding: 0.5rem 0.7rem; font-size: 0.8rem; border-radius: 4px; margin-bottom: 0; }
  .override-row .remove-btn:hover { background: #b91c1c; }
  .add-btn { background: transparent; border: 1px dashed var(--border); color: var(--muted); padding: 0.4rem 1rem; font-size: 0.85rem; margin-top: 0.25rem; }
  .add-btn:hover { border-color: var(--accent); color: var(--accent); background: transparent; }
  .sub-label { font-size: 0.7rem; color: var(--muted); text-align: center; }
  .field-group { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .field-group input, .field-group select { margin-bottom: 0; }
  .account-row { display: flex; gap: 0.5rem; align-items: flex-end; margin-bottom: 0.5rem; }
  .account-row input { margin-bottom: 0; }
  .account-row .addr-field { flex: 3; }
  .account-row .label-field { flex: 1; }
  .account-row .remove-btn { flex: 0 0 auto; background: var(--danger); padding: 0.5rem 0.7rem; font-size: 0.8rem; border-radius: 4px; }
  .account-row .remove-btn:hover { background: #b91c1c; }
</style>
</head>
<body>
<h1>Polymonitor Config</h1>

<section class="card">
  <h2>Price Monitor</h2>
  <div class="row">
    <div>
      <label for="pm_interval">Interval (seconds)</label>
      <input id="pm_interval" type="number" min="0">
    </div>
    <div>
      <label for="pm_threshold">Default Threshold</label>
      <input id="pm_threshold" type="number" step="0.01" min="0">
    </div>
  </div>
  <label>Per-Market Overrides</label>
  <div id="pm_markets"></div>
  <button class="add-btn" onclick="addPmRow()">+ Add market</button>
</section>

<section class="card">
  <h2>Position Changes</h2>
  <div class="row">
    <div>
      <label for="pc_interval">Interval (seconds)</label>
      <input id="pc_interval" type="number" min="0">
    </div>
    <div>
      <label for="pc_threshold">Default Threshold</label>
      <input id="pc_threshold" type="number" step="0.01" min="0">
    </div>
  </div>
  <label>Per-Market Overrides</label>
  <div id="pc_markets"></div>
  <button class="add-btn" onclick="addPcRow()">+ Add market</button>
</section>

<section class="card">
  <h2>Account Tracker</h2>
  <label for="at_interval">Interval (seconds)</label>
  <input id="at_interval" type="number" min="0" style="max-width:200px">
  <label>Tracked Accounts</label>
  <div id="at_accounts"></div>
  <button class="add-btn" onclick="addAtRow()">+ Add account</button>
</section>

<div class="actions">
  <button id="saveBtn" onclick="saveConfig()">Save Config</button>
  <button onclick="loadConfig()" style="background:var(--border)">Reload</button>
  <span id="status"></span>
</div>

<script>
let positions = []; // [{condition_id, title, outcome, event_title}]

function marketOptionHtml(selected) {
  let html = '<option value="">-- select market --</option>';
  for (const p of positions) {
    const label = p.title + ' (' + p.outcome + ')';
    const sel = p.condition_id === selected ? ' selected' : '';
    html += '<option value="' + p.condition_id + '"' + sel + '>' + label + '</option>';
  }
  if (selected && !positions.find(p => p.condition_id === selected)) {
    html += '<option value="' + selected + '" selected>' + selected + '</option>';
  }
  return html;
}

function addPmRow(conditionId, above, below, threshold) {
  const container = document.getElementById('pm_markets');
  const row = document.createElement('div');
  row.className = 'override-row';
  row.innerHTML =
    '<div class="field-group" style="flex:2"><div class="sub-label">Market</div><select>' + marketOptionHtml(conditionId || '') + '</select></div>' +
    '<div class="field-group"><div class="sub-label">Above</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (above != null ? above : '') + '"></div>' +
    '<div class="field-group"><div class="sub-label">Below</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (below != null ? below : '') + '"></div>' +
    '<div class="field-group"><div class="sub-label">Threshold</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (threshold != null ? threshold : '') + '"></div>' +
    '<button class="remove-btn" onclick="this.parentElement.remove()">X</button>';
  container.appendChild(row);
}

function addPcRow(conditionId, threshold) {
  const container = document.getElementById('pc_markets');
  const row = document.createElement('div');
  row.className = 'override-row';
  row.innerHTML =
    '<div class="field-group" style="flex:2"><div class="sub-label">Market</div><select>' + marketOptionHtml(conditionId || '') + '</select></div>' +
    '<div class="field-group"><div class="sub-label">Threshold</div><input type="number" step="0.01" min="0" placeholder="-" value="' + (threshold != null ? threshold : '') + '"></div>' +
    '<button class="remove-btn" onclick="this.parentElement.remove()">X</button>';
  container.appendChild(row);
}

function addAtRow(address, label) {
  const container = document.getElementById('at_accounts');
  const row = document.createElement('div');
  row.className = 'account-row';
  row.innerHTML =
    '<div class="field-group addr-field"><div class="sub-label">Address</div><input type="text" placeholder="0x..." value="' + (address || '') + '"></div>' +
    '<div class="field-group label-field"><div class="sub-label">Label</div><input type="text" placeholder="Name" value="' + (label || '') + '"></div>' +
    '<button class="remove-btn" onclick="this.parentElement.remove()">X</button>';
  container.appendChild(row);
}

function populate(cfg) {
  document.getElementById('pm_interval').value = cfg.price_monitor.interval_seconds;
  document.getElementById('pm_threshold').value = cfg.price_monitor.default_threshold;
  document.getElementById('pm_markets').innerHTML = '';
  for (const [cid, v] of Object.entries(cfg.price_monitor.per_market || {})) {
    addPmRow(cid, v.above, v.below, v.threshold);
  }
  document.getElementById('pc_interval').value = cfg.position_changes.interval_seconds;
  document.getElementById('pc_threshold').value = cfg.position_changes.default_threshold;
  document.getElementById('pc_markets').innerHTML = '';
  for (const [cid, v] of Object.entries(cfg.position_changes.per_market || {})) {
    addPcRow(cid, v.threshold);
  }
  document.getElementById('at_interval').value = cfg.account_tracker.interval_seconds;
  document.getElementById('at_accounts').innerHTML = '';
  for (const a of cfg.account_tracker.accounts || []) {
    addAtRow(a.address, a.label);
  }
}

function collect() {
  const pmMarkets = {};
  for (const row of document.getElementById('pm_markets').children) {
    const sel = row.querySelector('select');
    const inputs = row.querySelectorAll('input');
    const cid = sel.value;
    if (!cid) continue;
    const entry = {};
    if (inputs[0].value !== '') entry.above = Number(inputs[0].value);
    if (inputs[1].value !== '') entry.below = Number(inputs[1].value);
    if (inputs[2].value !== '') entry.threshold = Number(inputs[2].value);
    pmMarkets[cid] = entry;
  }

  const pcMarkets = {};
  for (const row of document.getElementById('pc_markets').children) {
    const sel = row.querySelector('select');
    const inputs = row.querySelectorAll('input');
    const cid = sel.value;
    if (!cid) continue;
    const entry = {};
    if (inputs[0].value !== '') entry.threshold = Number(inputs[0].value);
    pcMarkets[cid] = entry;
  }

  const accounts = [];
  for (const row of document.getElementById('at_accounts').children) {
    const inputs = row.querySelectorAll('input');
    const address = inputs[0].value.trim();
    const label = inputs[1].value.trim();
    if (address) accounts.push({address, label});
  }

  return {
    price_monitor: {
      interval_seconds: Number(document.getElementById('pm_interval').value),
      default_threshold: Number(document.getElementById('pm_threshold').value),
      per_market: pmMarkets,
    },
    position_changes: {
      interval_seconds: Number(document.getElementById('pc_interval').value),
      default_threshold: Number(document.getElementById('pc_threshold').value),
      per_market: pcMarkets,
    },
    account_tracker: {
      interval_seconds: Number(document.getElementById('at_interval').value),
      accounts: accounts,
    },
  };
}

function showStatus(msg, ok) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = ok ? 'success' : 'error';
  setTimeout(() => { el.textContent = ''; }, 4000);
}

async function loadPositions() {
  try {
    const resp = await fetch('/api/positions');
    positions = await resp.json();
  } catch (e) {
    console.warn('Failed to load positions:', e);
  }
}

async function loadConfig() {
  try {
    await loadPositions();
    const resp = await fetch('/api/config');
    const cfg = await resp.json();
    populate(cfg);
    showStatus('Config loaded', true);
  } catch (e) {
    showStatus('Failed to load: ' + e.message, false);
  }
}

async function saveConfig() {
  const btn = document.getElementById('saveBtn');
  btn.disabled = true;
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(collect()),
    });
    if (resp.ok) {
      const cfg = await resp.json();
      populate(cfg);
      showStatus('Config saved successfully', true);
    } else {
      const err = await resp.json();
      showStatus('Error: ' + (err.error || resp.statusText), false);
    }
  } catch (e) {
    showStatus('Failed to save: ' + e.message, false);
  } finally {
    btn.disabled = false;
  }
}

loadConfig();
</script>
</body>
</html>
"""
