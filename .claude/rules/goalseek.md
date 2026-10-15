---
paths:
  - "src/dagobert/goalseek.py"
  - "tests/test_goalseek.py"
---

# Goal seek

The goal seek of the explorer, its levers and `Apply to sliders`: rule `explorer`. The buttons of
the Overview: rule `overview`.

- `src/dagobert/goalseek.py`: the value of one `Dial` at which P(broke by 90) meets a target. A dial
  sets override paths to its value times a weight: a slider (`Knob.dial`, across the slider range,
  one slider step as resolution) or `spending`, the one factor `scale.spending` (weight: its value
  in the plan). Its `label` and `format` are words, no part of its identity (`compare=False`): the
  explorer keeps the answers by the dial (rule `explorer`).
- Under VPW (rule `spending`; owner 7) `spending` is the floor dial instead: `FLOOR` (`Spending
  floor`), `FLOOR_PATH` (`spending.vpw.floor`) at weight 1, from 0 to the largest of twice
  `monthly`, `FLOOR_LEAST` (5,000 €) and the floor, in steps of `FLOOR_STEP` (50 €), `PER_MONTH`:
  the highest guaranteed flexible spending at the target. VPW spends a share of the wealth, so a
  factor on the plan or on `growth` hardly moves P(broke); the floor does. `scale.categories` stays
  the dial of the other rules. A caller tells the floor dial by its weights (`outlook._allowed`).
- `edge` runs both ends, takes the one with the lower P(broke) as safe and narrows towards the
  other, so it assumes one crossing: it comes in from the safe end and returns the last value
  before the first step that misses the target, and a value further in may meet it again. Equal
  ends mean no effect, for example an event id that a scenario lacks, also when the chance moves
  between them (`stop`: `the seek finds no effect`). Each round runs as many values as the
  explorer's process pool has workers (about 25 runs, 3 s at 500 paths); `progress` takes the
  share of the rounds done after the ends and after each round (`rounds`: the most that narrow
  the range to one step), for the progress bars of the Explorer and the Overview (`runs.tick`).
- `seek` runs with `mortality=False`, as `sensitivity.run`: P(broke by 90)
  (`RunResult.p_broke_by_age`) and the medians of `Outcome` count every path, the survival
  overlay weights only `p_broke_alive` and `shortfall`. So the answer is the P(broke)@90 of the
  tiles and the table (`runs.options`, `mortality=True`), and the runs skip the life table; the
  manual says so beside both seeks.
- The age (rule `charts`): a plan that ends before 90 takes the chance at its last month, one that
  starts after 90 at its first, and the words name that age. `seek` sets `Found.age` from
  `Outcome.ages` of its runs (no dial moves the end of a plan), so each answer names the age of
  its own runs (`stop`, `seek.seek_answer`, `outlook._allowed`). The target (`seek.Target.of`, in
  the explorer and on the Overview) names the age that every chosen run takes it at, else 90 with
  the runs at another age in its help (`report.taken_at`, as the summary; a decision). A label
  before a run, the help of a savings slider (`knobs._savings_knobs`, by the plan of the first
  chosen scenario), takes `broke_age`: the months of the plan as the engine counts them
  (`Person.age` up to `horizon_months`) through `result.age_at`.
- `work` (a decision): the `shift` of the id of the change out of the last phase that pays a salary
  or a profit, whole months, the month without the sliders as origin, the age in the text
  (`Dial.born`; `Dial.month` gives both, for the tile of the Overview). The shift moves only the
  items of the id (`loader.adjust`): its events move along (a severance, a lump sum, a `write_off`),
  the later changes stay, and so do the dates of the streams, `start`, `end` and an `add_stream` or
  `end_streams` of another id. So a stretch of a phase pays while a stream of `EARNED` pays in it by
  those dates (`_pays` as the engine: the events of a month in file order, an `end_streams` ends by
  name or tag what runs by then; `_Pay.during`), in one of its `phases` (none: every phase), with an
  amount, at no `factor` and no `scale.salary` of 0 (`engine.core.pays`, which the spending rule
  takes for the first month, rule `engine`): with the kind and the phases alone, a job that an
  `end_streams` ends in the month it starts moved the pension, for a flat P(broke).
- The change stops the streams of that stretch that do not pay in the next phase and run up to it,
  or that an `end_streams` of the id ends. With none it raises `NoChangeError` (`does not stop the
  pay`, with the date of each). The month runs from the start of that phase or of the run (no event
  of the id before the start: the plan refuses it, rule `plan`) to the next change, age `WORK_AGE`,
  and the latest own end of the stopped streams when each has one (beyond it the pay does not move).
  So the order of the changes stays (a tie takes the later item, `Scenario.phase_at`). A change into
  the phase that holds already changes nothing and may share the id while it follows the change
  before the next one, by list position as `loader.adjust` sorts (`own`): a repeat before it moved
  past the change before at the earliest month, for years of pay that the plan lacks. It raises
  `NoChangeError` with the sentence for a scenario without such a change (it names a stream without
  `phases` that keeps the last phase paid), before the start, without an id (the sentence names the
  Phases tab, which gives a row that it saves an id, rule `scenarios`), or whose id another entry
  shares outside that stretch. `stop_help` says what it moves in plain words, on the Overview and in
  the explorer; `stop` is the answer of both.
- Words (rule `i18n`): `NoChangeError` (a `ValueError`, its message English) carries the reason as
  data, `NoChange`: a message of the catalogue with its fields, which the explorer caches and says
  per page (`said`). `STOP`, `SPENDING`, `FLOOR` and the format `PER_MONTH` (context `sprintf`) are
  messages that a cached dial keeps in English; `stop_help` (`STOP_MOVES`), `Dial.text`,
  `Found.limit` and `stop` speak the language of the page.
