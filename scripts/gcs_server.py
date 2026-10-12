#!/usr/bin/env bash
"""Neuron Cupboard: Pure-Python Tactical Ground Control Station (GCS).

Zero-dependency tactical HUD web server and optical pulse wire stream ingest.
Runs seamlessly on Windows, macOS, Linux, and Raspberry Pi without Go or C compilers.
"""

import sys
import os
import time
import json
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional

# Link-layer wire protocol framing constants
PREAMBLE = 0xAA
SYNC_WORD = 0xD5
FRAME_LEN = 6

MODE_NAMES = ["MODE_UNSPECIFIED", "MODE_SEARCH", "MODE_FORMATION_LOCK", "MODE_DISPERSAL"]
LOCK_NAMES = ["LOCK_NONE", "LOCK_ACQUIRING", "LOCK_TRACKING", "LOCK_HARD_LOCKED"]


def crc8(data: bytes) -> int:
    crc = 0x00
    for b in data:
        crc ^= b & 0xFF
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class SwarmMonitor:
    def __init__(self, node_ttl_sec: float = 5.0):
        self.lock = threading.Lock()
        self.nodes: Dict[int, dict] = {}
        self.events: List[dict] = []
        self.latest_pulse: Optional[dict] = None
        self.total_frames = 0
        self.last_rate_time = time.time()
        self.rate_frames = 0
        self.current_rate_hz = 0.0
        self.node_ttl_sec = node_ttl_sec

    def ingest_frame(self, raw_bytes: bytes, client_addr=None):
        if len(raw_bytes) != FRAME_LEN:
            return False
        if raw_bytes[0] != PREAMBLE or raw_bytes[1] != SYNC_WORD:
            return False

        expected = crc8(raw_bytes[2:5])
        if raw_bytes[5] != expected:
            return False

        node_id = raw_bytes[2]
        seq_num = raw_bytes[3]
        state_byte = raw_bytes[4]
        crc_val = raw_bytes[5]

        mode = (state_byte & 0x03)
        lock_status = (state_byte >> 2) & 0x03
        ack = bool(state_byte & 0x10)
        prox = bool(state_byte & 0x20)
        swap = bool(state_byte & 0x40)

        now = time.time()
        now_ms = int(now * 1000)
        time_str = time.strftime("%H:%M:%S", time.localtime(now))

        with self.lock:
            self.total_frames += 1
            self.rate_frames += 1
            elapsed = now - self.last_rate_time
            if elapsed >= 1.0:
                self.current_rate_hz = self.rate_frames / elapsed
                self.rate_frames = 0
                self.last_rate_time = now

            prev = self.nodes.get(node_id)
            mode_str = MODE_NAMES[mode] if mode < len(MODE_NAMES) else f"MODE_{mode}"
            lock_str = LOCK_NAMES[lock_status] if lock_status < len(LOCK_NAMES) else f"LOCK_{lock_status}"

            if not prev:
                self._add_event(time_str, node_id, "INFO", "Optical line-of-sight acquired")
            else:
                if prev.get("mode") != mode_str:
                    self._add_event(time_str, node_id, "INFO", f"Operational mode -> {mode_str.replace('MODE_', '')}")
                if prev.get("lock_status") != lock_str:
                    lvl = "LOCK" if lock_str == "LOCK_HARD_LOCKED" else "INFO"
                    self._add_event(time_str, node_id, lvl, f"Optical lock -> {lock_str.replace('LOCK_', '')}")
                if not prev.get("proximity_alert") and prox:
                    self._add_event(time_str, node_id, "WARN", "Proximity alert flag active")

            # Optical bearing default (forward boresight lock)
            az_mrad = prev.get("azimuth_mrad", 50) if prev else 50
            el_mrad = prev.get("elevation_mrad", 0) if prev else 0

            self.nodes[node_id] = {
                "node_id": node_id,
                "sequence_num": seq_num,
                "mode": mode_str,
                "lock_status": lock_str,
                "consensus_ack": ack,
                "proximity_alert": prox,
                "swap_critical": swap,
                "azimuth_mrad": az_mrad,
                "elevation_mrad": el_mrad,
                "crc8": crc_val,
                "last_seen_ms": now_ms,
            }

            self.latest_pulse = {
                "time": time.strftime("%H:%M:%S", time.localtime(now)) + f".{int((now % 1)*1000):03d}",
                "node_id": node_id,
                "sequence_num": seq_num,
                "mode": mode_str,
                "lock_status": lock_str,
                "azimuth_mrad": az_mrad,
                "crc8": crc_val,
            }

        return True

    def _add_event(self, time_str: str, node_id: int, level: str, message: str):
        self.events.insert(0, {
            "time": time_str,
            "node_id": node_id,
            "level": level,
            "message": message,
        })
        if len(self.events) > 8:
            self.events = self.events[:8]

    def snapshot(self) -> dict:
        now_ms = int(time.time() * 1000)
        with self.lock:
            active = []
            stale = []
            for n_id, n in list(self.nodes.items()):
                if now_ms - n["last_seen_ms"] < int(self.node_ttl_sec * 1000):
                    active.append(dict(n))
                else:
                    stale.append(n_id)

            for n_id in stale:
                del self.nodes[n_id]
                time_str = time.strftime("%H:%M:%S")
                self._add_event(time_str, n_id, "WARN", "Optical line-of-sight lost (timeout)")

            return {
                "active_nodes": active,
                "stats": {
                    "total_frames": self.total_frames,
                    "packet_rate_hz": round(self.current_rate_hz, 1),
                },
                "events": list(self.events),
                "latest_pulse": dict(self.latest_pulse) if self.latest_pulse else None,
            }


