# Rules for the flow forecast

Written 13 Nov 2026, before any benchmark or model was scored. Nothing here changes after a result is seen; a
change is a new dated section below, and the old rule stays.

## What is forecast

- The net day-ahead auction flow on each of DK1's six cables, per hour of the Danish day: Germany (DE),
  the Netherlands (NL), Britain (GB), Norway (NO2), Sweden (SE3) and the Great Belt to DK2.
- Net flow = flow out of DK1 minus flow into DK1, in MW. Plus means export from DK1.
- Source: ENTSO-E scheduled commercial exchanges, day-ahead (A09). Quarter-hours are averaged to hours.
  ENTSO-E leaves out points that repeat the one before (curve type A03), so a missing position takes the last
  value given in its period.
- A day counts only if it has all 24 hours for every cable (the two daylight-saving days are left out).

## When

- The forecast for day D is made before 12:00 Danish time on D-1, using only what is published by then.
- The flows for D-1 come from the auction on D-2, so they are known. The flows for D are not.

## Benchmarks

- **Last week:** the same hour on D-7.
- **Yesterday:** the same hour on D-1.

## Model

- A lasso regression per cable, refitted on the first day of each month on all earlier test-period days.
- Inputs, all known before 12:00 on D-1:
  - our DK1 price forecast for each hour of D (the ensemble of jacobazu/dk1-price-forecasting)
  - the neighbours' day-ahead prices for the same hour on D-1 (DE, NL, NO2, SE3, DK2; Britain has left ENTSO-E's platform, so no GB price)
  - our offshore wind forecast for D (jacobazu/dk1-renewables-forecasting) and the onshore and solar ones
  - the cable's flow in the same hour on D-1 and D-7
  - hour of day, weekday, Danish holiday
- The lasso penalty is chosen on tuning days: every 7th day of the test period, counted from its first day.
  Tuning days are never scored.

## Test period and score

- Days where both the price backtest and the renewables backtest exist: 1 Jan 2026 to 10 Oct 2026.
- The model is first scored from 1 Mar 2026, so its first fit has two months behind it. Benchmarks are scored on
  exactly the same days.
- Score: mean absolute error per cable, MW, over all hours of the scored days.
- The model beats a benchmark on a cable if its mean absolute error is lower, by a Diebold-Mariano test on the
  daily mean absolute errors with Newey-West variance (7 lags), p < 0.05 after a Holm correction over the six
  cables. It is compared with the better of the two benchmarks on that cable.

## Shown, not forecast

- After each day, the measured flow (ENTSO-E physical flows, A11) minus the auction flow, per cable and hour.
  A11 gives one direction per document, so measured net = A11 out of DK1 minus A11 into DK1.
