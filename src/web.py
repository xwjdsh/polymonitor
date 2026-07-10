from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from .config_manager import ConfigManager
    from .polymarket.client import PolymarketClient
    from .state import StateManager

logger = logging.getLogger(__name__)

app = FastAPI(title="Polymonitor Config")

_config_mgr: ConfigManager | None = None
_client: PolymarketClient | None = None
_state_mgr: StateManager | None = None


def init_app(config_mgr: ConfigManager, client: PolymarketClient, state_mgr: StateManager) -> FastAPI:
    global _config_mgr, _client, _state_mgr
    _config_mgr = config_mgr
    _client = client
    _state_mgr = state_mgr
    return app


_MONITOR_KEYS = ("price_monitor", "position_changes")


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


@app.get("/api/daily-changes")
async def get_daily_changes():
    assert _state_mgr is not None and _config_mgr is not None and _client is not None
    baseline = _state_mgr.load_daily_baseline()
    if baseline is None:
        return {"changes": []}

    current: dict[str, dict] = {}
    for wallet in _config_mgr.config.my_wallets:
        try:
            positions = await _client.get_positions(wallet)
            for p in positions:
                if p.token_id and p.token_id not in current:
                    current[p.token_id] = {
                        "title": p.title,
                        "outcome": p.outcome,
                        "value": p.current_value,
                        "price": p.cur_price or 0.0,
                        "event_slug": p.event_slug,
                    }
        except Exception:
            logger.exception("Failed to fetch positions for daily changes")

    changes = []
    for token_id, cur in current.items():
        base = baseline.get(token_id)
        if base is None:
            continue
        _, _, base_value, base_price = base
        change = cur["value"] - base_value
        if abs(change) < 0.01:
            continue
        changes.append({
            "title": cur["title"],
            "outcome": cur["outcome"],
            "event_slug": cur["event_slug"],
            "base_price": round(base_price * 100, 1),
            "cur_price": round(cur["price"] * 100, 1),
            "base_value": round(base_value, 2),
            "cur_value": round(cur["value"], 2),
            "change": round(change, 2),
        })

    changes.sort(key=lambda x: x["change"], reverse=True)
    return {"changes": changes}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymonitor</title>
