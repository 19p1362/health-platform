"""
Healthcare Orchestra — Dashboard Server (Flask)

Provides:
- REST API for agent status, patient data, analytics
- WhatsApp webhook endpoint for Twilio
- Dark-theme dashboard frontend (static)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread

from flask import Flask, jsonify, request, send_from_directory

# Layer imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config

logger = logging.getLogger("healthcare_orchestra.dashboard")

app = Flask(__name__, static_folder="static", static_url_path="")

# ── HealthBridge token cache ──
_hb_token = None
_hb_token_expires = 0


def _get_hb_token():
    global _hb_token, _hb_token_expires
    import time
    import requests

    if _hb_token and time.time() < _hb_token_expires:
        return _hb_token
    try:
        resp = requests.post(
            f"{config.HEALTHBRIDGE_API_URL}/api/v1/auth/login",
            json={"email": "admin@healthbridge.io", "password": "Admin2025!"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            _hb_token = data.get("access_token", "")
            _hb_token_expires = time.time() + 3000  # ~50 min
            return _hb_token
    except Exception as e:
        logger.error(f"HealthBridge auth: {e}")
    return ""


# ══════════════════════════════════════════════════════════
# Dashboard API
# ══════════════════════════════════════════════════════════


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/health")
def api_health():
    hb_ok = False
    import requests

    try:
        r = requests.get(f"{config.HEALTHBRIDGE_API_URL}/health", timeout=5)
        hb_ok = r.status_code == 200
    except Exception:
        pass

    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "healthbridge_connected": hb_ok,
        "agents_enabled": sum(1 for v in config.AGENTS.values() if v),
        "agents_total": len(config.AGENTS),
    })


@app.route("/api/stats")
def api_stats():
    """Aggregated stats from HealthBridge."""
    import requests

    token = _get_hb_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    stats = {
        "patients": 0,
        "medications": 0,
        "lab_results": 0,
        "adherence_rate": 0,
        "ingestion_logs": 0,
        "pending_follow_ups": 0,
        "active_claims": 0,
    }

    try:
        # Patient count from FHIR
        r = requests.get(
            f"{config.HEALTHBRIDGE_API_URL}/fhir/Patient?_summary=count",
            headers=headers, timeout=5
        )
        if r.status_code == 200:
            stats["patients"] = r.json().get("total", 0)
    except Exception:
        pass

    try:
        r = requests.get(
            f"{config.HEALTHBRIDGE_API_URL}/api/v1/ingest/logs?limit=1",
            headers=headers, timeout=5
        )
        if r.status_code == 200:
            stats["ingestion_logs"] = len(r.json())
    except Exception:
        pass

    return jsonify(stats)


@app.route("/api/patients")
def api_patients():
    import requests

    token = _get_hb_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    search = request.args.get("search", "")
    url = f"{config.HEALTHBRIDGE_API_URL}/fhir/Patient"
    if search:
        url += f"?name={search}"

    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            bundle = r.json()
            patients = []
            for entry in bundle.get("entry", []):
                res = entry.get("resource", {})
                name = res.get("name", [{}])[0]
                patients.append({
                    "id": res.get("id", ""),
                    "name": name.get("text", ""),
                    "gender": res.get("gender", ""),
                    "phone": next((t.get("value", "") for t in res.get("telecom", []) if t.get("system") == "phone"), ""),
                    "birth_date": res.get("birthDate", ""),
                })
            return jsonify({"patients": patients, "total": bundle.get("total", len(patients))})
    except Exception as e:
        logger.error(f"Patient query failed: {e}")

    return jsonify({"patients": [], "total": 0})


@app.route("/api/ingestion/logs")
def api_ingestion_logs():
    import requests

    token = _get_hb_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        r = requests.get(
            f"{config.HEALTHBRIDGE_API_URL}/api/v1/ingest/logs?limit=20",
            headers=headers, timeout=5
        )
        if r.status_code == 200:
            return jsonify(r.json())
    except Exception:
        pass

    return jsonify([])


@app.route("/api/agents/status")
def api_agents_status():
    """Return status of all 10 agents."""
    return jsonify({
        name: {
            "enabled": enabled,
            "interval_minutes": config.AGENT_INTERVALS.get(name, 60),
            "last_run": None,
        }
        for name, enabled in config.AGENTS.items()
    })


@app.route("/api/run/orchestrator", methods=["POST"])
def api_run_orchestrator():
    """Trigger orchestrator run on demand."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "master_orchestrator", "--once"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True, text=True, timeout=120,
        )
        return jsonify({
            "status": "completed" if result.returncode == 0 else "failed",
            "stdout": result.stdout[-500:],
            "stderr": result.stderr[-500:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({"status": "timeout"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


# ══════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    )
    port = config.DASHBOARD_PORT
    logger.info(f"Healthcare Orchestra Dashboard starting on port {port}")
    logger.info(f"  Dashboard:        http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)


if __name__ == "__main__":
    main()
