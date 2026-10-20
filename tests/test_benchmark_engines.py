import pytest
from eval.benchmark import BenchmarkRunner


def test_benchmark_runner_raw_simulated():
    runner = BenchmarkRunner(use_simulated=True, engine="raw")
    # Run only 2 scenarios to keep execution fast and lightweight
    summary = runner.run_benchmark(scenario_ids=["INC-001", "INC-004"])

    assert summary.total_incidents == 2
    assert summary.accuracy_rate == 100.0
    assert summary.false_autonomous_action_rate == 0.0


def test_benchmark_runner_langgraph_simulated():
    runner = BenchmarkRunner(use_simulated=True, engine="langgraph")
    # Run only 2 scenarios to keep execution fast and lightweight
    summary = runner.run_benchmark(scenario_ids=["INC-001", "INC-004"])

    assert summary.total_incidents == 2
    assert summary.accuracy_rate == 100.0
    assert summary.false_autonomous_action_rate == 0.0
