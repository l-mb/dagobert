# Flows: Monte Carlo variant

Waits: build it only if the fixed run is missed. The Flows page shows whole stretches, the
run rate of payments every n months and the settlement by the months that earn. Left open
from the short-phase list: a first partial year carries the Vorabpauschale and the interest
tax of the whole year in its few months (a start in October puts the tax of that year into
three months). The whole-stretch view dilutes it. A ledger per month and path needs gigabytes, a
sum per phase and path about 20 MB. Medians of single items do not add up, so average the
paths around the median surplus, as `RunResult.balance` does with `MEDIAN_BAND`. It
matters only for what depends on returns: capital gains tax, withdrawals, spending cuts,
care, a conditional sale.
