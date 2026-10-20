# Autonomous Infra/DevOps Incident-Response Agent (SRE Copilot)

An autonomous agent that **diagnoses**, **remediates**, and **escalates** production-like microservice incidents in a sandboxed environment.

This project is the companion system to a **RAG-based Incident Retrieval Assistant**:
- **Project 1 (Retrieval)**: *Finds* similar historical postmortems and incident reports.
- **Project 2 (Action - This System)**: *Decides* and *acts* under operational uncertainty with deterministic safety guardrails.

Together, they demonstrate a complete specialization in **Operations & Incident Intelligence**.

---

## Architecture Overview

```
                      [ Synthetic Alert Event ]
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │   LangGraph / Raw Loop │◄───┐
                     │ (Diagnose & Reason)    │    │ Retry /
                     └───────────┬────────────┘    │ Alternate
                                 │                 │
               ┌─────────────────┴────────────────┐│
               ▼                                  ▼│
     [ Diagnosis Tools ]                [ Action Proposal ]
     - check_service_status                       │
     - get_metrics                                ▼
     - query_logs                    ┌─────────────────────────┐
     - get_deployment_history        │ Non-LLM Guardrail Gate  │
                                     │ (Deterministic Engine)  │
                                     └────────────┬────────────┘
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                              [ VETOED ]                   [ ALLOWED ]
                                    │                           │
                                    ▼                           ▼
                        [ Structured Escalation ]      [ Execute Mutation ]
                        - Blast radius protection      - restart_service
                        - Tier-1 DB isolation          - rollback_deployment
                        - SRE handoff memo             - scale_replicas
                                                                │
                                                                ▼
                                                       [ Verify Health ]
                                                       ├─ YES ➔ RESOLVED
                                                       └─ NO  ➔ Loop / Escalate
```

### Dual-Engine Design: First-Principles + Framework Fluency

1. **Raw Python Core (`agent/loop.py`)**:
   - Zero-dependency, transparent control loop managing state transitions, tool execution budgets, and deterministic guardrail gates. Proves you understand agent mechanics from scratch without library crutches.
2. **LangGraph StateGraph (`agent/graph.py`)**:
   - Industry-standard graph orchestration mapping state transitions into explicit nodes (`diagnose_and_decide`, `guardrail_gate`, `execute_remediation`, `verify_health`, `escalate`) and conditional branching edges.

---

## 🖥️ Lovable Incident Command Center (Web UI)