<style>
  :root { --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a; --text: #e1e4eb; --muted: #8b8fa3; --accent: #6366f1; --accent-hover: #818cf8; --success: #22c55e; --error: #ef4444; --danger: #dc2626; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; max-width: 800px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; }
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
  .ignore-field { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; padding-bottom: 2px; }
  .ignore-field input[type=checkbox] { width: auto; margin-bottom: 0; accent-color: var(--accent); width: 1.1rem; height: 1.1rem; cursor: pointer; }
  .field-group { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .field-group input, .field-group select { margin-bottom: 0; }
  .combobox-wrap { position: relative; }
  .combo-input { margin-bottom: 0; }
  .combo-dropdown { position: absolute; z-index: 100; background: var(--card); border: 1px solid var(--border); border-radius: 4px; width: 100%; max-height: 200px; overflow-y: auto; list-style: none; padding: 0.25rem 0; margin: 2px 0 0; display: none; }
  .combo-dropdown li { padding: 0.35rem 0.75rem; cursor: pointer; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .combo-dropdown li:hover { background: var(--border); }
  .combo-dropdown li span { color: var(--muted); }
  /* Tabs */
  .tabs { display: flex; gap: 0.25rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
  .tab-btn { background: transparent; color: var(--muted); border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 0.5rem 1.25rem; font-size: 0.95rem; cursor: pointer; margin-bottom: -1px; }
  .tab-btn:hover { color: var(--text); background: transparent; }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  /* Daily changes */
  .change-item { display: flex; justify-content: space-between; align-items: flex-start; padding: 0.75rem 0; border-bottom: 1px solid var(--border); gap: 1rem; }
  .change-item:last-child { border-bottom: none; }
  .change-market { flex: 1; min-width: 0; }
  .change-market a { color: var(--text); text-decoration: none; font-weight: 500; }
  .change-market a:hover { color: var(--accent); }
  .change-outcome { font-size: 0.82rem; color: var(--muted); margin-top: 0.1rem; }
  .change-value { text-align: right; white-space: nowrap; }
  .change-delta { font-weight: 600; font-size: 1rem; }
  .change-detail { font-size: 0.8rem; color: var(--muted); margin-top: 0.1rem; }
  .pos { color: var(--success); }
  .neg { color: var(--error); }
  .net-summary { font-size: 0.95rem; padding: 0.6rem 0; margin-bottom: 0.5rem; color: var(--muted); }
  .net-summary strong { color: var(--text); }
  #changes-empty { color: var(--muted); padding: 1rem 0; }
</style>
</head>
<body>
<h1>Polymonitor</h1>
<nav class="tabs">
  <button class="tab-btn active" onclick="showTab('config')">Config</button>
  <button class="tab-btn" onclick="showTab('changes')">Today's Changes</button>
</nav>

<div id="tab-config">
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
  </div>
  <div class="row">
    <div>
      <label for="pc_threshold">Min Change Value ($)</label>
      <input id="pc_threshold" type="number" step="0.01" min="0">
    </div>
    <div>
      <label for="pc_min_value">Min Position Value ($)</label>
      <input id="pc_min_value" type="number" step="0.01" min="0" placeholder="no limit">
    </div>
  </div>
  <div class="row">
    <div>
      <label for="pc_pct_up">Alert if Up ≥ (%)</label>
      <input id="pc_pct_up" type="number" step="0.1" min="0" placeholder="no limit">
    </div>
    <div>
      <label for="pc_pct_down">Alert if Down ≤ (%, e.g. -5)</label>
      <input id="pc_pct_down" type="number" step="0.1" placeholder="no limit">
    </div>
  </div>
  <label>Per-Market Overrides</label>
  <div id="pc_markets"></div>
  <button class="add-btn" onclick="addPcRow()">+ Add market</button>
</section>

<div class="actions">
  <button id="saveBtn" onclick="saveConfig()">Save Config</button>
  <span id="status"></span>
</div>
</div><!-- #tab-config -->

<div id="tab-changes" style="display:none">
  <div class="card">
    <div id="changes-net" class="net-summary" style="display:none"></div>
    <div id="changes-list"></div>
    <div id="changes-empty" style="display:none">No notable changes today.</div>
  </div>
  <div class="actions">
    <button onclick="loadChanges()">Refresh</button>
    <span id="changes-status" style="font-size:0.85rem;color:var(--muted)"></span>
  </div>
</div>

<script>
let positions = []; // [{condition_id, title, outcome, event_title}]

function comboFieldHtml() {
  return '<div class="field-group" style="flex:2"><div class="sub-label">Market</div>' +
    '<div class="combobox-wrap">' +
      '<input type="text" class="combo-input" placeholder="Search market..." autocomplete="off">' +
      '<input type="hidden" class="combo-value">' +
      '<ul class="combo-dropdown"></ul>' +
    '</div></div>';
}

function initCombobox(row, selectedId) {
  const wrap = row.querySelector('.combobox-wrap');
  const input = wrap.querySelector('.combo-input');
  const hidden = wrap.querySelector('.combo-value');
  const dropdown = wrap.querySelector('.combo-dropdown');

  function filter(q) {
    if (!q) return positions;
    const lq = q.toLowerCase();
    return positions.filter(p =>
      p.title.toLowerCase().includes(lq) || p.outcome.toLowerCase().includes(lq)
    );
  }

  function renderDropdown(matches) {
    if (!matches.length) { dropdown.style.display = 'none'; return; }
    dropdown.innerHTML = matches.slice(0, 20).map(p =>
      '<li data-id="' + p.condition_id + '">' + p.title + ' <span>(' + p.outcome + ')</span></li>'
    ).join('');
    dropdown.style.display = '';
    dropdown.querySelectorAll('li').forEach(li => {
      li.addEventListener('mousedown', e => {
        e.preventDefault();
        hidden.value = li.dataset.id;
        input.value = li.firstChild.textContent + li.querySelector('span').textContent;
        dropdown.style.display = 'none';
      });
    });
  }

  if (selectedId) {
    const pos = positions.find(p => p.condition_id === selectedId);
    input.value = pos ? pos.title + ' (' + pos.outcome + ')' : selectedId;
    hidden.value = selectedId;
  }

  input.addEventListener('focus', () => renderDropdown(filter(input.value)));
  input.addEventListener('input', () => { hidden.value = ''; renderDropdown(filter(input.value)); });
  input.addEventListener('blur', () => setTimeout(() => { dropdown.style.display = 'none'; }, 150));
}

function addPmRow(conditionId, above, below, threshold, ignored) {
  const container = document.getElementById('pm_markets');
  const row = document.createElement('div');
  row.className = 'override-row';
  row.innerHTML =
    comboFieldHtml() +
    '<div class="field-group"><div class="sub-label">Above</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (above != null ? above : '') + '"></div>' +
    '<div class="field-group"><div class="sub-label">Below</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (below != null ? below : '') + '"></div>' +
    '<div class="field-group"><div class="sub-label">Threshold</div><input type="number" step="0.01" min="0" max="1" placeholder="-" value="' + (threshold != null ? threshold : '') + '"></div>' +
    '<div class="ignore-field"><div class="sub-label">Ignore</div><input type="checkbox"' + (ignored ? ' checked' : '') + '></div>' +
    '<button class="remove-btn" onclick="this.parentElement.remove()">X</button>';
  container.appendChild(row);
  initCombobox(row, conditionId || '');
}

function addPcRow(conditionId, threshold) {
  const container = document.getElementById('pc_markets');
  const row = document.createElement('div');
  row.className = 'override-row';
  row.innerHTML =
    comboFieldHtml() +
    '<div class="field-group"><div class="sub-label">Threshold</div><input type="number" step="0.01" min="0" placeholder="-" value="' + (threshold != null ? threshold : '') + '"></div>' +
    '<button class="remove-btn" onclick="this.parentElement.remove()">X</button>';
  container.appendChild(row);
  initCombobox(row, conditionId || '');
}

function populate(cfg) {
  document.getElementById('pm_interval').value = cfg.price_monitor.interval_seconds;
  document.getElementById('pm_threshold').value = cfg.price_monitor.default_threshold;
  document.getElementById('pm_markets').innerHTML = '';
  for (const [cid, v] of Object.entries(cfg.price_monitor.per_market || {})) {
    addPmRow(cid, v.above, v.below, v.threshold, v.ignored);
  }
  document.getElementById('pc_interval').value = cfg.position_changes.interval_seconds;
  document.getElementById('pc_threshold').value = cfg.position_changes.default_threshold;
  document.getElementById('pc_min_value').value = cfg.position_changes.min_value ?? '';
  document.getElementById('pc_pct_up').value = cfg.position_changes.pct_up ?? '';
  document.getElementById('pc_pct_down').value = cfg.position_changes.pct_down ?? '';
  document.getElementById('pc_markets').innerHTML = '';
  for (const [cid, v] of Object.entries(cfg.position_changes.per_market || {})) {
    addPcRow(cid, v.threshold);
  }
}

function collect() {
  const pmMarkets = {};
  for (const row of document.getElementById('pm_markets').children) {
    const inputs = row.querySelectorAll('input[type=number]');
    const checkbox = row.querySelector('input[type=checkbox]');
    const cid = row.querySelector('.combo-value').value;
    if (!cid) continue;
    const entry = {};
    if (inputs[0].value !== '') entry.above = Number(inputs[0].value);
    if (inputs[1].value !== '') entry.below = Number(inputs[1].value);
    if (inputs[2].value !== '') entry.threshold = Number(inputs[2].value);
    if (checkbox && checkbox.checked) entry.ignored = true;
    pmMarkets[cid] = entry;
  }

  const pcMarkets = {};
  for (const row of document.getElementById('pc_markets').children) {
    const inputs = row.querySelectorAll('input[type=number]');
    const cid = row.querySelector('.combo-value').value;
    if (!cid) continue;
    const entry = {};
    if (inputs[0].value !== '') entry.threshold = Number(inputs[0].value);
    pcMarkets[cid] = entry;
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
      min_value: document.getElementById('pc_min_value').value !== '' ? Number(document.getElementById('pc_min_value').value) : null,
      pct_up: document.getElementById('pc_pct_up').value !== '' ? Number(document.getElementById('pc_pct_up').value) : null,
      pct_down: document.getElementById('pc_pct_down').value !== '' ? Number(document.getElementById('pc_pct_down').value) : null,
      per_market: pcMarkets,
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

function showTab(name) {
  document.getElementById('tab-config').style.display = name === 'config' ? '' : 'none';
  document.getElementById('tab-changes').style.display = name === 'changes' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', (i === 0) === (name === 'config'));
  });
  if (name === 'changes') loadChanges();
}

async function loadChanges() {
  const statusEl = document.getElementById('changes-status');
  const listEl = document.getElementById('changes-list');
  const netEl = document.getElementById('changes-net');
  const emptyEl = document.getElementById('changes-empty');
  statusEl.textContent = 'Loading...';
  listEl.innerHTML = '';
  netEl.style.display = 'none';
  emptyEl.style.display = 'none';
  try {
    const resp = await fetch('/api/daily-changes');
    const data = await resp.json();
    const changes = data.changes || [];
    statusEl.textContent = 'Updated ' + new Date().toLocaleTimeString();
    if (changes.length === 0) {
      emptyEl.style.display = '';
      return;
    }
    const net = changes.reduce((s, c) => s + c.change, 0);
    const netCls = net >= 0 ? 'pos' : 'neg';
    netEl.innerHTML = 'Net today: <strong class="' + netCls + '">' + (net >= 0 ? '+' : '') + '$' + net.toFixed(2) + '</strong>';
    netEl.style.display = '';
    listEl.innerHTML = changes.map(c => {
      const cls = c.change >= 0 ? 'pos' : 'neg';
      const sign = c.change >= 0 ? '+' : '';
      const url = 'https://polymarket.com/event/' + c.event_slug;
      return '<div class="change-item">' +
        '<div class="change-market">' +
          '<a href="' + url + '" target="_blank">' + c.title + '</a>' +
          '<div class="change-outcome">' + c.outcome + ' &nbsp;' + c.base_price + '¢ → ' + c.cur_price + '¢</div>' +
        '</div>' +
        '<div class="change-value">' +
          '<div class="change-delta ' + cls + '">' + sign + '$' + c.change.toFixed(2) + '</div>' +
          '<div class="change-detail">$' + c.base_value.toFixed(2) + ' → $' + c.cur_value.toFixed(2) + '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch (e) {
    statusEl.textContent = 'Error: ' + e.message;
  }
}
</script>
</body>
</html>
"""
