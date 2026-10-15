# Features

A feature is a part of life that a plan can model, such as gold and crypto, property or children.
The page `Features` in the section Setup switches each feature on or off. A feature that is off
is hidden on every page: its pages, tabs, asset kinds, event types, fields, columns and sliders.
This makes the app smaller when your plan does not need a part.

The switches are in the file `app.yaml` of your data directory. So they apply on every device that
opens your plan, in simple and in advanced mode. The mode is different: each browser keeps its own
mode. See [Simple and advanced mode, and features](index.md#simple-and-advanced-mode-and-features).

A plan of the [quick start](start-a-plan.md#the-quick-start) begins with every feature off. The
simple example begins with the ten features off that it does not use.

## Switch a feature off or on

1. Open the page `Features`.
2. Turn off the switch of each part that your plan does not model. Turn on a part that you need.
   The list below the switches shows each change, for example `gold and crypto on → off`.
3. Press `Save` at the top of the page.

The save changes only `app.yaml`. A switch never changes your other data. If you turn a feature
on again, everything that it hid shows again.

The help of each switch tells what it hides. On a phone the help shows below the switch.

## A part that your plan uses stays on

If your plan holds data of a feature, its switch is on and locked. Below the switch, `In use:`
names up to three places, for example `assets.yaml: coins (gold)` or `history.csv: 12 rows`. To
switch the feature off, first remove that data on its page.

Only data that acts counts. A key at its default, for example `children: 0`, does not lock a
switch. A value in the column `check every (months)` of an asset is data of Records. The column
`deductible` of a PKV premium belongs to no feature: it is the share of the premium that the income
tax takes.

If `app.yaml` lists such a feature as off, the app shows its parts anyway. This can happen after
an import or after an edit of the file by hand. The page then shows `Switched off in app.yaml, but
in use: it shows anyway.` The next `Save` removes the feature from the list.

If another device or another tab changes `app.yaml` while you change a switch, the page shows a
warning and `Save` stays off. Press `Discard my edits` to see the switches as the file holds them
now.

## The features

| Feature | Off hides | Still acts when off |
|---|---|---|
| Records | the Snapshot and Spend pages, the trades and prices of securities, the column `update_every` | nothing |
| Gold and crypto | the asset kinds gold and crypto, the event `buy`, their sliders, `crypto_capital_from` | nothing |
| Property, rental and loans | the asset kinds property and loan, the events `buy_property` and `repay`, the stream columns `property`, `after_sale_of` and `repays`, `refinance_rate` | nothing |
| Self-employment | the stream kind of a self-employed profit, the column `hebesatz`, the tax options of self-employment | nothing |
| Children | your children, `alleinerziehend`, childcare as a deduction | the care insurance surcharge for the childless |
| Inheritance and gifts | your relatives and their gifts before the start, the events `inheritance` and `gift` | nothing |
| Job loss | the stream kind ALG1, the event `severance` | nothing |
| Disability | the risk of disability, the stream kind of a BU policy and the tab `disability insurance` | nothing |
| Deductions and Basisrente | the Werbungskosten, the column `deduct` of an expense, a Basisrente, the event `fund_policy` | the Arbeitnehmer-Pauschbetrag |
| Spending rules beyond the cut | the increase of the spending rule, its ceiling, the spending by age, VPW | nothing: the cut stays in simple and advanced mode |
| Long-term care | the risk of long-term care and its sliders | nothing |
| Allocation and glide path | the allocation, its glide path and their sliders | the surplus goes into equity |

The switch `Invest the rest` of the Explorer belongs to no feature.
