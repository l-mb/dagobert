"""The options of a run and the runs of scenarios, which the CLI, the explorer and the workers of
its process pool share: a worker unpickles `Options` without the CLI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from dagobert import series
from dagobert.engine.simulation import horizon_months, simulate
from dagobert.loader import load_plan
from dagobert.mortality import load_life_table, survival_curve
from dagobert.returns import make_provider
from dagobert.scenariofiles import scenario_labels

if TYPE_CHECKING:
    from pathlib import Path

    from dagobert.result import RunResult

ModelName = Literal["fixed", "montecarlo", "historical"]
DATA_ENV = "DAGOBERT_DATA"
WORKERS_ENV = "DAGOBERT_WORKERS"


@dataclass(frozen=True)
class Options:
    data: Path
    out: Path
    model: ModelName
    paths: int
    seed: int
    mortality: bool

    def run_one(self, scenario: Path, overrides: dict[str, Any] | None = None) -> RunResult | None:
        """None for an abstract scenario."""
        plan = load_plan(self.data, scenario, overrides)
        if plan.scenario.abstract:
            return None
        provider = make_provider(self.model, plan, self.data, paths=self.paths, seed=self.seed)
        months = horizon_months(plan.assumptions)
        result = simulate(plan, provider.sample(months), provider.name)
        if self.mortality:
            result.survival = survival_curve(
                load_life_table(series.life_table().path),
                plan.assumptions.person,
                result.months[0],
                months,
            )
        return result

    def run_all(self, scenarios: list[Path]) -> list[RunResult]:
        """The concrete ones of `scenarios`, once each, named apart: two of one name take their
        file stems too (`scenario_labels`). The stems differ: `run` refuses two files of one."""
        ran = {s.stem: r for s in dict.fromkeys(scenarios) if (r := self.run_one(s)) is not None}
        labels = scenario_labels({stem: r.scenario for stem, r in ran.items()})
        return [replace(r, scenario=labels[stem]) for stem, r in ran.items()]