class GCSRequestHandler(BaseHTTPRequestHandler):
    monitor: SwarmMonitor = None
    html_content: bytes = b""

    def log_message(self, format, *args):
        # Silence standard HTTP access logging to keep terminal clean
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(self.html_content)))
            self.end_headers()
            self.wfile.write(self.html_content)
        elif self.path == "/healthz":
            snap = self.monitor.snapshot()
            resp = json.dumps({"status": "UP", "frames_ingested": snap["stats"]["total_frames"]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif self.path == "/api/nodes":
            snap = self.monitor.snapshot()
            resp = json.dumps(snap["active_nodes"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    snap = self.monitor.snapshot()
                    payload = f"data: {json.dumps(snap)}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        else:
            self.send_response(404)
            self.end_headers()


def run_udp_listener(monitor: SwarmMonitor, host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Enable socket reuse
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    print(f"level=INFO event=gcs_udp_listener_active addr={host}:{port}")

    while True:
        try:
            data, addr = sock.recvfrom(256)
            if data:
                monitor.ingest_frame(data, addr)
        except Exception as e:
            time.sleep(0.01)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neuron Cupboard Python Tactical Ground Control Station")
    parser.add_argument("--listen", type=str, default="0.0.0.0:9092", help="UDP listen address (default: 0.0.0.0:9092)")
    parser.add_argument("--http", type=str, default="0.0.0.0:8080", help="HTTP dashboard address (default: 0.0.0.0:8080)")
    parser.add_argument("--ttl", type=float, default=6.0, help="Node line-of-sight timeout in seconds (default: 6.0)")
    parser.add_argument("--demo", action="store_true", help="Simulate swarm telemetry")
    args = parser.parse_args()

    # Embedded web/index.html tactical HUD
    GCSRequestHandler.html_content = b'<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>Bamboo Node // Swarm Monitor</title>\n  <style>\n    :root {\n      /* Bamboo & Panda Color Theme */\n      --bg: #0d120f;\n      --card-bg: #141c16;\n      --card-border: #1f2d22;\n      --card-border-active: #2d4232;\n      --text: #f0fdf4;\n      --text-muted: #7b9483;\n      --bamboo-green: #34d399;\n      --bamboo-green-glow: rgba(52, 211, 153, 0.12);\n      --amber: #fbbf24;\n      --red: #f87171;\n      --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;\n      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;\n    }\n\n    * { box-sizing: border-box; margin: 0; padding: 0; }\n\n    body {\n      background: var(--bg);\n      color: var(--text);\n      font-family: var(--sans);\n      font-size: 13px;\n      line-height: 1.5;\n      padding: 24px;\n      max-width: 900px;\n      margin: 0 auto;\n    }\n\n    /* Minimal Header */\n    header {\n      display: flex;\n      justify-content: space-between;\n      align-items: center;\n      padding-bottom: 16px;\n      border-bottom: 1px solid var(--card-border);\n      margin-bottom: 20px;\n    }\n\n    .brand {\n      display: flex;\n      align-items: center;\n      gap: 10px;\n    }\n\n    .brand-icon {\n      font-size: 18px;\n    }\n\n    .brand-name {\n      font-size: 15px;\n      font-weight: 700;\n      color: #fff;\n      letter-spacing: 0.3px;\n    }\n\n    .brand-tag {\n      font-size: 11px;\n      color: var(--bamboo-green);\n      font-family: var(--mono);\n      background: var(--bamboo-green-glow);\n      border: 1px solid rgba(52, 211, 153, 0.25);\n      padding: 1px 7px;\n      border-radius: 4px;\n    }\n\n    .header-controls {\n      display: flex;\n      align-items: center;\n      gap: 14px;\n      font-family: var(--mono);\n      font-size: 12px;\n    }\n\n    .live-indicator {\n      display: flex;\n      align-items: center;\n      gap: 6px;\n      color: var(--bamboo-green);\n      font-weight: 600;\n    }\n\n    .live-dot {\n      width: 7px;\n      height: 7px;\n      border-radius: 50%;\n      background: var(--bamboo-green);\n    }\n\n    .pause-btn {\n      background: #1a251e;\n      border: 1px solid var(--card-border);\n      color: var(--text-muted);\n      padding: 3px 8px;\n      border-radius: 4px;\n      font-family: var(--mono);\n      font-size: 11px;\n      cursor: pointer;\n    }\n\n    .pause-btn:hover {\n      color: #fff;\n      border-color: var(--bamboo-green);\n    }\n\n    .pause-btn.paused {\n      background: rgba(251, 191, 36, 0.15);\n      border-color: var(--amber);\n      color: var(--amber);\n      font-weight: bold;\n    }\n\n    .stat-text {\n      color: var(--text-muted);\n    }\n\n    /* Main Stack */\n    main {\n      display: flex;\n      flex-direction: column;\n      gap: 20px;\n    }\n\n    .section-header {\n      display: flex;\n      justify-content: space-between;\n      align-items: center;\n      margin-bottom: 8px;\n    }\n\n    .section-label {\n      font-size: 11px;\n      font-weight: 700;\n      text-transform: uppercase;\n      letter-spacing: 1px;\n      color: var(--text-muted);\n    }\n\n    .filter-indicator {\n      font-family: var(--mono);\n      font-size: 11px;\n      color: var(--text-muted);\n      cursor: pointer;\n      transition: color 0.15s ease;\n    }\n\n    .filter-indicator.active {\n      color: var(--bamboo-green);\n    }\n\n    .filter-indicator.active:hover {\n      text-decoration: underline;\n    }\n\n    /* Section 1: Anchored Swarm Cards */\n    .node-grid {\n      display: grid;\n      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));\n      gap: 14px;\n    }\n\n    .node-card {\n      background: var(--card-bg);\n      border: 1px solid var(--card-border);\n      border-radius: 6px;\n      padding: 14px;\n      display: flex;\n      flex-direction: column;\n      gap: 8px;\n      cursor: pointer;\n      user-select: none;\n      transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;\n      position: relative;\n    }\n\n    .node-card:hover {\n      border-color: var(--card-border-active);\n      background: #162019;\n    }\n\n    .node-card.locked {\n      border-left: 3px solid rgba(52, 211, 153, 0.7);\n    }\n\n    .node-card.selected {\n      border-color: var(--bamboo-green) !important;\n      background: #18241c !important;\n      box-shadow: 0 0 0 1px var(--bamboo-green), 0 3px 12px var(--bamboo-green-glow);\n    }\n\n    .selected-tag {\n      font-size: 9px;\n      font-family: var(--mono);\n      font-weight: 700;\n      color: var(--bamboo-green);\n      background: var(--bamboo-green-glow);\n      border: 1px solid rgba(52, 211, 153, 0.4);\n      padding: 1px 5px;\n      border-radius: 3px;\n      letter-spacing: 0.5px;\n      text-transform: uppercase;\n    }\n\n    .card-row {\n      display: flex;\n      justify-content: space-between;\n      align-items: center;\n    }\n\n    .node-title {\n      font-size: 14px;\n      font-weight: 700;\n      color: #fff;\n    }\n\n    .badge {\n      font-size: 10px;\n      font-family: var(--mono);\n      font-weight: 600;\n      padding: 1px 6px;\n      border-radius: 3px;\n      text-transform: uppercase;\n    }\n\n    .badge-green {\n      background: var(--bamboo-green-glow);\n      color: var(--bamboo-green);\n      border: 1px solid rgba(52, 211, 153, 0.3);\n    }\n\n    .badge-amber {\n      background: rgba(251, 191, 36, 0.12);\n      color: var(--amber);\n      border: 1px solid rgba(251, 191, 36, 0.3);\n    }\n\n    .badge-red {\n      background: rgba(248, 113, 113, 0.12);\n      color: var(--red);\n      border: 1px solid rgba(248, 113, 113, 0.3);\n    }\n\n    .field-row {\n      display: flex;\n      justify-content: space-between;\n      font-size: 12px;\n    }\n\n    .field-label {\n      color: var(--text-muted);\n    }\n\n    .field-val {\n      font-family: var(--mono);\n      font-weight: 500;\n      color: #fff;\n    }\n\n    /* Section 2: Anchored Latest Pulse Inspector */\n    .pulse-box {\n      background: var(--card-bg);\n      border: 1px solid var(--card-border);\n      border-radius: 6px;\n      padding: 10px 14px;\n      display: flex;\n      align-items: center;\n      justify-content: space-between;\n      font-family: var(--mono);\n      font-size: 12px;\n    }\n\n    .pulse-title {\n      color: var(--text-muted);\n      font-size: 11px;\n      text-transform: uppercase;\n      letter-spacing: 0.5px;\n    }\n\n    .pulse-data {\n      display: flex;\n      gap: 16px;\n      color: var(--text);\n    }\n\n    .pulse-data span {\n      color: var(--bamboo-green);\n    }\n\n    /* Section 3: Sequence of Events Log */\n    .log-box {\n      background: var(--card-bg);\n      border: 1px solid var(--card-border);\n      border-radius: 6px;\n      padding: 12px 14px;\n      font-family: var(--mono);\n      font-size: 12px;\n      min-height: 120px;\n      display: flex;\n      flex-direction: column;\n      gap: 6px;\n    }\n\n    .log-row {\n      display: flex;\n      gap: 10px;\n      color: var(--text-muted);\n    }\n\n    .log-time {\n      color: var(--text-muted);\n      flex-shrink: 0;\n    }\n\n    .log-node {\n      color: var(--bamboo-green);\n      font-weight: 600;\n      flex-shrink: 0;\n    }\n\n    .log-text {\n      color: #e2e8f0;\n    }\n\n    .log-text.lock {\n      color: var(--bamboo-green);\n    }\n\n    .log-text.warn {\n      color: var(--amber);\n    }\n  </style>\n</head>\n<body>\n\n  <header>\n    <div class="brand">\n      <span class="brand-icon">\xf0\x9f\x8e\x8b</span>\n      <span class="brand-name">Bamboo Node</span>\n      <span class="brand-tag">GCS</span>\n    </div>\n    <div class="header-controls">\n      <div class="live-indicator">\n        <span class="live-dot" id="live-dot"></span>\n        <span id="conn-status">LIVE</span>\n      </div>\n      <button class="pause-btn" id="pause-btn" onclick="togglePause()">PAUSE</button>\n      <div class="stat-text" id="stat-frames">Frames: 0</div>\n      <div class="stat-text" id="stat-rate">0.0 Hz</div>\n    </div>\n  </header>\n\n  <main>\n    <!-- Section 1: Active Nodes in The Cupboard -->\n    <section>\n      <div class="section-header">\n        <div class="section-label">Active Swarm Nodes</div>\n        <div class="filter-indicator" id="node-filter-status" onclick="clearSelection()">All Nodes (Click card to filter)</div>\n      </div>\n      <div class="node-grid" id="node-grid">\n        <div style="color: var(--text-muted); padding: 12px; grid-column: 1/-1;">Waiting for optical frames...</div>\n      </div>\n    </section>\n\n    <!-- Section 2: Anchored Latest Pulse Inspector -->\n    <section>\n      <div class="section-header">\n        <div class="section-label">Latest Decoded Optical Pulse</div>\n      </div>\n      <div class="pulse-box">\n        <div class="pulse-title" id="pulse-title">WIRE LINK</div>\n        <div class="pulse-data" id="pulse-data">\n          <div>NODE: <span id="pulse-node">--</span></div>\n          <div>SEQ: <span id="pulse-seq">--</span></div>\n          <div>BEARING: <span id="pulse-az">--</span></div>\n          <div>CRC-8: <span id="pulse-crc">--</span></div>\n        </div>\n      </div>\n    </section>\n\n    <!-- Section 3: Actionable Sequence of Events -->\n    <section>\n      <div class="section-header">\n        <div class="section-label">Sequence of Events Log</div>\n        <div class="filter-indicator" id="log-filter-tag">All Nodes</div>\n      </div>\n      <div class="log-box" id="log-box">\n        <div style="color: var(--text-muted);">Awaiting operational state transitions...</div>\n      </div>\n    </section>\n  </main>\n\n  <script>\n    let isPaused = false;\n    let selectedNodeId = null;\n    let lastData = null;\n\n    const nodeGrid = document.getElementById(\'node-grid\');\n    const logBox = document.getElementById(\'log-box\');\n    const statFrames = document.getElementById(\'stat-frames\');\n    const statRate = document.getElementById(\'stat-rate\');\n    const connStatus = document.getElementById(\'conn-status\');\n    const pauseBtn = document.getElementById(\'pause-btn\');\n\n    const nodeFilterStatus = document.getElementById(\'node-filter-status\');\n    const pulseTitle = document.getElementById(\'pulse-title\');\n    const logFilterTag = document.getElementById(\'log-filter-tag\');\n\n    const pulseNode = document.getElementById(\'pulse-node\');\n    const pulseSeq = document.getElementById(\'pulse-seq\');\n    const pulseAz = document.getElementById(\'pulse-az\');\n    const pulseCrc = document.getElementById(\'pulse-crc\');\n\n    function togglePause() {\n      isPaused = !isPaused;\n      if (isPaused) {\n        pauseBtn.innerText = \'RESUME\';\n        pauseBtn.classList.add(\'paused\');\n      } else {\n        pauseBtn.innerText = \'PAUSE\';\n        pauseBtn.classList.remove(\'paused\');\n      }\n    }\n\n    function selectNode(id) {\n      if (selectedNodeId === id) {\n        selectedNodeId = null;\n      } else {\n        selectedNodeId = id;\n      }\n      if (lastData) {\n        render(lastData);\n      }\n    }\n\n    function clearSelection() {\n      if (selectedNodeId !== null) {\n        selectedNodeId = null;\n        if (lastData) {\n          render(lastData);\n        }\n      }\n    }\n\n    function cleanName(str) {\n      return (str || \'\').replace(\'MODE_\', \'\').replace(\'LOCK_\', \'\').replace(\'_\', \' \');\n    }\n\n    // In-place node elements cache\n    const nodeElements = new Map();\n\n    function updateNodes(activeNodes) {\n      if (!activeNodes || activeNodes.length === 0) {\n        if (nodeElements.size > 0) {\n          nodeGrid.innerHTML = \'<div style="color: var(--text-muted); padding: 12px; grid-column: 1/-1;">Waiting for optical frames...</div>\';\n          nodeElements.clear();\n        }\n        return;\n      }\n\n      const activeIds = new Set(activeNodes.map(n => n.node_id));\n\n      // Remove evicted nodes\n      for (const [id, el] of nodeElements.entries()) {\n        if (!activeIds.has(id)) {\n          el.remove();\n          nodeElements.delete(id);\n          if (selectedNodeId === id) {\n            selectedNodeId = null;\n          }\n        }\n      }\n\n      // If empty state exists, clear it\n      if (nodeElements.size === 0) {\n        nodeGrid.innerHTML = \'\';\n      }\n\n      // Update or create nodes in-place\n      activeNodes.forEach(node => {\n        const isLocked = node.lock_status === \'LOCK_HARD_LOCKED\';\n        const isSelected = selectedNodeId === node.node_id;\n        let badgeType = \'badge-green\';\n        if (node.mode === \'MODE_SEARCH\') badgeType = \'badge-amber\';\n        if (node.mode === \'MODE_DISPERSAL\') badgeType = \'badge-red\';\n\n        const lastSeenSec = ((Date.now() - (node.last_seen_ms || Date.now())) / 1000).toFixed(1);\n\n        if (!nodeElements.has(node.node_id)) {\n          // Create once\n          const card = document.createElement(\'div\');\n          card.className = `node-card ${isLocked ? \'locked\' : \'\'} ${isSelected ? \'selected\' : \'\'}`;\n          card.id = `node-card-${node.node_id}`;\n          card.onclick = () => selectNode(node.node_id);\n          card.innerHTML = `\n            <div class="card-row">\n              <div style="display: flex; align-items: center; gap: 8px;">\n                <span class="node-title">Bamboo Node #${node.node_id}</span>\n                <span class="selected-tag" id="sel-tag-${node.node_id}" style="display: ${isSelected ? \'inline-block\' : \'none\'};">ACTIVE</span>\n              </div>\n              <span class="badge ${badgeType}" id="badge-${node.node_id}">${cleanName(node.mode)}</span>\n            </div>\n            <div class="field-row">\n              <span class="field-label">Optical Lock</span>\n              <span class="field-val" id="lock-${node.node_id}" style="color: ${isLocked ? \'var(--bamboo-green)\' : \'var(--text)\'};">${cleanName(node.lock_status)}</span>\n            </div>\n            <div class="field-row">\n              <span class="field-label">Bearing</span>\n              <span class="field-val" id="bearing-${node.node_id}">${node.azimuth_mrad || 0} mrad</span>\n            </div>\n            <div class="field-row">\n              <span class="field-label">Sequence</span>\n              <span class="field-val" id="seq-${node.node_id}">#${node.sequence_num || 0}</span>\n            </div>\n            <div class="field-row">\n              <span class="field-label">Last Seen</span>\n              <span class="field-val" id="seen-${node.node_id}">${lastSeenSec}s ago</span>\n            </div>\n          `;\n          nodeGrid.appendChild(card);\n          nodeElements.set(node.node_id, card);\n        } else {\n          // Update in place without DOM re-layout\n          const card = nodeElements.get(node.node_id);\n          card.className = `node-card ${isLocked ? \'locked\' : \'\'} ${isSelected ? \'selected\' : \'\'}`;\n          \n          const selTag = document.getElementById(`sel-tag-${node.node_id}`);\n          if (selTag) {\n            selTag.style.display = isSelected ? \'inline-block\' : \'none\';\n          }\n          const badge = document.getElementById(`badge-${node.node_id}`);\n          if (badge) {\n            badge.className = `badge ${badgeType}`;\n            badge.innerText = cleanName(node.mode);\n          }\n          const lock = document.getElementById(`lock-${node.node_id}`);\n          if (lock) {\n            lock.style.color = isLocked ? \'var(--bamboo-green)\' : \'var(--text)\';\n            lock.innerText = cleanName(node.lock_status);\n          }\n          const bearing = document.getElementById(`bearing-${node.node_id}`);\n          if (bearing) bearing.innerText = `${node.azimuth_mrad || 0} mrad`;\n\n          const seq = document.getElementById(`seq-${node.node_id}`);\n          if (seq) seq.innerText = `#${node.sequence_num || 0}`;\n\n          const seen = document.getElementById(`seen-${node.node_id}`);\n          if (seen) seen.innerText = `${lastSeenSec}s ago`;\n        }\n      });\n    }\n\n    function render(data) {\n      if (isPaused) return;\n\n      // 1. Stats\n      if (data.stats) {\n        statFrames.innerText = `Frames: ${data.stats.total_frames || 0}`;\n        statRate.innerText = `${(data.stats.packet_rate_hz || 0).toFixed(1)} Hz`;\n      }\n\n      // Filter status header labels\n      if (selectedNodeId !== null) {\n        nodeFilterStatus.innerText = `Filtered: Node #${selectedNodeId} (Click to reset)`;\n        nodeFilterStatus.classList.add(\'active\');\n        pulseTitle.innerText = `WIRE LINK (NODE #${selectedNodeId})`;\n        logFilterTag.innerText = `Filtered: Node #${selectedNodeId}`;\n        logFilterTag.classList.add(\'active\');\n      } else {\n        nodeFilterStatus.innerText = \'All Nodes (Click card to filter)\';\n        nodeFilterStatus.classList.remove(\'active\');\n        pulseTitle.innerText = \'WIRE LINK (LATEST)\';\n        logFilterTag.innerText = \'All Nodes\';\n        logFilterTag.classList.remove(\'active\');\n      }\n\n      // 2. Active Nodes (In-place)\n      updateNodes(data.active_nodes);\n\n      // 3. Anchored Latest Pulse (scoped to selected node if filtered)\n      let pulse = null;\n      if (selectedNodeId !== null) {\n        const found = (data.active_nodes || []).find(n => n.node_id === selectedNodeId);\n        if (found) {\n          pulse = {\n            node_id: found.node_id,\n            sequence_num: found.sequence_num,\n            azimuth_mrad: found.azimuth_mrad,\n            crc8: found.crc8\n          };\n        } else if (data.latest_pulse && data.latest_pulse.node_id === selectedNodeId) {\n          pulse = data.latest_pulse;\n        }\n      } else {\n        pulse = data.latest_pulse;\n      }\n\n      if (pulse) {\n        pulseNode.innerText = `#${pulse.node_id}`;\n        pulseSeq.innerText = `#${pulse.sequence_num}`;\n        pulseAz.innerText = `${pulse.azimuth_mrad || 0} mrad`;\n        pulseCrc.innerText = `0x${(pulse.crc8 || 0).toString(16).toUpperCase().padStart(2, \'0\')} OK`;\n      } else {\n        pulseNode.innerText = \'--\';\n        pulseSeq.innerText = \'--\';\n        pulseAz.innerText = \'--\';\n        pulseCrc.innerText = \'--\';\n      }\n\n      // 4. Actionable Events Log (filtered to selected node if active)\n      let eventsToDisplay = data.events || [];\n      if (selectedNodeId !== null) {\n        eventsToDisplay = eventsToDisplay.filter(e => e.node_id === selectedNodeId);\n      }\n\n      if (eventsToDisplay.length > 0) {\n        logBox.innerHTML = eventsToDisplay.map(e => {\n          let textClass = \'log-text\';\n          if (e.level === \'LOCK\') textClass += \' lock\';\n          if (e.level === \'WARN\') textClass += \' warn\';\n          return `\n            <div class="log-row">\n              <span class="log-time">${e.time}</span>\n              <span class="log-node">N#${e.node_id}</span>\n              <span class="${textClass}">${e.message}</span>\n            </div>\n          `;\n        }).join(\'\');\n      } else {\n        logBox.innerHTML = `<div style="color: var(--text-muted);">No events recorded${selectedNodeId !== null ? \' for Node #\' + selectedNodeId : \'\'}.</div>`;\n      }\n    }\n\n    // Connect SSE\n    function connect() {\n      const evt = new EventSource(\'/events\');\n      evt.onopen = () => {\n        connStatus.innerText = \'LIVE\';\n        connStatus.style.color = \'var(--bamboo-green)\';\n      };\n      evt.onmessage = (e) => {\n        try {\n          lastData = JSON.parse(e.data);\n          render(lastData);\n        } catch (err) {}\n      };\n      evt.onerror = () => {\n        connStatus.innerText = \'OFFLINE\';\n        connStatus.style.color = \'var(--amber)\';\n      };\n    }\n    connect();\n  </script>\n</body>\n</html>\n'

    monitor = SwarmMonitor(node_ttl_sec=args.ttl)
    GCSRequestHandler.monitor = monitor

    # Parse UDP addr
    u_host, u_port_str = args.listen.split(":")
    u_port = int(u_port_str)

    # Start UDP listener thread
    udp_thread = threading.Thread(target=run_udp_listener, args=(monitor, u_host, u_port), daemon=True)
    udp_thread.start()

    # Demo mode generator if requested
    if args.demo:
        def run_demo():
            seq = 0
            while True:
                time.sleep(0.2)
                seq += 1
                # Mode=FORMATION_LOCK, Lock=HARD_LOCKED, ACK=True
                st = 0x02 | (0x03 << 2) | 0x10
                wire = bytes([PREAMBLE, SYNC_WORD, 1, seq & 0xFF, st, crc8(bytes([1, seq & 0xFF, st]))])
                monitor.ingest_frame(wire)
        demo_thread = threading.Thread(target=run_demo, daemon=True)
        demo_thread.start()

    # Parse HTTP addr
    h_host, h_port_str = args.http.split(":")
    h_port = int(h_port_str)

    httpd = HTTPServer((h_host, h_port), GCSRequestHandler)
    print("=" * 60)
    print("   NEURON CUPBOARD: TACTICAL GROUND CONTROL STATION (GCS)")
    print(f"   HTTP Dashboard: http://localhost:{h_port}")
    print(f"   UDP Ingest:     {args.listen}")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down GCS...")
        httpd.server_close()


if __name__ == "__main__":
    main()
