import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify

try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

from mock_infra.environment import MockEnvironment
from mock_infra.models import AlertEvent, AlertSeverity
from mock_infra.scenarios import SCENARIOS, inject_scenario
from agent.llm_client import ResilientLLMClient
from agent.simulated_client import ScriptedScenarioLLMClient
from agent.loop import IncidentResponseAgent
from agent.graph import LangGraphIncidentAgent
from agent.state import IncidentSessionState


def create_app(simulated: bool = True, engine: str = "raw") -> Flask:
    """
    Creates the Flask HTTP webhook application for real-time alert ingestion.
    """
    app = Flask(__name__)
    app.config["SIMULATED"] = simulated
    app.config["ENGINE"] = engine.lower()

    if HAS_CORS:
        CORS(app, resources={r"/*": {"origins": "*"}})

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        return response

    @app.route("/", methods=["GET"])
    def index():
        """Interactive dashboard landing page."""
        scenarios_html = "".join([
            f"""<div class="scenario-card">
                <div class="scenario-header">
                    <span class="badge {'badge-escalate' if sc.must_escalate else 'badge-remediate'}">
                        {'Must Escalate' if sc.must_escalate else 'Auto Remediate'}
                    </span>
                    <strong>{sc.id}</strong>: {sc.name}
                </div>
                <p class="scenario-desc">{sc.description}</p>
                <div class="scenario-meta">Target: <code>{sc.target_service}</code></div>
                <button class="trigger-btn" onclick="triggerAlert('{sc.id}')">⚡ Trigger Incident</button>
            </div>"""
            for sc in SCENARIOS.values()
        ])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Incident-Response Agent | Webhook Server</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #111827;
            --border: #1f2937;
            --text: #f3f4f6;
            --muted: #9ca3af;
            --primary: #3b82f6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', sans-serif;
            padding: 30px 20px;
            line-height: 1.5;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 8px; color: #fff; }}
        .subtitle {{ color: var(--muted); font-size: 0.95rem; }}
        .status-bar {{
            display: flex;
            gap: 15px;
            margin-top: 15px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
        }}
        .status-pill {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 6px;
        }}
        .pulse {{ color: var(--success); }}
        .endpoints {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }}
        .endpoints h2 {{ font-size: 1.1rem; margin-bottom: 12px; }}
        .ep-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
        .ep-item {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .method {{
            background: #1e3a8a;
            color: #93c5fd;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .method-post {{ background: #064e3b; color: #6ee7b7; }}
        a {{ color: var(--primary); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .scenarios-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 14px;
            margin-top: 20px;
        }}
        .scenario-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            transition: border-color 0.2s;
        }}
        .scenario-card:hover {{ border-color: #374151; }}
        .scenario-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .scenario-desc {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 10px; }}
        .scenario-meta {{ font-size: 0.8rem; color: #6b7280; margin-bottom: 12px; }}
        .scenario-meta code {{ color: #e5e7eb; }}
        .badge {{
            font-size: 0.72rem;
            padding: 2px 8px;
            border-radius: 999px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-remediate {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .badge-escalate {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
        .trigger-btn {{
            background: #2563eb;
            color: white;
            border: none;
            padding: 7px 14px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .trigger-btn:hover {{ background: #1d4ed8; }}
        .trigger-btn:disabled {{ background: #374151; cursor: not-allowed; }}
        #output-panel {{
            margin-top: 30px;
            background: #030712;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px;
            display: none;
        }}
        #output-panel h3 {{ font-size: 1rem; margin-bottom: 10px; color: #60a5fa; }}
        #output-content {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.82rem;
            color: #d1d5db;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Autonomous Infra/DevOps Incident-Response Agent</h1>
            <p class="subtitle">Real-time Alert Ingestion & Autonomous Diagnostic-Remediation Webhook Daemon</p>
            <div class="status-bar">
                <div class="status-pill"><span class="pulse">●</span> Server: Online</div>
                <div class="status-pill">Engine: {app.config["ENGINE"].upper()}</div>
                <div class="status-pill">Mode: {"SIMULATED" if app.config["SIMULATED"] else "LIVE LLM"}</div>
            </div>
        </header>

        <section class="endpoints">
            <h2>Available API Endpoints</h2>
            <ul class="ep-list">
                <li class="ep-item">
                    <span class="method">GET</span>
                    <a href="/health">/health</a>
                    <span style="color: var(--muted);">- System health check & daemon state</span>
                </li>
                <li class="ep-item">
                    <span class="method">GET</span>
                    <a href="/api/v1/scenarios">/api/v1/scenarios</a>
                    <span style="color: var(--muted);">- Full catalog of testable incident archetypes</span>
                </li>
                <li class="ep-item">
                    <span class="method method-post">POST</span>
                    <span>/api/v1/alert</span>
                    <span style="color: var(--muted);">- Ingest webhook (JSON / Prometheus Alertmanager)</span>
                </li>
            </ul>
        </section>

        <h2>Test Incident Ingestion Live</h2>
        <p class="subtitle" style="margin-bottom: 10px;">Click any incident below to trigger the agent and watch it remediate or escalate:</p>
        <div class="scenarios-grid">
            {scenarios_html}
        </div>

        <div id="output-panel">
            <h3 id="output-title">Incident Response Result</h3>
            <pre id="output-content">Running...</pre>
        </div>
    </div>

    <script>
        async function triggerAlert(scenarioId) {{
            const panel = document.getElementById('output-panel');
            const content = document.getElementById('output-content');
            const btns = document.querySelectorAll('.trigger-btn');
            btns.forEach(b => b.disabled = true);

            panel.style.display = 'block';
            content.textContent = '⏳ Triggering incident [' + scenarioId + ']... Agent diagnosing and acting...';
            panel.scrollIntoView({{ behavior: 'smooth' }});

            try {{
                const res = await fetch('/api/v1/alert', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ scenario_id: scenarioId }})
                }});
                const data = await res.json();
                content.textContent = JSON.stringify(data, null, 2);
            }} catch (err) {{
                content.textContent = 'Error: ' + err.message;
            }} finally {{
                btns.forEach(b => b.disabled = false);
            }}
        }}
    </script>
</body>
</html>"""
        return html, 200, {"Content-Type": "text/html"}

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "infra-incident-response-agent",
            "engine": app.config["ENGINE"],
            "simulated": app.config["SIMULATED"],
            "timestamp": datetime.now().isoformat(),
        }), 200

    @app.route("/api/v1/scenarios", methods=["GET"])
    def list_scenarios():
        """Lists all supported incident scenarios."""
        sc_list = [
            {
                "id": sc.id,
                "name": sc.name,
                "target_service": sc.target_service,
                "description": sc.description,
                "must_escalate": sc.must_escalate,
            }
            for sc in SCENARIOS.values()
        ]
        return jsonify({"scenarios": sc_list, "total": len(sc_list)}), 200

    @app.route("/api/v1/alert", methods=["POST", "OPTIONS"])
    def ingest_alert():
        """
        Receives an alert webhook, triggers the autonomous incident response agent,
        and returns the resolution/escalation response.
        """
        if request.method == "OPTIONS":
            return "", 204

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Allow query-param or body override for engine / simulated
        raw_simulated = data.get("simulated", request.args.get("simulated", app.config["SIMULATED"]))
        if isinstance(raw_simulated, bool):
            req_simulated = raw_simulated
        else:
            req_simulated = str(raw_simulated).lower() in ("true", "1", "yes")

        req_engine = str(data.get("engine") or request.args.get("engine") or app.config["ENGINE"]).lower()

        print(f"[*] Ingest alert received payload: {data}")

        env = MockEnvironment()
        scenario_id = data.get("scenario_id") or data.get("scenarioId") or data.get("id") or data.get("scenario")

        if scenario_id and scenario_id in SCENARIOS:
            alert = inject_scenario(env, scenario_id)
        elif "alerts" in data and isinstance(data["alerts"], list) and len(data["alerts"]) > 0:
            # Standard Prometheus Alertmanager webhook format
            first_alert = data["alerts"][0]
            labels = first_alert.get("labels", {})
            annotations = first_alert.get("annotations", {})
            svc_name = labels.get("service", "web-api")
            sev_str = labels.get("severity", "CRITICAL").upper()
            sev = getattr(AlertSeverity, sev_str, AlertSeverity.CRITICAL)

            # Reset baseline and customize service
            env.reset_to_baseline()
            alert = AlertEvent(
                alert_id=labels.get("alertname", f"ALT-{int(datetime.now().timestamp())}"),
                service=svc_name,
                alert_type=labels.get("alertname", "unknown_alert"),
                severity=sev,
                trigger_metric=annotations.get("metric", "error_rate_percent"),
                trigger_value=float(annotations.get("value", 50.0)),
                threshold=float(annotations.get("threshold", 10.0)),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                summary=annotations.get("summary", "Automated alert received from Alertmanager webhook"),
            )
        else:
            # Direct JSON alert payload
            svc_name = data.get("service", "web-api")
            sev_str = data.get("severity", "CRITICAL").upper()
            sev = getattr(AlertSeverity, sev_str, AlertSeverity.CRITICAL)
            env.reset_to_baseline()
            try:
                alert = AlertEvent(
                    alert_id=data.get("alert_id", f"ALT-{int(datetime.now().timestamp())}"),
                    service=svc_name,
                    alert_type=data.get("alert_type", "custom_alert"),
                    severity=sev,
                    trigger_metric=data.get("trigger_metric", "error_rate_percent"),
                    trigger_value=float(data.get("trigger_value", 50.0)),
                    threshold=float(data.get("threshold", 10.0)),
                    timestamp=data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    summary=data.get("summary", "Custom alert received via webhook"),
                )
            except Exception as e:
                return jsonify({"error": f"Invalid alert format: {e}"}), 400

        # Select LLM client
        if req_simulated:
            client = ScriptedScenarioLLMClient(scenario_id=scenario_id or "INC-001")
        else:
            client = ResilientLLMClient()

        # Instantiate agent based on engine
        if req_engine == "langgraph":
            agent = LangGraphIncidentAgent(llm_client=client)
        else:
            agent = IncidentResponseAgent(llm_client=client)

        # Run agent loop
        session: IncidentSessionState = agent.run(env, alert)

        # Build response JSON
        is_recovered = env.is_service_recovered(session.target_service)
        final_diag = session.final_diagnosis
        if not final_diag:
            thoughts = [t.thought for t in session.trace if t.thought]
            final_diag = thoughts[-1] if thoughts else alert.summary

        # Steps / trace representation supporting both snake_case and camelCase
        steps_list = [
            {
                "step": t.step_number,
                "step_number": t.step_number,
                "stepNumber": t.step_number,
                "tool": t.tool_called or "conclusion",
                "tool_called": t.tool_called or "conclusion",
                "toolCalled": t.tool_called or "conclusion",
                "name": t.tool_called or "conclusion",
                "action": t.tool_called or "diagnosis",
                "thought": t.thought or "",
                "description": t.thought or (f"Executed {t.tool_called}" if t.tool_called else "Diagnosis complete"),
                "details": t.thought or (json.dumps(t.observation) if t.observation else ""),
                "guardrail": t.guardrail_decision or ("PERMITTED" if t.tool_called else "COMPLETED"),
                "guardrail_decision": t.guardrail_decision or ("PERMITTED" if t.tool_called else "COMPLETED"),
                "guardrailDecision": t.guardrail_decision or ("PERMITTED" if t.tool_called else "COMPLETED"),
                "status": t.guardrail_decision or ("PERMITTED" if t.tool_called else "COMPLETED"),
                "timestamp": t.timestamp,
                "time": t.timestamp,
            }
            for t in session.trace
        ]

        # Problems / symptoms representation
        problem_text = alert.summary or f"Alert triggered on {session.target_service}"
        problems_list = [problem_text]
        if alert.trigger_metric:
            problems_list.append(f"{alert.trigger_metric} = {alert.trigger_value} (threshold {alert.threshold})")

        # Actions list formatted as strings so React can render {action} directly without crashing
        formatted_actions = []
        for a in session.actions_attempted:
            act_name = a.get("action", "action")
            msg = a.get("message", "")
            if msg:
                formatted_actions.append(f"{act_name}: {msg}")
            else:
                formatted_actions.append(f"{act_name} on {a.get('service', session.target_service)}")

        actions_list = [
            {
                "action": a.get("action", ""),
                "name": a.get("action", ""),
                "service": a.get("service", session.target_service),
                "success": a.get("success", True),
                "status": "success" if a.get("success", True) else "failed",
                "is_healthy_after": a.get("is_healthy_after", True),
                "message": a.get("message", ""),
            }
            for a in session.actions_attempted
        ]

        escalation_data = session.escalation_report.model_dump() if session.escalation_report else None
        escalation_memo_text = session.escalation_report.to_markdown() if session.escalation_report else None

        response_payload = {
            "incident_id": session.alert_id,
            "incidentId": session.alert_id,
            "target_service": session.target_service,
            "targetService": session.target_service,
            "status": session.status.value,
            "service_recovered": is_recovered,
            "serviceRecovered": is_recovered,
            "is_recovered": is_recovered,
            "isRecovered": is_recovered,
            "confidence_score": session.confidence_score,
            "confidenceScore": session.confidence_score,
            "confidence": session.confidence_score,
            "percentage": round(session.confidence_score * 100),
            "steps_taken": session.step_count,
            "stepsTaken": session.step_count,

            # Diagnosis fields
            "final_diagnosis": final_diag,
            "finalDiagnosis": final_diag,
            "diagnosis": final_diag,
            "root_cause": final_diag,
            "rootCause": final_diag,
            "hypothesis": final_diag,

            # Problem / symptoms fields
            "problem": problem_text,
            "problems": problems_list,
            "symptom": problem_text,
            "symptoms": problems_list,
            "unresolved_symptoms": problems_list,
            "unresolvedSymptoms": problems_list,
            "detected_issues": problems_list,
            "detectedIssues": problems_list,
            "issues": problems_list,
            "summary": problem_text,
            "alert_summary": problem_text,
            "alertSummary": problem_text,

            # Steps / Trace fields (every possible alias)
            "steps": steps_list,
            "trace": steps_list,
            "trace_summary": steps_list,
            "traceSummary": steps_list,
            "execution_trace": steps_list,
            "executionTrace": steps_list,
            "timeline": steps_list,

            # Actions attempted fields (strings for React child rendering)
            "actions_attempted": formatted_actions,
            "actionsAttempted": formatted_actions,
            "actions_taken": formatted_actions,
            "actionsTaken": formatted_actions,
            "actions": formatted_actions,
            "action_objects": actions_list,
            "action_details": actions_list,

            # Escalation report & memo
            "escalation_report": escalation_data,
            "escalationReport": escalation_data,
            "escalation_memo": escalation_memo_text,
            "escalationMemo": escalation_memo_text,
            "memo": escalation_memo_text,
        }

        return jsonify(response_payload), 200

    return app


def run_server(port: int = 8000, host: str = "0.0.0.0", simulated: bool = True, engine: str = "raw"):
    """Starts the webhook listener daemon."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    app = create_app(simulated=simulated, engine=engine)
    print(f"\n[*] Starting Incident Response Webhook Server on http://{host}:{port}")
    print(f"[*] Health check : http://localhost:{port}/health")
    print(f"[*] Scenarios API: http://localhost:{port}/api/v1/scenarios")
    print(f"[*] Alert Webhook: http://localhost:{port}/api/v1/alert (POST)\n")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()
