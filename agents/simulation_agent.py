from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analytics.stress_testing import (
    StressTestResult,
    generate_custom_scenarios,
    get_builtin_stress_scenarios,
    parse_scenario_text,
    run_stress_test,
)


@dataclass
class SimulationAgentOutput:
    result: StressTestResult
    scenario_text: str


class SimulationAgent:
    def run(
        self,
        latest_record: pd.Series,
        revenue_drop_pct: float = 0.0,
        expense_increase_pct: float = 0.0,
        scenario_text: str | None = None,
    ) -> SimulationAgentOutput:
        if scenario_text:
            parsed_revenue_drop, parsed_expense_increase = parse_scenario_text(scenario_text)
            revenue_drop_pct = revenue_drop_pct or parsed_revenue_drop
            expense_increase_pct = expense_increase_pct or parsed_expense_increase

        result = run_stress_test(latest_record, revenue_drop_pct, expense_increase_pct)
        return SimulationAgentOutput(
            result=result,
            scenario_text=scenario_text or "Structured simulation input",
        )

    def get_builtin_scenarios(self) -> list[dict[str, float | str]]:
        """Expose built-in scenario presets."""
        return get_builtin_stress_scenarios()

    def generate_custom_scenarios(
        self,
        max_revenue_drop_pct: float,
        max_expense_increase_pct: float,
        count: int = 5,
    ) -> list[dict[str, float | str]]:
        """Generate bounded custom stress scenarios."""
        return generate_custom_scenarios(max_revenue_drop_pct, max_expense_increase_pct, count=count)
