# Salary growth per phase

The Explorer has one growth slider per index (`knobs._growth_knobs`), and an index is global: every
salary row with `index: salary` follows it in every phase. A plan with a job now and another job
later needs a second index to let the two grow apart, for example a job without raises now and one
with raises later. The owner (2026-10-14): every phase with a salary could have its own growth
lever.

- Idea: a growth lever per phase with a salary or a profit, beside `Salary and profit in <phase>`
  in the group `Income`, as a `scale` of the growth of that phase (a real growth on top of the
  index of its rows, stepped each January from the start of the phase), so no input needs a second
  index.
- Open: how it composes with the index of a row (on top, or instead), its key in `scale`, the
  sensitivity and the goal seek (a lever and a dial), the migration of plans that use a second
  index for this today.
- Needs: a short design, then the engine (`income.py`, `profit.py`), the sliders and rule `engine`.
