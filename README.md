# DK1 cable flow forecasting

A forecast of tomorrow's net flow on DK1's six cables (Germany, Norway, Britain, the Netherlands, Sweden and DK2), hour by hour. It is saved before the noon day-ahead auction and scored when the auction result is out.

Dashboard: [jacobazu.github.io/dk1-flow-forecasting](https://jacobazu.github.io/dk1-flow-forecasting)

The main page is a map of the Northern European price areas for the last week and tomorrow, with prices, generation by fuel and the flow on every border. The track record, backtest and method are on a second page.

## Backtest

186 days from 1 March to 10 October 2026. Mean absolute error per hour, compared with using the same hour yesterday. The rules were fixed before the test ([RULES.md](RULES.md)).

| Cable | Model | Same hour yesterday | Better by | p (Holm) |
|---|---:|---:|---:|---:|
| Germany | 1,059 MW | 1,264 MW | 16% | <0.001 |
| Britain | 590 MW | 670 MW | 12% | 0.20 |
| Norway | 517 MW | 570 MW | 9% | 0.57 |
| Netherlands | 423 MW | 461 MW | 8% | 0.11 |
| Great Belt (DK2) | 255 MW | 252 MW | −1% | 0.79 |
| Sweden | 326 MW | 309 MW | −6% | 0.75 |

Only Germany is clearly better than yesterday's flow. Britain, Norway and the Netherlands point the right way but could be luck. On Sweden and the Great Belt the model doesn't help.

## Method

One lasso regression per cable, refit every month on earlier days only. Inputs are what is known before noon the day before: my DK1 price forecast ([dk1-price-forecasting](https://github.com/jacobazu/dk1-price-forecasting)), my wind and solar forecasts ([dk1-renewables-forecasting](https://github.com/jacobazu/dk1-renewables-forecasting)), today's prices in DK1 and its neighbours, the cable's flow today and a week ago, and the calendar. Diebold-Mariano test with Holm correction over the six cables.

## Track record

Live forecasts are in `forecasts/flow_live.csv` and are never changed. The days between the end of the backtest and the first live run were made afterwards, using only data published before each auction, and are kept in `forecasts/flow_backfill.csv`. They are marked with * on the dashboard. 11 October to 10 November is missing because the price and wind forecasts weren't both running then.

Data: ENTSO-E, Energi Data Service and the Rebase Grid API.
