# Start a plan

The app shows the page `Start a plan` when the data directory is empty or does not exist. A data
directory is empty when it holds no input file and no revision. Other files, such as a folder
`lost+found`, do not count. The page replaces the other pages and the navigation until a plan
exists. The sidebar then holds only the switches of the mode and the [language](index.md#language).

The page gives three choices: an example, the quick start, or an export of your plan. The log of
the revisions names the first revision `example`, `quick start` or `import` with the name of the
zip. A plan that you start on this page opens in simple mode (see
[Simple and advanced mode](index.md#simple-and-advanced-mode-and-features)).

## The examples

Each example copies its data into the data directory. Then the Overview opens. All names and
amounts are made up. There are two examples:

- `Start from the simple example` starts a small plan to learn the app. The person is 31, single,
  and an employee with about 70,000 € a year and a bonus of 10%. She pays into a company pension
  from her salary (Entgeltumwandlung), an Altersvorsorgedepot from 2027 and an ETF savings plan of
  500 € a month. She rents a flat, is in the statutory health insurance (GKV) and pays no church
  tax. Her spending is about the average of a person who lives alone in Germany. She wants to stop
  working early. The plan has three scenarios: `Mit 55 aufhören`, `Arbeiten bis 67` and
  `Teilzeit ab 40`. On the Overview, `Find when to stop working` finds the earliest month that
  keeps the chance to run out of money low. The parts of the app that the example does not use,
  such as property or gold, are off. The [Features](features.md) page turns them on.
- `Start from the full example` starts the plan of a made-up engineer. The person was born in
  1986, has one child and private health insurance (PKV), rents a home and owns a rented-out flat
  with a loan. It uses every feature of the app in seven scenarios.

The simple example is in German: the names of its scenarios, assets, cashflows, phases and spending
categories, and the notes of its scenarios. The full example is in English. The data of an example
keeps its language when you change the language of the app.

`Their scenarios` on the page lists the scenarios of both examples with their notes.

The dates of the examples are fixed. Their simulation starts in October 2026, and their values
date from then. If you start from one in a later month, the Overview offers the roll forward and
marks the values as old. `Their dates` on the page says the same.

## The quick start

The quick start writes your plan from a few numbers. Only the date of birth is necessary. A field
that you leave empty adds nothing, and an amount of 0 adds nothing too. You can add the rest later
on the pages Assets, Cashflows and Scenarios.

Type your date of birth first: the button `Start my plan` is off without it, and a line below the
field says so. Type the day first with dots, such as `20.05.1986`, or in the order year, month,
day, such as `1986-05-20`. The app does not read digits without dots, such as `20051986`, because
the order is not clear. Below the field, the app shows the date in words with your age, for example
`Born 20 May 1986, age 40.` Read it to make sure that the app read the date correctly. The date must
be from 1900-01-01 to today.

The other fields:

- `Sex`: for the life table. Without a choice, the plan takes male.
- `Gross salary per month €`: your salary before tax and social insurance, without a bonus. The
  plan writes the salary `Gehalt`, which pays in the phase `work`.
- `Spending per month €`: all that you spend in a month, with the rent. The plan writes one expense
  `Lebenshaltung` in the category `Leben`. On the Cashflows page you can split it into categories.
- `Savings today €`: the value of your funds and shares. The plan writes one equity asset `Depot`.
  Its cost basis is the same value, so the tax counts no gain in it yet.
- `Cash today €`: the balance of your current account, as the cash asset `Girokonto`.
- `Pension points so far`: the Rentenpunkte of your Renteninformation, the yearly letter of the
  Deutsche Rentenversicherung.
- `Pension insurance since (year)`: the year of your first contribution to the statutory pension
  insurance. The plan writes it as `person.rv_since`. If the points are empty, the app estimates
  them: for each year since then, the points of a year of your salary of today, up to the
  contribution ceiling. A line below the field shows the estimate. Your Renteninformation has the
  exact number. If you type a salary but neither the points nor the year, the line says that the
  pension counts only the points that the salary earns in the plan, from now on.
- `Savings plan per month €`: the savings plan `Sparplan` into the depot, in the phase `work`.
- `Private health insurance (PKV)`: off means the statutory health insurance (GKV). If you turn it
  on, add your premium on the Cashflows page as an expense with its part of the health insurance.
  Then the subsidy of your employer and the tax count it.

With a salary or points, the plan also writes the pension `Rente` in the phase `retired`. Its
value of a point is the current Rentenwert of the tax year. The names are German, as in the simple
example.

Every plan of the quick start holds:

- the date of birth, in `assumptions.yaml`, and `tax.pkv`
- the current month as the simulation start
- the four return classes that every plan needs (equity, fixed income, cash and property), with
  the values of the example
- the four phases of a new plan (see [Assumptions](assumptions.md))
- one scenario `Plan`, which the app opens with. It is in the phase `work` from the start and in
  `retired` from the month in which you are 67. That change has the id `retired`, so `Find when to
  stop working` on the Overview can move it. If you are 67 or older, the scenario is in `retired`
  from the start. Then the salary and the savings plan do not pay, and a line below the fields
  says so. To use them, add a phase of work on the Scenarios page.
- every feature off in `app.yaml`, because the plan uses none. The caption below the button lists
  them. The [Features](features.md) page turns a feature on.

With a salary, the Overview opens next: `Find when to stop working` tells you by when you can stop.
Without a salary, or if you are 67 or older, the Assumptions page opens. Make sure that the person
and the markets are correct. Then add your assets on the Assets page, your income and spending on
the Cashflows page, and the phases of your life on the Scenarios page. Then explore your plan on the
[Explorer](explorer.md) page and compare its scenarios.

## An export

Use an export to move your plan into a new instance, or to restore a backup. Make the export on
the old instance, on the page [Export and import](transfer.md) or with `dagobert export`.

1. Upload the zip under `Choose a Dagobert export (.zip)`.
2. Make sure that the table lists the files of your plan. Each file is new here, so its action is
   `add`.
3. Push `Import N files`. Then the Overview opens and says what the import did.

If the export holds its change history (the revisions), the data directory takes it, and the
history of your plan stays. Without it, the import is the first revision.

## On the command line

The command `dagobert init` starts an example or an empty plan:

- `dagobert init --example starter` copies the simple example.
- `dagobert init --example` copies the full example. `dagobert init --example engineer` does the
  same.
- `dagobert init --born 1985-03-14` writes an empty plan: the plan of the quick start with the date
  of birth alone. Without `--born`, the command asks for the date of birth.

`--data` names the data directory, as for the other commands. A data directory that holds a plan
stays as it is, and the command stops with a message. So does a file in place of the directory,
and a date of birth before 1900 or after today. Other commands, such as `dagobert run`, stop
with a message on an empty data directory and name `dagobert init`. The command
`dagobert import <zip>` imports an export into an empty data directory.

## If the start fails

The page shows `Not started:` and the reason. Nothing changed in that case. Usually the app cannot
write into the data directory. In the container, the user of the app must own the data directory.
If Docker made the directory for a bind mount, it belongs to `root`: make it yourself before the
first start, as the README says. On Windows, use a folder in your user folder that OneDrive does
not synchronize, as [Install Dagobert on Windows](../install/windows.md) says.
