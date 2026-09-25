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
                     │ Autonomous Agent Loop  │◄───┐
                     │ (Diagnose ➔ Plan ➔ Act) │    │ Retry /
                     └───────────┬────────────┘    │ Alternate
                                 │                 │
               ┌─────────────────┴────────────────┐│
               ▼                                  ▼│
     [ Diagnosis Tools ]                [ Action Proposal ]
     - check_service_status                       │
     - get_metrics                                ▼
     - query_logs                    ┌─────────────────────────┐
     - get_deployment_history        │ Non-LLM Guardrail Layer │
                                     │ (Deterministic Engine)  │
                                     └────────────┬────────────┘
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                              [ VETOED ]                   [ ALLOWED ]
                                    │                           │
                                    ▼                           ▼
                        [ Structured Escalation ]      [ Mock Environment ]
                        - Blast radius protection      - restart_service
                        - Tier-1 DB isolation          - rollback_deployment
                        - SRE handoff memo             - scale_replicas
                                                                │
                                                                ▼
                                                       [ Health Verified? ]
                                                       ├─ YES ➔ RESOLVED
                                                       └─ NO  ➔ Loop / Escalate
```

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
Average Agent Steps Per Incident    : 3.00
=============================================================
```

---

## Project Structure

```
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
│   ├── state.py            # Session state and auditable step trace
│   ├── confidence.py       # Deterministic signal convergence scoring
│   ├── llm_client.py       # Resilient client with rate-limiting & exponential backoff
│   └── simulated_client.py # Scripted expert SRE client for offline dry-runs
├── escalation/
│   └── handoff.py          # Structured Markdown incident handoff memo generator
├── eval/
│   ├── benchmark.py        # Automated test harness runner
│   └── metrics.py          # Accuracy, False Action Rate, and table renderer
├── tests/                  # Pytest unit tests for all modules
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
# Run a single incident simulation with full audit trace
python main.py --scenario INC-001 --simulated

# See Tier-1 Database Guardrail Veto in action
python main.py --scenario INC-004 --simulated

# Run the complete benchmark evaluation suite
python main.py --eval --simulated
```

### 3. Run Live with Free Groq or OpenAI
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set your free Groq API key:
   ```ini
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_groq_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```
3. Run live:
   ```bash
   python main.py --scenario INC-001
   python main.py --eval
   ```

### 4. Run Unit Test Suite
```bash
pytest
```
