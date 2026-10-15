# Existing Riester contracts

The engine models Riester contracts only under the rules of 2027 on. A contract concluded before
2027 keeps the old rules until its payout starts. Those rules give a basic allowance of 175 €, a
child allowance of 185 € or 300 € per child, a minimum contribution of 4 % of the last year's
pensionable income, and a tax deduction (Sonderausgabe) of up to 2,100 € a year. This item adds
those rules for old contracts, and the switch to the new funding. Value applies only to people with
an old contract. It extends the depot kind; it is not a new kind.

- Old contracts extend `AvDepot` with `concluded`, `paid`, `guarantee` and `switched`. A new kind
  would cost a tab, labels, references and a manual section.
- The contribution is `minimum` by default: exactly the minimum contribution, in start-year euros,
  rebased at each roll forward. A fixed number is also allowed.
- Only people insured in the statutory pension scheme are eligible: salary, ALG1, or self-employed
  with a pension insurance duty.
- An ALG1 month counts the benefit actually paid, not 80 % of the reference pay.
- The payout tops up to `guarantee` times the paid contributions.
- The switch to the new funding is an irrevocable declaration, or it happens by law when a new
  contract is concluded.

Legal basis: EStG §10a Abs. 1 and 2 (deduction), §§84 to 86 (basic and child allowance, minimum
contribution), §52 Abs. 50a EStG (transition, BGBl. 2026 I Nr. 156). Pensionable income in SGB VI.

Waits: nothing; the deductions are built (rule `deductions`). The Zulage and the room of §10a count
once per person on the contributions of all depots (`Income._contribute_av`), so an old contract
joins that sum with its own rules. The transition text of §52 Abs. 50a must be checked against the
current law before the build.
