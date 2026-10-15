# Realize gains beside the loss pots

The harvest (rule `harvest`) realizes gains each December within the tax-free room. It takes no
room at all while the §20 loss pot holds losses, and no tariff room while a Verlustvortrag (§10d)
is left. Both keep the engine simple and err towards more tax: a pot would offset the realized gain
first, so the room would hold more gain. On the example `engineer` the pot's room cost about
3,000 € of median wealth. The owner (2026-10-14): the full loss pot handling can come later.

- Idea: the room plus what the §20 pot offsets (`capital_gains_tax` takes the pot first, §20 Abs. 6
  EStG), and the tariff room less what the §10d pot would offset of the year's income.
- Also open: a harvest in a month other than December (a sale that a deficit forces, the month of
  a lump sum).
- Needs: a short design, then `tax.harvest_room`, `engine/settlement.py`, rule `harvest`, the
  tests of `test_harvest.py`.
