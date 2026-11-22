# DK1 cable flow forecasting

Tomorrow's net flow on each of DK1's six cables (Germany, Norway, Britain, the Netherlands, Sweden and DK2), forecast hour by hour before the noon day-ahead auction and scored once the auction result is out. Next to it: how far the measured flow strayed from the auction flow.

**Dashboard: [jacobazu.github.io/dk1-flow-forecasting](https://jacobazu.github.io/dk1-flow-forecasting)**: a map of Denmark's cables hour by hour for the last week and tomorrow, with Energinet's measured flows and generation, the auction flows and our forecast. The forecast record, backtest and method are on a second page.

## Result

The rules were written before any result ([RULES.md](RULES.md)). Backtest on 186 days from 1 March to 10 October 2026, mean absolute error per hour against the best simple guess, the same hour yesterday:

| Cable | Model | Same hour yesterday | Better by | p (Holm) | Beats yesterday |
|---|---:|---:|---:|---:|---|
| Germany | 1,059 MW | 1,264 MW | 16% | <0.001 | yes |
| Britain | 590 MW | 670 MW | 12% | 0.20 | no |
| Norway | 517 MW | 570 MW | 9% | 0.57 | no |
| Netherlands | 423 MW | 461 MW | 8% | 0.11 | no |
| Great Belt (DK2) | 255 MW | 252 MW | −1% | 0.79 | no |
| Sweden | 326 MW | 309 MW | −6% | 0.75 | no |

The model passes on Germany, DK1's biggest and most price-driven link. It is closer on Britain, Norway and the Netherlands too, but not by enough to rule out luck once six cables are tested. On Sweden and the Great Belt yesterday's flow is as good as it gets. Nothing was tuned after seeing these numbers.

## How it works

- **Inputs, all known before noon the day before:** the DK1 price forecast saved live by [dk1-price-forecasting](https://github.com/jacobazu/dk1-price-forecasting), the offshore, onshore and solar forecasts saved by [dk1-renewables-forecasting](https://github.com/jacobazu/dk1-renewables-forecasting), today's prices in DK1 and the five neighbours, the cable's flow in the same hour today and a week ago, and hour, weekday and holidays.
- **Model:** one lasso regression per cable (glmnet), refit on the first of each month on earlier days. The penalty is the one that did best on tuning days (every 7th day from 1 January), which are never scored.
- **Test:** Diebold-Mariano on daily errors with Newey-West (7 lags), Holm correction over the six cables, p < 0.05.
- **Live:** every morning before 12:00 Danish time the forecast for tomorrow is saved to `forecasts/flow_live.csv` and never changed.
- **Backfilled:** the days between the backtest and the first live forecast were made afterwards by `scripts/05_backfill.R`, with only what was published before each auction and the model fit only on earlier days, as the live run would have. They are kept in `forecasts/flow_backfill.csv` and scored apart from the live record. 11 Oct to 10 Nov are missing: the price and wind forecasts they need were not both running then.

## Files

| | |
|---|---|
| `scripts/01_download.R` | auction (A09) and measured (A11) flows and day-ahead prices from ENTSO-E, resumable |
| `scripts/02_benchmarks.R` | the simple guesses and measured vs auction |
| `R/inputs.R`, `R/model.R` | features and the lasso |
| `scripts/03_model.R` | the backtest, written to `results/` |
| `scripts/04_live.R` | tomorrow's forecast |
| `scripts/05_backfill.R` | the backfilled days |
| `dashboard.py`, `assets/` | the map and the record page |

Data: ENTSO-E Transparency Platform (auction flows, prices; measured flows on the British cable are not published there), Energi Data Service (Energinet's real-time generation and cable flows, for the map), Natural Earth (borders).
