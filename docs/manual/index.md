# User guide

This guide describes the pages of the Dagobert app, the models behind the results, and the files
of the data directory. The [README](../../README.md) tells you how to start the app. For Windows
and macOS, the install guides below give each step.

## The pages

If the data directory is empty, the app first shows [Start a plan](start-a-plan.md): start from a
simple example, from the full example, with the quick start, or from an export of your plan.

The navigation on the left has three sections. On a phone, the button at the top left opens it.
In simple mode, and for a part of life that is off, the navigation leaves out some pages. See
[Simple and advanced mode, and features](#simple-and-advanced-mode-and-features).

Track: what you have and what you spend.

- [Overview](overview.md): your net worth, the outlook of your plan, and what needs your attention.
- [Snapshot](snapshot.md): record the values of your accounts, and the prices of your securities.
- [Assets](assets.md): edit your assets, see the trades and returns of your securities, and
  [import the trades](assets.md#import-trades) from the export of your broker.
- [Cashflows](cashflows.md): edit your income and spending, and see them per phase of life.
- [Spend](spend.md): record what you spent each month, and compare it with the plan.

Plan: what-if questions.

- [Explorer](explorer.md): run scenarios, move the assumptions with sliders, and compare.
- [Flows](flows.md): see where the money of one scenario goes in each phase.

Setup: the data that the app needs.

- [Features](features.md): switch off the parts of life that your plan does not model, such as
  property or children.
- [Data](data.md): the external series, such as the consumer prices, and their sources.
- [Assumptions](assumptions.md): edit the facts about you and the assumptions of every scenario,
  such as the inflation, the returns and the tax.
- [Scenarios](scenarios.md): create, copy, rename and delete scenarios, and edit their phases.
- [Events of a scenario](events.md): edit the sales, payments and other events of a scenario, and
  leave out events that it takes from the scenario that it extends.
- [Overrides of a scenario](overrides.md): change assumptions, a salary or the items of the
  scenario that it extends for one scenario only.
- [Export and import](transfer.md): a zip of your data directory as a backup or as a copy to work
  on, and its import.

## The other documents

- [How the simulation works](models.md): what the app computes each month, the three models and the
  meaning of the results, such as P(broke).
- [Buy or rent](buy-or-rent.md): compare the purchase of a home with renting, in two scenarios.
- [Configuration reference](configuration.md): the input files of the data directory, field by
  field.
- [Adding a tax year](adding-a-tax-year.md): for contributors who add the legal values of a new
  year.
- [Install Dagobert on Windows](../install/windows.md) and
  [Install Dagobert on macOS](../install/macos.md): install and start the app without a container.

## Words in this guide

- Data directory: the folder that holds your inputs, your records and the revisions.
- Simulation start: the first month that the simulation computes. Every amount of your plan is in
  euros of this month.
- Stream: a payment that repeats, such as a salary, the rent or an insurance premium. Expenses
  are negative.
- Event: a change on one date, such as the sale of a flat, a severance payment or an inheritance.
- Phase: a period of your life, such as work, part time, a career break or retirement. You
  define your phases on the Assumptions page. A new plan has four: `Work` (a time with a job),
  `Unemployed` (a time with unemployment benefit, ALG1), `Career break` (any other time, such as
  a sabbatical) and `Retired` (a time with a pension). A stream can apply
  in some phases only. What a phase means comes from the streams that pay in it.
- Scenario: one version of your life: its phases, its events and the assumptions that it changes.
  A scenario can extend another scenario and change only some parts of it.
- Main scenario: the scenario of your plan. The Overview, the Cashflows page, the Flows page and
  the Spend page show it. Select it at the top of the Scenarios page, together with the other
  scenarios that the Explorer opens with, or with `Set as default` on the Explorer: its first
  scenario becomes the main scenario.
- Path: one possible future of the markets and of inflation. A Monte Carlo run computes many paths.
- Liquid net worth: cash, deposits, fixed income, shares and funds, gold and crypto, less the tax
  that a sale of them costs. Property and pension policies are not liquid.
- Broke: the liquid net worth is below zero. The money that you can spend ran out.
- Euros of the start: amounts that are corrected for inflation since the simulation start, so that
  they keep their buying power. Nominal euros are the amounts as paid on the day.
- Revision: a copy of the files that one save changed. The app keeps every revision.

## How the pages behave

- Money shows as `1.234.567 €`: a dot groups the thousands. A share or a rate shows in percent.
  Type it in percent too: type `2.5` for 2.5%.
- A page that edits your data has a button `Save` or `Record` at the top of the page. On the Spend
  page, `Save` sits below the grid. Near the table, a list shows each change before you save, with
  the old and the new value.
- If a change looks like a typing error, the list shows a warning and the button shows a `⚠`.
  Examples are a value set to zero, a changed sign, a value that more than doubles or falls below
  half, and a share above 100%. You can save anyway, because a large change can be correct.
- If a save fails, the page shows `Not saved:` and the reason. Nothing changed in that case.
- If an input file contains an error, a page that needs the file shows the file, the line and
  the problem instead of its content. Correct the file, then load the page again. The Scenarios
  page shows the problem of a scenario above its tabs, and you can correct the scenario there.
- Most pages show one sentence of help and fold the rest into a box, such as `How to read this`.
  The Explorer folds its long help texts on a phone only.
- On a phone every page works. A tap on a chart shows its values. On a desktop a click on a bar
  selects it, and you can drag to zoom.

## Simple and advanced mode, and features

Two settings make the app smaller. Neither one changes your data or the simulation.

The mode is a setting of your browser. Simple mode hides the settings for experts that your plan
does not use. Advanced mode shows everything. To change the mode, use the switch `Mode` at the end
of the sidebar, above the language switch. On a phone, the button at the top left opens the
sidebar. A cookie in your browser keeps your choice for the next visit. Without a choice, the app
opens in simple mode. The page [Start a plan](start-a-plan.md) has no switch of the mode: a plan
that you start there opens in the mode of your browser. Another browser or another device keeps
its own mode.

In simple mode the navigation leaves out these pages:

- Snapshot, until your plan holds a record of a value or a trade of a security.
- Spend, until your plan holds a record of what you spent.
- Data, until your plan holds a fetched or imported series.

If you open the address of a page that the navigation leaves out, for example from a bookmark, the
app shows `Page not found` and opens the Overview.

Simple mode also hides the asset kinds, the kinds of streams and the event types for experts that
your plan does not use, for example a term deposit or a write-off of shares. A table moves its
columns for experts that no row fills behind `All columns`. The
[Assumptions](assumptions.md#simple-mode) page and the tab `Overrides` of a scenario hide the fields
for experts that your plan does not set, and the [Scenarios](scenarios.md) page hides the tab
`Overrides` of a scenario without overrides. A note names what is hidden. A field, a tab or a table
with edits that you did not save keeps them when you switch the mode.

A feature is a part of life that a plan can model, such as gold and crypto, property, children or
long-term care. The [Features](features.md) page switches each feature on or off. A feature that
is off is hidden in both modes, on every device that opens your plan, because the switches are in
the file `app.yaml`.

One rule applies to both settings: what your plan uses always shows. If your plan holds a gold
asset, the app shows gold and crypto, also when that feature is off. So no setting hides a value
that acts in your plan. A key that your file sets to its default does not count as used, for
example `children: 0`. The defaults of a hidden field still act in the simulation, for example
the Teilfreistellung of 30% for an equity fund.

## Language

The app shows its pages in English or in German. On your first visit it uses the language of your
browser, and English if that is not German. To change the language, use the switch `Sprache ·
Language` at the end of the sidebar. A cookie in your browser keeps your choice for the next visit.

Every page is in German, with its help, its tables and its charts. Some text always stays in
English: the names and notes in your files, the examples, the problems of an input file, and the
words that Streamlit draws itself, such as the toolbar of a table and the file upload.

The report of the command line is in English. To get it in German, add `--lang de`, for example
`uv run dagobert run --lang de data/scenarios/*.yaml`. You can also set the environment variable
`DAGOBERT_LANG` to `de`. The summary that the command prints stays in English.
