"""HTML and console reporting for RunResult sequences."""

from __future__ import annotations

from dagobert.report.anatomy import anatomy_figure
from dagobert.report.balance import (
    Observed,
    balance_figure,
    lasting_figure,
    lasting_reading,
    lasting_shares,
)
from dagobert.report.comparison import broke_probability_figure, comparison_figure
from dagobert.report.fan import difference_figure, liquid_fan_figure
from dagobert.report.flows import flow_figure
from dagobert.report.page import write_html
from dagobert.report.sensitivity import sensitivity_figure
from dagobert.report.summary import (
    BROKE_ALIVE,
    BROKE_AT,
    COLUMNS,
    DIFFERENCE_NOTE,
    TOTAL_AT,
    SummaryRow,
    changes,
    console_table,
    difference_table,
    print_summary,
    summary_columns,
    summary_row,
    summary_table,
    taken_at,
)

__all__ = [
    "BROKE_ALIVE",
    "BROKE_AT",
    "COLUMNS",
    "DIFFERENCE_NOTE",
    "TOTAL_AT",
    "Observed",
    "SummaryRow",
    "anatomy_figure",
    "balance_figure",
    "broke_probability_figure",
    "changes",
    "comparison_figure",
    "console_table",
    "difference_figure",
    "difference_table",
    "flow_figure",
    "lasting_figure",
    "lasting_reading",
    "lasting_shares",
    "liquid_fan_figure",
    "print_summary",
    "sensitivity_figure",
    "summary_columns",
    "summary_row",
    "summary_table",
    "taken_at",
    "write_html",
]
