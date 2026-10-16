---
paths:
  - "src/dagobert/locale/**"
  - "src/dagobert/i18n.py"
  - "src/dagobert/ui/*.py"
  - "src/dagobert/report/*.py"
  - "tests/german.py"
  - "tests/test_i18n.py"
  - "scripts/i18n"
---

# German glossary

The German of the app (rule `i18n`): one German word per English term on every page. A new term
gets its row with the unit that brings it.

Style: "du", lowercase (`du`, `dein`); buttons in the infinitive (`Speichern`, `Szenario anlegen`);
short active sentences; quotes „…"; after a colon a capital before a whole sentence (Duden D 89),
not before a fragment or an apposition; legal terms as the law writes them; a term of the report
(`P(broke)@90`, `Total@67`) stays as it is in the help; a number with a decimal comma and a no-break
space before `%` (`36,6 %`, `5,00`; euros `1.234.567 €` and ISO months as in English: rule
`money`). The page names of rule `i18n` win over this table: `Snapshot` stays English in German
text too (owner, issue #23: `auf der Seite Snapshot`), as do Explorer, Cashflows and Flows.

| English (app) | German | Note |
|---|---|---|
| net worth / liquid / illiquid / debt | Nettovermögen / liquide / gebunden / Schulden | help: „nach Abzug der Schulden"; `Nettovermögen` everywhere, as the page Assets is `Vermögen`; but `Liquides Vermögen` (liquid net worth, also `liquid` as a noun: a legend, a row; not „liquide Mittel") and `Gesamtvermögen` (total) |
| 1 in 20 runs out at (a header) | Geld aus bei 1 von 20 (Alter) | no-break spaces keep `bei 1 von 20` on one line: the header took six lines on a phone; its tip explains the 5th percentile |
| chance to run out by 90 | Risiko, dass dein Geld vor 90 ausgeht | never „Chance": good things only; a header, axis or measure `Risiko bis 90` (`RUN_OUT`, also `Risiko zu Lebzeiten`, `Pflegerisiko`): the summary fits 1,500 px |
| run out (of money) / typical shortfall | dein Geld geht aus / typischer Fehlbetrag | never „pleite" in a label |
| scenario / template / phase | Szenario / Vorlage / Phase | user labels stay as written |
| main scenario / Also compare in the Explorer / Edit scenario | Hauptszenario / Im Explorer auch vergleichen / Szenario bearbeiten | the first of `app.yaml`, which the pages of one scenario show; the select marks it `(Hauptszenario)` |
| stream | Zahlung | „Zahlungsstrom" is jargon |
| income / spending, expenses / savings plan | Einnahmen / Ausgaben / Sparplan | |
| asset / security / depot | Vermögenswert / Wertpapier / Depot | |
| tab / coin (crypto) | Tab / Kryptowährung | not „Reiter"; „Münze" is a physical coin (gold) only |
| units / lot / trade | Stück / Tranche / Kauf oder Verkauf (pl. Transaktionen) | |
| sale / purchase / property | Verkauf / Kauf / Immobilie | |
| let (a property) / rental income / bought in / building share / financed property | vermietet / Mieteinnahmen / Kaufmonat / Gebäudeanteil / Finanzierte Immobilie | a field reads as its noun, not „gekauft im", „finanziert" |
| AfA, AfA rate / Werbungskosten, work expenses (a `deduct` option) / Verlustvortrag / Verlustrücktrag, carry a loss back / Feststellungsbescheid | AfA, AfA-Satz / Werbungskosten / Verlustvortrag / Verlustrücktrag, zurücktragen / Feststellungsbescheid | as the law writes them; English help: `depreciation (AfA)`, `losses carried forward` |
| losses of capital income / Capital losses carried forward € (`tax.capital_losses`) / Aktienverlusttopf | Verluste aus Kapitalvermögen / Kapitalverlustvortrag € / Aktienverlusttopf | the label fits one line beside its neighbours, the term of its help „Verlustvortrag aus Kapitalvermögen"; the key „Kapitalverluste"; loss certificate „Verlustbescheinigung" |
| Sonderausgaben / donation / childcare / household services / craftsman's labour / deductible as / own premium (`premium`) / Kinderzulage | Sonderausgaben / Spende / Kinderbetreuung / haushaltsnahe Dienstleistung / Handwerkerleistung / absetzbar als / Eigenbeitrag (eigener Beitrag pro Monat) / Kinderzulage | rule `deductions`; `deductible` stays „Absetzbar", one term, one word; never „Steuerabzug": that is the withholding |
| loan / interest / principal / fixed for / repayment (a `repay` event) | Darlehen / Zinsen / Tilgung / Zinsbindung / Sondertilgung | |
| term deposit / overnight | Festgeld / Tagesgeld | |
| equity / fixed income / gold / crypto | Aktien / Anleihen / Gold / Krypto | |
| inflation / consumer prices | Inflation / Verbraucherpreise | |
| euros of the start / nominal euros | Euro in Kaufkraft von 2026-10 / nominale Euro | axis „€, Kaufkraft 2026-10"; help „ohne Inflationsausgleich"; start-year euros „Euro in Kaufkraft des Startjahrs", not „Euro des Starts" |
| paths / median / p5 to p95 | Verläufe / Median / 5. bis 95. Perzentil | labels: „mittlerer Verlauf" |
| Monte Carlo / historical / fixed / spread | Monte Carlo / historisch / fest / Schwankung | |
| severance / one-off payment, lump sum / write-off | Abfindung / Einmalzahlung / Ausbuchung | not „Abschreibung" (AfA), not „Einmalauszahlung" |
| pension / bAV policy / care | Rente / bAV-Vertrag / Pflege, Pflegefall | company pension: Betriebsrente |
| Pension growth / Raises in (a phase, `scale.growth`) | Rentensteigerung / Gehaltssteigerung in | the key `growth` „Wachstum“; a growth of a phase in a sentence „Steigerung“ |
| self-employment / profit / business | Selbstständigkeit / Gewinn / Betrieb | |
| income tax / Soli / capital gains tax / SV | Einkommensteuer / Soli / Abgeltungsteuer / Sozialversicherung (SV) | |
| Vorabpauschale, Teilfreistellung, Sparer-Pauschbetrag, Grunderwerbsteuer, Fünftelregelung, Gewerbesteuer, Hebesatz, Vorsorgepauschale, Basisrente, Altersvorsorgedepot, Hausgeld, ALG1, Rentenpunkte, Krankengeld, PKV, GKV, KVdR, Bundesland | as is | the English UI uses them; PKV, GKV spelled out once in help |
| Statutory health insurance from (`tax.gkv_from`) / private insurance only / statutory insurance only / switch, change (of the insurance) / exemption / ALG1 in the PKV (a marker) | Gesetzlich versichert ab / nur privat versichert / nur gesetzlich versichert / Wechsel / Befreiung / ALG1 in der PKV | the key `gkv_from` „GKV ab"; the marker `gkv` „Gesetzliche Krankenversicherung" |
| Sperrzeit / course, training (`training`) / claim (to ALG1) / used up | Sperrzeit / Weiterbildung / Anspruch / verbraucht | rule `alg1`; the key `sperrzeit` „Sperrzeit", `training` „Weiterbildung" |
| allocation / glide path / invest the rest | Aufteilung / Gleitpfad / Rest anlegen | |
| realize gains (`tax.harvest`) / Gains realized (a marker) | Gewinne realisieren / Gewinne realisiert | the key `harvest`: „Gewinnrealisierung"; the tax-free room: „steuerfreier Rahmen" |
| spending rule / cuts / trigger | Ausgabenregel / Kürzungen / Schwelle | `Cut when wealth falls below`: „Kürzung unterhalb dieser Vermögensschwelle" (owner), `liquid_below` of a sale `Vermögensschwelle`; no verb at the end of a label |
| increase / ceiling / reference wealth / pay (salary or profit) | Erhöhung / Obergrenze / Bezugsvermögen / Erwerbseinkommen | the upper band of the spending rule: `Increase when wealth rises above` „Erhöhung oberhalb dieser Vermögensschwelle"; `The first month without pay` „Dem ersten Monat ohne Erwerbseinkommen"; the headers `Months of cuts` and `Months of raises` „Monate mit Kürzung" and „Monate mit Erhöhung": a header wraps between words, one compound pushed `Pflegerisiko` out of the report at 1,200 px |
| VPW, variable percentage withdrawal / growth trend / floor / spend down to (age) / Spending floor | variable Entnahme (VPW) / Wachstumstrend / Untergrenze / aufbrauchen bis (Alter) / Untergrenze der Ausgaben | rule `spending`; the key `vpw` „variable Entnahme"; `essential spending` „feste Ausgaben" |
| What moves the result / Why paths run out / better, worse (a step) | Was das Ergebnis bewegt / Warum das Geld ausgeht / besser, schlechter | sensitivity, failure anatomy |
| Will the money last? / below 1×, 1× to 2×, 5× or more / run out, dead (its bands) | Reicht das Geld? / unter 1×, 1× bis 2×, 5× oder mehr / Geld ausgegangen, verstorben | the chart of the share of the paths by age (rule `balance`); the title `Reicht das Geld? 1× ist das liquide Vermögen mit 49` |
| goal seek / roll forward / lever / Stop working | Zielsuche / Start vorrücken / Hebel / Arbeitsende | |
| record / revision / Changes since | erfassen / Version / Änderungen seit | |
| Kept results / Clear cache / Clear, Cancel | Gespeicherte Ergebnisse / Cache leeren / Leeren, Abbrechen | the folder `.cache` of the Data page (rule `series`); `Cache` as is |
| Undo / Saved at … / Took back the save … / Last save … / Correct a recorded month | Rückgängig / Gespeichert um … / Rückgängig gemacht: das Speichern … / Zuletzt gespeichert … / Einen erfassten Monat korrigieren | the undo of a save (rule `save-guard`); in a sentence the button in quotes, „Rückgängig“ bleibt gesperrt |
| Save / Discard my edits / stays off / against the plan | Speichern / Meine Änderungen verwerfen / bleibt gesperrt / im Vergleich zum Plan | a button that stays off „bleibt gesperrt", not „bleibt aus" |
| overrides (tab) / tag / default | Abweichungen / Schlagwort / Standard | |
| Track / Plan / Setup | Verfolgen / Planen / Einrichten | the sections |
| Mode / Simple / Advanced / simple mode / Hidden in simple mode (at their defaults) | Modus / Einfach / Erweitert / einfacher Modus / Im einfachen Modus ausgeblendet (auf Standard) | rule `mode`; `Switch to Advanced in the sidebar` „Stelle in der Seitenleiste auf Erweitert", on a phone `im Menü` |
| Features (the page) / feature / switched off / in use / Template (a scenario) | Funktionen / Funktion / abgeschaltet / in Gebrauch / Vorlage | `Off in Features` „Unter Funktionen abgeschaltet"; a feature in a sentence by its message in the context `inline`, German with its capitals (`Gold und Krypto`), never a `.lower()` |
| start a plan / start (a button) / data directory | einen Plan starten / starten / Datenverzeichnis | the start page |
| example / their (the examples') | Beispiel / der Beispiele | not „Ihre …": a capital „Ihre" reads as „Sie" |
| Rename / All columns / Columns / Use / Override (its toggle) / a key of the inputs | Umbenennen / Alle Spalten / Spalten / Verwenden / Abweichen / the German name of its field, a noun (`Restschuld`) | the shared helpers |
| sheet / As of / outflows / surplus / non-cash income / wealth built / one-offs / run rate / actual | Tabelle / Stichtag / Abflüsse / Überschuss / unbare Einnahmen / Vermögenszuwachs / Einmalposten / laufende Rate / Ist | the cash pages; the ledger `budget.said` |
| extends / Dates / Event fields / New / Copy / Rename file / zip / Keep this instance / Take the import | basiert auf / Termine / Ereignisfelder / Neu / Kopieren / Datei umbenennen / Zip-Datei / Diese Instanz behalten / Import übernehmen | the pages of `Setup` |
| cash / cash buffer | Bargeld / Liquiditätsreserve | the cash of a run, an asset kind, a class; not „Konto", not „Liquidität": `liquide` is the liquid wealth |
| run (a simulation) / slider | Simulation / Regler | not „Lauf", not „Schieberegler"; the run: die Simulation |
| measure: of the Snapshot / of a figure | Einheit / Kennzahl | |
| at 67 (a value) / at 60 (a condition) / by 90 | mit 67 / ab 60 / bis 90 | a month count on a slider `6 Mon.`: a format has no plural |
| item / set in / left out by / shift (key) | Eintrag / Festgelegt in / Weggelassen von / Verschiebung | headers capitalised |
| job loss / Unemployed (the phase it adds) / move (a phase change) | Jobverlust / Arbeitslos / verschieben | the Scenarios page; `Arbeitslos` in the context `phase` |
| What-ifs / Check a what-if / Stop earlier / Lose the job / Take a course / Start a business / Buy a property / Add and compare / own funds / Self-employed (the phase) | Was-wäre-wenn / Was-wäre-wenn prüfen / Früher aufhören / Job verlieren / Weiterbildung machen / Selbstständig machen / Immobilie kaufen / Hinzufügen und vergleichen / Eigenkapital / Selbstständig | rule `whatifs`; `Arbeitsende` for the stop of the plan in a sentence; the names a step writes in the context `data` |
| Your goals / Stop working at age / Check a job loss in (month) / I own a property / Loan still owed € / pauses (a savings plan) | Deine Ziele / Arbeitsende im Alter von / Jobverlust prüfen im (Monat) / Ich besitze eine Immobilie / Restschuld des Darlehens € / setzt aus | the quick start (rule `first-run`); a pause of a savings plan in the attention table of the Overview; the names of a new plan (`Arbeit`, `Arbeitslos`, `Auszeit`, `Ruhestand`) are data |
| Check a what-if / Rent that ends (€ a month) / Spending that holds the rent | Was-wäre-wenn prüfen / Entfallende Miete (€ pro Monat) / Ausgabe mit der Miete | the what-ifs (rule `whatifs`); `spending` of one row, a stream of expenses: `Ausgabe` |
| Summary / Comparison / Difference from / Views / Balance sheet / Liquid, Flows (headings) | Zusammenfassung / Vergleich / Unterschied zu / Ansichten / Bilanz / Liquides Vermögen, Einnahmen, Ausgaben und Steuern | the report; not „Übersicht": the page Overview |
| € of 2026-10 per year / nominal € per year | € pro Jahr, Kaufkraft 2026-10 / € pro Jahr, nominal | the axis of the flows: `pro Jahr` after the `€` |
| Kindergeld, Kinderfreibetrag, Kindererziehungszeiten, Entlastungsbetrag, Elterngeld | as is | the English UI uses them (rule `children`) |
| child allowance / counts as a child until / Kindergeld paid to you / child-raising years credited to your pension / single parent / half, full | Kinderfreibetrag / Kind bis / Kindergeld an dich / Kindererziehungszeiten bei dir / alleinerziehend / halb, voll | the grid of the children |
| disability (a full Erwerbsminderung) / Disabled from (what-if) / Chance of disability / Unable to work (a marker) / Disability starts at age | Erwerbsminderung / Erwerbsgemindert ab (Was-wäre-wenn) / Risiko einer Erwerbsminderung / Erwerbsunfähig / Erwerbsminderung ab Alter | never „Chance" (a bad thing: `Risiko`); rule `disability` |
| disability insurance (BU) / Monthly benefit € / Monthly premium € / Pays until age / benefit (a ledger item) | Berufsunfähigkeitsversicherung (BU), the tab `BU-Versicherung` / Monatliche BU-Rente € / Monatsbeitrag € / Leistet bis Alter / Leistung | `Krankengeld`, `EM-Rente` as is |
| inheritance / gift / inheritance tax / gift tax / relatives / relation / cost basis | Erbschaft / Schenkung / Erbschaftsteuer / Schenkungsteuer / Angehörige / Verwandtschaft / Anschaffungskosten | a relative `Angehöriger`, the relations `Elternteil`, `Großelternteil`, `Geschwister`, `Tante oder Onkel`, `Schwiegerelternteil`, `andere`; Freibetrag as is (rule `estates`) |
