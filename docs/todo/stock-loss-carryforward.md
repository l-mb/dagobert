# Stock loss carryforward

Waits for the BVerfG.

A loss from the sale of single stocks goes into a pot of its own: §20 Abs. 6 S. 4 EStG lets it
offset only gains from single stocks, not from ETFs. The BVerfG decides on this rule under
2 BvL 3/21 (BFH VIII R 11/18) and announced the decision for 2026. Tax assessments are
provisional on this point since 2022. If the court strikes the rule, such a loss offsets every
capital gain, and the engine needs the carryforward as an input: the start value of its general
loss pot (`Engine.losses`).
