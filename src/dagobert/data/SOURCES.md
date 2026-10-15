# Data sources

The files in this directory ship with the package. The app reads them and never writes them.
Each source allows the redistribution only with a source note. This file gives the source, the
terms and the source note of each file. The app shows the same notes.

## Shipped series

| File | Content | Source | Terms | Source note | Downloaded |
|---|---|---|---|---|---|
| `destatis_vpi_west.csv` | Consumer price index of the former West Germany (Früheres Bundesgebiet), all private households, 1995=100, monthly from 1962-01 to 1999-12. An extract: one column of the sheet `csv-611xx-b03`, values unchanged. | Statistisches Bundesamt (Destatis), [Statistischer Bericht "Preisindizes für die Lebenshaltung - Lange Reihen von 1948 bis 1999"](https://www.destatis.de/DE/Themen/Wirtschaft/Preise/Verbraucherpreisindex/Publikationen/Downloads-Verbraucherpreise/statistischer-bericht-preisindizes-lebenshaltung-lange-reihen-5611111999005.html), article number 5611111999005, published on 2025-08-13. The report is final. | Impressum: "Vervielfältigung und Verbreitung, auch auszugsweise, mit Quellenangabe gestattet." [Datenlizenz Deutschland – Namensnennung – Version 2.0](https://www.govdata.de/dl-de/by-2-0) | © Statistisches Bundesamt (Destatis), 2025 | 2026-10-12 |
| `bundesbank_vpi.csv` | Verbraucherpreisindex for Germany, 2020=100, monthly from 1991-01. The newest month can be an estimate of the Bundesbank, with the flag `Geschätzter Wert`. | Deutsche Bundesbank, [SDMX web service](https://api.statistiken.bundesbank.de/rest/data/BBDP1/M.DE.N.VPI.C.A00000.I20.A?format=bbk_csv), flow `BBDP1`, key `M.DE.N.VPI.C.A00000.I20.A`, format `bbk_csv`. The Bundesbank names the Statistisches Bundesamt as its source. | [Terms of use of the Deutsche Bundesbank](https://www.bundesbank.de/de/startseite/benutzerhinweise/nutzungsbedingungen-fuer-den-allgemeinen-gebrauch-der-website-763554), §4.1 | Quelle: Deutsche Bundesbank; Statistisches Bundesamt, Wiesbaden | 2026-10-12, up to 2026-09 (an estimate) |
| `bundesbank_umlaufsrendite.csv` | Umlaufsrendite inländischer Inhaberschuldverschreibungen, insgesamt: the yield of the German bonds outstanding in percent, monthly from 1955-08. | Deutsche Bundesbank, [SDMX web service](https://api.statistiken.bundesbank.de/rest/data/BBSIS/M.I.UMR.RD.EUR.A.B.A.A.R.A.A._Z._Z.A?format=bbk_csv), flow `BBSIS`, key `M.I.UMR.RD.EUR.A.B.A.A.R.A.A._Z._Z.A`, format `bbk_csv` | [Terms of use of the Deutsche Bundesbank](https://www.bundesbank.de/de/startseite/benutzerhinweise/nutzungsbedingungen-fuer-den-allgemeinen-gebrauch-der-website-763554), §4.1 | Quelle: Deutsche Bundesbank | 2026-10-12, up to 2026-09 |
| `worldbank_gold.csv` | Gold in US dollars per troy ounce, monthly from 1960-01: the average of daily prices (the spot price from 2025-06, before that the London afternoon fixing). The workbook stores whole dollars. An extract: the column `Gold` of the sheet `Monthly Prices`, values unchanged. | World Bank, Commodity Price Data (The Pink Sheet), workbook `CMO-Historical-Data-Monthly.xlsx`, linked as "Monthly prices" on the [Commodity Markets page](https://www.worldbank.org/en/research/commodity-markets). The sheet `Description` of the workbook names the sources of the gold prices, as the source note lists them. | [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/), as the [data catalog of the World Bank](https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections) states for the data set, and the [terms of use for datasets of the World Bank](https://www.worldbank.org/ext/en/legal/terms-conditions/datasets). These terms ask for the source note in the form "The World Bank: Dataset name: Data source". Who passes the data on must pass on the same requirement, for example with the URL of these terms. | The World Bank: Commodity Prices - History and Projections (Pink Sheet): Bloomberg Finance L.P.; Kitco.com; International Monetary Fund, International Financial Statistics; London Bullion Market; Metals Week; Platts Metals Week; Shearson Lehman Brothers, Metal Market Weekly Review; Thomson Reuters Datastream; World Bank. Extract: the column Gold of the sheet Monthly Prices, values unchanged. | 2026-10-12, the workbook of 2026-10-02, up to 2026-09 |
| `bundesbank_usd_dem.csv` | Deutsche Mark per US dollar, monthly average, from 1948-07 to 1998-12. From 1953-08 on, the average of the official quotations of the Frankfurt exchange. Before, fixed conversion rates. The header block of the file explains them. The series is final. | Deutsche Bundesbank, [SDMX web service](https://api.statistiken.bundesbank.de/rest/data/BBEX3/M.USD.DEM.AA.AC.A02?format=bbk_csv), flow `BBEX3`, key `M.USD.DEM.AA.AC.A02`, format `bbk_csv` | [Terms of use of the Deutsche Bundesbank](https://www.bundesbank.de/de/startseite/benutzerhinweise/nutzungsbedingungen-fuer-den-allgemeinen-gebrauch-der-website-763554), §4.1 | Quelle: Deutsche Bundesbank | 2026-10-12 |
| `ecb_usd_eur.csv` | US dollars per euro, the reference rate of the ECB, monthly average, from 1999-01. The ECB publishes a month after it ends. | European Central Bank, [SDMX web service of the ECB Data Portal](https://data-api.ecb.europa.eu/service/data/EXR/M.USD.EUR.SP00.A?format=csvdata), flow `EXR`, key `M.USD.EUR.SP00.A`, format `csvdata` | [Policy regarding the reuse of ESCB statistics](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html): free reuse when the source is quoted and the statistics, metadata included, are not modified | Source: ECB statistics. | 2026-10-12, up to 2026-09 |
| `sterbetafel-2023-2025.csv` | Period life table for Germany, 2023/2025: the probability of death within one year (`qx`) for each age from 0 to 100, male (`qx_m`) and female (`qx_f`). An extract of the sheets `csv-12613-b01` and `csv-12613-b02`, values unchanged. | Statistisches Bundesamt (Destatis), [Statistischer Bericht "Sterbetafeln" 2023/2025](https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Sterbefaelle-Lebenserwartung/Publikationen/Downloads-Sterbefaelle/statistischer-bericht-sterbetafeln-5126207257005.html), article number 5126207257005 | Impressum: "Vervielfältigung und Verbreitung, auch auszugsweise, mit Quellenangabe gestattet." [Datenlizenz Deutschland – Namensnennung – Version 2.0](https://www.govdata.de/dl-de/by-2-0) | © Statistisches Bundesamt (Destatis), 2026 | 2026-10-12 |

The terms of the Bundesbank allow you to store, pass on and copy its data. The data must not be
changed or falsified. So the three Bundesbank files are the answers of the web service, byte for
byte, with their header blocks. The reuse policy of the ECB also forbids a change of its
statistics and their metadata. So `ecb_usd_eur.csv` is the answer of the web service of the ECB,
byte for byte.

The app joins the two consumer price series in memory. Up to 1990-12 it takes the West German
index, multiplied by the ratio of the two indices in 1991-01. From 1991-01 on it takes the VPI
as published. So no shipped file is changed.

The app also converts gold and Bitcoin from US dollars to euros in memory, month by month. From
1999-01 on, it divides by the ECB rate of the month. Up to 1998-12, it multiplies by the
Deutsche Mark per US dollar and divides by 1.95583. That is the fixed number of Deutsche Mark per
euro (Council Regulation (EC) No 2866/98). A month after the last rate takes the last rate. So
no shipped file is changed.

The gold prices and the exchange rates are monthly averages of daily values. The MSCI series
and Bitcoin are values at the end of a month. An average makes the change from one month to the
next smaller, and it links each month to the month before. Over a year the effect is small.

The directory `tax/` holds the legal constants of each tax year. The comments in each file name
the laws and the sources. The file `grunderwerbsteuer.yaml` holds the rates of the
Grunderwerbsteuer of each Land, each with the day from which it holds. Its comments name the
sources.

## Series that do not ship

The historical model needs an equity series: the MSCI World Net Total Return in EUR. The MSCI
index terms (<https://www.msci.com/legal/index-terms>) allow informational, non-commercial use
only. So the series does not ship. A user fetches it from Curvo or imports an index history
into the data directory, where it stays. Without it the historical model is off.

The Bitcoin prices come from the [Community API of Coin
Metrics](https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data): the daily
close in US dollars from 2010-07-18. Coin Metrics licenses this data under [Creative Commons
Attribution-NonCommercial 4.0](https://creativecommons.org/licenses/by-nc/4.0/). So the series
does not ship. A user fetches it on the Data page or with `dagobert series fetch bitcoin`. The
fetch keeps the close of the last day of each month, in `series/bitcoin.csv` of the data
directory, where it stays. The app shows the source note "Source: Coin Metrics Community Data.
Non-commercial use only." The app values `BTC` at the last month of the series, unless a stored
price is as new or newer. The historical model does not replay it: the growth by a factor of about 10,000 up to 2013
is no sample of the future.

## Refresh before a release

1. Run `uv run python scripts/refresh_shipped.py` in the repository root. The script makes three
   requests to the Bundesbank and one to the ECB, five seconds apart. It also makes three
   requests to Destatis and two to the World Bank.
2. If the script refuses the gold workbook as old, the Commodity Markets page of the World Bank
   links an old workbook. Make sure that the page links the workbook of the current month, and
   run the script again.
3. Read the list of changed files that the script prints.
4. If the script wrote a new life table, update its row above. The script removes the old
   table. It also names the report and the source note of the new table: set them in
   `LIFE_TABLE_SOURCE` and `LIFE_TABLE_ATTRIBUTION` of `series.py`.
5. If the script names new sources of the gold prices, set them in the source note of `gold` in
   `series.py` and in the row above.
6. Update the column `Downloaded` above.
