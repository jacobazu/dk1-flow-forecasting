# scores the two benchmarks of RULES.md on the test days: the same hour a week ago and yesterday.
# also how far the measured flow strayed from the auction flow on the same days (shown, not forecast).
# reads data/flows_hourly.csv, writes results/benchmarks.csv and results/measured_vs_auction.csv

library(dplyr)
library(tidyr)
library(readr)
library(lubridate)

first_test <- as_date("2026-01-01"); first_scored <- as_date("2026-03-01"); last_test <- as_date("2026-10-10")

f <- read_csv("data/flows_hourly.csv", show_col_types = FALSE) |>
  mutate(local = with_tz(time_utc, "Europe/Copenhagen"), date = as_date(local), hour = hour(local))

# danish days with 24 hours on every cable
full <- f |> filter(type == "auction") |> count(date, cable) |>
  summarise(ok = all(n == 24) && n() == 6, .by = date) |> filter(ok) |> pull(date)

a <- f |> filter(type == "auction", date %in% full) |> select(date, hour, cable, net)
bench <- a |>
  left_join(rename(a, last_week = net) |> mutate(date = date + 7), by = c("date", "hour", "cable")) |>
  left_join(rename(a, yesterday = net) |> mutate(date = date + 1), by = c("date", "hour", "cable"))

tuning <- \(d) as.integer(d - first_test) %% 7 == 0
scored <- bench |>
  filter(date >= first_scored, date <= last_test, !tuning(date)) |>
  filter(!any(is.na(last_week) | is.na(yesterday)), .by = date)

dir.create("results", showWarnings = FALSE)
out <- scored |>
  pivot_longer(c(last_week, yesterday), names_to = "benchmark", values_to = "forecast") |>
  summarise(days = n_distinct(date), mae_mw = mean(abs(net - forecast)), bias_mw = mean(net - forecast),
            mean_abs_flow_mw = mean(abs(net)), .by = c(cable, benchmark)) |>
  arrange(cable, benchmark) |> mutate(across(where(is.double), \(x) round(x, 1)))
write_csv(out, "results/benchmarks.csv")
print(as.data.frame(out))

m <- f |> filter(date %in% unique(scored$date)) |>
  select(type, date, hour, cable, net) |> pivot_wider(names_from = type, values_from = net) |>
  filter(!is.na(measured), !is.na(auction)) |>
  summarise(hours = n(), mean_abs_diff_mw = mean(abs(measured - auction)), mean_diff_mw = mean(measured - auction),
            .by = cable) |> mutate(across(where(is.double), \(x) round(x, 1)))
write_csv(m, "results/measured_vs_auction.csv")
print(as.data.frame(m))
