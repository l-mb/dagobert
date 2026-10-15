# Elterngeld

Parental allowance (Elterngeld) replaces part of a parent's income for the first months after a
birth. The plan has no such benefit. Today the user enters it by hand as a stream of the approval
amount, marked not taxable. This item would pay it by rule, from the net income before the birth,
and apply the tax and insurance effects. The effects are the progression clause and the health and
care insurance of the benefit months. Value is one year of income for one parent. The design
review found four open high and medium points, so it is a separate item.

- Since the children item, Elterngeld is a stream of the approval amount with `taxable: false`, for
  twelve months from the birth. The progression clause on it is a documented gap (rule `children`).
- When built, the amount is computed by rule from the net income before the birth, with the
  statutory minimum and maximum, and the partner months.
- A generic `other_income` field with a progression flag is added. The same field serves sick pay
  and short-time work benefit.
- Before the build, the four review points are settled: the average income of §2b, the annual
  income reference (JAEG), maternity protection, and the offset against ALG1.
- The birth is in the `sabbatical` scenario of `engineer`, with the interim stream. No new
  scenario.

Legal basis: BEEG §§2 ff. (amount and months). Progression clause §32b Abs. 1 S. 1 Nr. 1 j EStG.
Compulsory health insurance during the benefit §192 Abs. 1 Nr. 2 SGB V.

Waits: the generic progression field on `other_income` and the four review points. The children
item is built: the birth in `sabbatical` and the `taxable: false` interim stream exist.