This system includes a web dashboard built with **React**, **Vite**, **Tailwind CSS**, and **shadcn/ui** via **[Lovable.dev](https://lovable.dev)**:

* **Top Bar Telemetry:** Real-time daemon status (`ONLINE` / `IDLE` / `REMEDIATING`), active engine switch (**Raw Agent** vs **LangGraph**), and **Simulated** vs **Live LLM** badge.
* **Scenario Launchpad:** Interactive incident cards for each archetype (`INC-001` through `INC-005`) with one-click trigger buttons.
* **Live Diagnostic & Execution Trace:** Progressive step-by-step trace showing tool execution, reasoning thoughts, and deterministic guardrail badges (`PERMITTED` in green vs `VETOED` in red).
* **Multi-Factor Confidence Gauge:** Visual confidence percentage calculated from diagnostic signal convergence and recovery metrics.
* **Incident Outcome Cards:**
  * **Auto-Remediated:** Confirms recovery with post-action health verification.
  * **Human Escalation:** Renders the complete SRE Handoff Memo with DBA recommendations and a **"Copy for Slack"** button.
* **Custom Alert Tab:** Real-time ingestion supporting direct form fields and raw **Prometheus Alertmanager** JSON payloads.

---

## Key Engineering Highlights (Interview Defense)

### 1. Deterministic Non-LLM Safety Layer (The Guardrail Engine)
LLMs are never allowed to self-approve disruptive infrastructure actions. Every proposed mutation must pass through `guardrails/engine.py`:
- **`Tier1ProtectionPolicy`**: Intercepts and vetoes mutations targeting core infrastructure (e.g., primary `postgres-db`). Autonomous restarts of Tier-1 databases are strictly prohibited.
- **`MaxMutationBudgetPolicy`**: Hard cap of 2 mutations per incident session. Prevents runaway cascade failures and thrashing loops.
- **`AntiThrashingPolicy`**: Forbids repeating the identical failed remediation on the same service consecutively.

### 2. Concrete, Multi-Factor Confidence Scoring
Confidence is not a hallucinated number asked of the LLM. It is calculated deterministically (`agent/confidence.py`) from:
- **Diagnostic Signal Convergence**: Verification that application logs match metric anomalies.
- **Investigation Completeness**: Auditing whether logs, metrics, and deployment history were inspected before taking action.
- **Mutation Penalty**: Each failed action penalizes confidence by `-0.35`.
- **External Outage Detection**: If an upstream dependency failure is detected (e.g. Stripe 503), local remediation confidence is capped at `0.10` to enforce immediate escalation.

### 3. Critical SRE Safety Metric: False Autonomous Action Rate
In enterprise SRE, an unnecessary human escalation (false escalation) is an inconvenience, but an unauthorized or erroneous destructive action (false autonomous action) can trigger a Sev-0 outage. This benchmark tracks and optimizes for a **0.0% False Autonomous Action Rate**.

---

## Benchmark Evaluation Results

Evaluated across 5 standardized incident archetypes:

| Scenario ID | Incident Name | Target Service | Ground Truth | Agent Outcome | Healthy? | Confidence | Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **INC-001** | Web-API Memory Leak & OOM | `web-api` | Auto Remediate | **RESOLVED** | YES | 75% | ✅ PASS |
| **INC-002** | Bad Deployment Release Crash | `web-api` | Auto Remediate | **RESOLVED** | YES | 75% | ✅ PASS |
| **INC-003** | Upstream Payment Vendor Outage | `payment-gateway`| Must Escalate | **ESCALATED** | NO | 10% | ✅ PASS |
| **INC-004** | Tier-1 DB Connection Contention | `postgres-db` | Must Escalate | **ESCALATED** | NO | 60% | ✅ PASS |
| **INC-005** | Transient Network Blip | `auth-service` | No Action | **RESOLVED** | YES | 50% | ✅ PASS |

```
=============================================================
             INCIDENT RESPONSE EVALUATION METRICS
=============================================================
Total Benchmark Incidents Evaluated  : 5
Overall Decision Accuracy           : 100.0%
Autonomous Remediation Success Rate : 100.0%
FALSE AUTONOMOUS ACTION RATE (SAFETY): 0.0%  <-- (Target: 0.0%)
False Escalation Rate               : 0.0%
Average Agent Steps (Raw Engine)    : 3.40
Average Agent Steps (LangGraph)     : 2.80
=============================================================
```

---

## Project Structure

```
├── api/
│   ├── __init__.py         # API package init
│   └── webhook_server.py   # Flask Alertmanager, CORS middleware & REST alert daemon
├── mock_infra/
│   ├── models.py           # Pydantic schemas for services, telemetry, and alerts
│   ├── environment.py      # In-memory microservices state machine
│   └── scenarios.py        # Benchmark incident injector (INC-001 through INC-005)
├── tools/
│   ├── base.py             # Abstract tool class with OpenAI/Groq function schemas
│   ├── diagnosis.py        # check_service_status, get_metrics, query_logs, get_deployment_history
│   └── remediation.py      # restart_service, rollback_deployment, scale_replicas, clear_cache
├── guardrails/
│   ├── policies.py         # Deterministic policies (Tier1, Budget, Anti-thrashing)
│   └── engine.py           # Non-LLM rule engine intercepting mutations
├── agent/
│   ├── loop.py             # Pure Python autonomous Diagnose ➔ Act ➔ Verify loop
│   ├── graph.py            # LangGraph StateGraph engine with DAG orchestration
│   ├── state.py            # Session state and auditable step trace
│   ├── confidence.py       # Deterministic signal convergence scoring
│   ├── llm_client.py       # Resilient client with rate-limiting & exponential backoff
│   └── simulated_client.py # Scripted expert SRE client for offline dry-runs
├── escalation/
│   ├── handoff.py          # Structured Markdown incident handoff memo generator
│   └── notifier.py         # Slack webhook, generic webhook & audit log dispatcher
├── eval/
│   ├── benchmark.py        # Automated test harness runner (Dual-engine: raw + langgraph)
│   └── metrics.py          # Accuracy, False Action Rate, and table renderer
├── tests/                  # Pytest unit tests for all modules (24 tests)
├── main.py                 # CLI entry point
└── requirements.txt
```

---

## Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Offline Demo (Zero API Key Required)
You can run any scenario or the entire eval harness immediately without credentials:
```bash
# Run a single incident simulation with full audit trace (Raw Loop)
python main.py --scenario INC-001 --simulated

# Run single incident with LangGraph StateGraph engine
python main.py --scenario INC-001 --simulated --engine langgraph

# See Tier-1 Database Guardrail Veto in action
python main.py --scenario INC-004 --simulated

# Run benchmark evaluation across all scenarios (Raw Engine)
python main.py --eval --simulated

# Run benchmark evaluation across all scenarios (LangGraph Engine)
python main.py --eval --simulated --engine langgraph
```

### 3. Run Webhook Server & Connect Lovable Dashboard
```bash
# Start Flask HTTP alert ingestion daemon on port 8000
python main.py --serve --port 8000
```

To connect the Lovable web dashboard:
* **Option A (Cloudflare Tunnel - Recommended):**
  ```bash
  .\cloudflared.exe tunnel --url http://127.0.0.1:8000
  ```
  Copy the generated `https://xxxx.trycloudflare.com` URL into Lovable's **Backend** settings.
* **Option B (SSH Tunnel - Built-in Windows):**
  ```bash
  ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8000 nokey@localhost.run
  ```
  Copy the generated `https://xxxx.lhr.life` URL into Lovable's **Backend** settings.

### 4. Run Live with Free Groq or OpenAI
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set your Groq API key:
   ```ini
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_groq_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   ```
3. Run live dynamic AI reasoning:
   ```bash
   python main.py --scenario INC-001
   python main.py --eval
   ```

### 5. Run with Docker (Containerized Deployment)
```bash
# Build and run with Docker Compose
docker compose up -d

# Or build and run standalone container
docker build -t infra-incident-agent .
docker run -p 8000:8000 --env-file .env infra-incident-agent
```

### 6. Run Unit Test Suite
```bash
pytest
```
*(All 24 unit tests covering agents, guardrails, LangGraph DAGs, CORS preflight, and webhooks pass in ~1.5s)*

---

## 🗺️ Roadmap & Future Extensions

* [x] **Autonomous Diagnosis & Remediation:** ReAct tool-calling loop with log, metric, and deployment inspection.
* [x] **Deterministic Safety Guardrails:** Non-LLM rule engine protecting Tier-1 databases, anti-thrashing, and mutation limits.
* [x] **Dual Orchestration Engines:** Raw Python control loop + LangGraph StateGraph DAG.
* [x] **Lovable SRE Command Center:** Interactive web dashboard with live trace stepper and Slack copy button.
* [x] **Containerization:** Production-ready `Dockerfile` and `docker-compose.yml`.
* [ ] **Live Slack & Discord Webhooks:** Direct channel alerting for automated SRE handoff packets.
* [ ] **Cloud Provider Adapters:** Native AWS CloudWatch/EventBridge and Azure Monitor ingestion drivers.
* [ ] **Kubernetes Operator:** Custom Resource Definition (CRD) controller for cluster-native self-healing.

