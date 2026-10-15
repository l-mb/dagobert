# Mobile leftovers: device check

Needs a phone on a deployed instance. Check: the numeric keypad of a grid cell has `-`,
`,` and `.`; the keyboard does not cover the lower rows of the Spend grid; the month select box
and the scenario pills open no keyboard; a new category typed in a grid row is not capitalized;
pull-to-refresh is off; edits survive three minutes in another app. Fix what fails.

Seen only in emulation so far:
- A tap on a chart counted as touch and mouse, so plotly saw a double click and reset the axes.
  `ui.chart` sets `doubleClick: False` on phones. Check that a tap reads the value and keeps
  the axes, and that the unified hover label of the explorer charts reads well.
- The pinned first column of the explorer's difference table.
- A positive amount typed into an expense or loan cell shows as positive until Save. The guard
  and the block header already show the stored negative value.
- A value typed again unchanged in a Cashflows grid enables Save with nothing listed (the write
  changes nothing).
- The `Spent` field of the quick add and the number fields of `Add a trade` open the decimal
  keypad, and the `Category` field of the quick add starts without a capital (`ui.keyboard`).
- The date of `Add a trade` can be cleared once set.
- A pinch on a bar chart (outflows, income, Spend difference) does not zoom it: the bars no
  longer fix their axes, since the desktop zooms them by drag again.
- A picked outflow group scrolls its streams into view once the page settles, also on the first
  load of the Overview, and a scroll by hand before that cancels it.
- The ⚠ before an asset that needs an update (Snapshot) may show as a color emoji on Android.
- Streamlit parts that measure below 40 px in emulation, though their box is 40 px: the
  chevron of a select box and of an expander (32 x 38), the input inside a text field (36 to 38
  px: `Category`, `Spent` and the month of the quick add). Check that a tap on them works.
