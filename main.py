import os
import sys
import argparse

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mock_infra.environment import MockEnvironment
from mock_infra.scenarios import SCENARIOS, inject_scenario
from agent.llm_client import ResilientLLMClient
from agent.loop import IncidentResponseAgent
from agent.state import SessionStatus
from eval.benchmark import BenchmarkRunner


def print_banner():
    banner = """
========================================================================
   🤖 AUTONOMOUS INFRA/DEVOPS INCIDENT-RESPONSE AGENT (SRE COPILOT)
        Diagnose ➔ Guardrail Gate ➔ Remediate ➔ Verify ➔ Escalate
========================================================================
"""
    print(banner)


def check_api_key():
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "groq" and not os.getenv("GROQ_API_KEY"):
        print("\n⚠️  NOTICE: GROQ_API_KEY is not set in your .env file.")
        print("👉 You can get a 100% free key at: https://console.groq.com")
        print("👉 Add it to your `.env` file as: GROQ_API_KEY=gsk_...\n")
        return False
    elif provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  NOTICE: OPENAI_API_KEY is not set in your .env file.")
        print("👉 Add it to your `.env` file as: OPENAI_API_KEY=sk-...\n")
        return False
    return True


def run_single_incident(scenario_id: str, simulated: bool = False, engine: str = "raw"):
    if scenario_id not in SCENARIOS:
        print(f"Error: Unknown scenario ID '{scenario_id}'. Available: {list(SCENARIOS.keys())}")
        return

    scenario = SCENARIOS[scenario_id]
    print(f"\n📋 Loading Scenario [{scenario.id}]: {scenario.name}")
    print(f"📝 Description: {scenario.description}")
    print(f"🎯 Target Service: {scenario.target_service}")
    print(f"⚙️  Engine Mode   : {engine.upper()} ({'SIMULATED' if simulated else 'LIVE LLM'})\n")

    env = MockEnvironment()
    alert = inject_scenario(env, scenario_id)

    print(f"🚨 ALERT TRIGGERED:")
    print(f"   - ID: {alert.alert_id}")
    print(f"   - Severity: {alert.severity}")
    print(f"   - Metric: {alert.trigger_metric} = {alert.trigger_value} (Threshold: {alert.threshold})")
    print(f"   - Summary: {alert.summary}\n")

    print(f"🤖 Agent initiating autonomous diagnose-act-verify loop...\n")

    if simulated:
        from agent.simulated_client import ScriptedScenarioLLMClient
        client = ScriptedScenarioLLMClient(scenario_id=scenario_id)
    else:
        client = ResilientLLMClient()

    if engine.lower() == "langgraph":
        from agent.graph import LangGraphIncidentAgent
        agent = LangGraphIncidentAgent(llm_client=client)
    else:
        agent = IncidentResponseAgent(llm_client=client)

    session = agent.run(env, alert)

    print("=" * 60)
    print("                    AGENT EXECUTION AUDIT TRACE")
    print("=" * 60)
    for trace in session.trace:
        print(f"\n[Step {trace.step_number}] ⏱ {trace.timestamp}")
        if trace.thought:
            print(f"  🧠 Reasoning: {trace.thought.strip()}")
        if trace.tool_called:
            print(f"  🔧 Tool Call : {trace.tool_called}({trace.tool_arguments})")
        if trace.guardrail_decision:
            decision_badge = "🛡️ ALLOWED" if trace.guardrail_decision == "ALLOWED" else "🚨 VETOED BY GUARDRAIL"
            print(f"  {decision_badge}")
        if trace.observation:
            obs_preview = str(trace.observation)
            if len(obs_preview) > 300:
                obs_preview = obs_preview[:300] + "... [truncated]"
            print(f"  👁 Observation: {obs_preview}")

    print("\n" + "=" * 60)
    print("                      INCIDENT RESOLUTION SUMMARY")
    print("=" * 60)
    print(f"Outcome Status  : {session.status.value}")
    print(f"Steps Taken     : {session.step_count} / {session.max_steps}")
    print(f"Confidence Score: {session.confidence_score * 100:.1f}%")
    print(f"Service Healthy : {'YES ✅' if env.is_service_recovered(session.target_service) else 'NO ❌'}")

    if session.actions_attempted:
        print("\nMutations Attempted:")
        for a in session.actions_attempted:
            res_icon = "✅" if a.get("is_healthy_after") else "❌"
            print(f"  {res_icon} {a['action']} on {a['service']} - {a['message']}")

    if session.escalation_report:
        print("\n" + session.escalation_report.to_markdown())


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="Autonomous SRE Incident-Response Agent")
    parser.add_argument("--scenario", type=str, help="Run specific scenario (e.g. INC-001, INC-002, INC-003, INC-004, INC-005)")
    parser.add_argument("--eval", action="store_true", help="Run full benchmark evaluation across all scenarios")
    parser.add_argument("--simulated", action="store_true", help="Run in offline deterministic simulation mode (no API key required)")
    parser.add_argument("--engine", type=str, default="raw", choices=["raw", "langgraph"], help="Orchestration engine: 'raw' (pure Python) or 'langgraph'")
    args = parser.parse_args()

    if not args.simulated and not check_api_key():
        print("Please configure your .env file or run with `--simulated` for an offline demonstration.")
        print("Example:")
        print("  python main.py --scenario INC-001 --simulated")
        print("  python main.py --eval --simulated\n")
        return

    if args.eval:
        if args.simulated:
            runner = BenchmarkRunner(use_simulated=True)
        else:
            client = ResilientLLMClient()
            if args.engine == "langgraph":
                from agent.graph import LangGraphIncidentAgent
                agent = LangGraphIncidentAgent(llm_client=client)
            else:
                agent = IncidentResponseAgent(llm_client=client)
            runner = BenchmarkRunner(agent)
        summary = runner.run_benchmark()
        print(summary.render_table())
    elif args.scenario:
        run_single_incident(args.scenario, simulated=args.simulated, engine=args.engine)
    else:
        print("Available benchmark scenarios:")
        for sc_id, sc in SCENARIOS.items():
            print(f"  • {sc.id}: {sc.name} ({sc.target_service})")
        print("\nUsage:")
        print("  python main.py --scenario INC-001 --engine raw          # Pure Python raw loop")
        print("  python main.py --scenario INC-001 --engine langgraph    # LangGraph StateGraph engine")
        print("  python main.py --scenario INC-001 --simulated           # Offline simulated run")
        print("  python main.py --eval                                   # Full eval benchmark")


if __name__ == "__main__":
    main()
