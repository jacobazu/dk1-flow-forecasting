# inputs for the flow model, all on the danish day and hour. see RULES.md for what is allowed and when

library(dplyr)
library(tidyr)
library(readr)
library(lubridate)

price_repo <- "https://raw.githubusercontent.com/jacobazu/dk1-price-forecasting/master/"
wind_repo  <- "https://raw.githubusercontent.com/jacobazu/dk1-renewables-forecasting/main/"
cables     <- c("DK1-DE", "DK1-NL", "DK1-GB", "DK1-NO2", "DK1-SE3", "DK1-DK2")
zones      <- c("DK1", "DE", "NL", "NO2", "SE3", "DK2")

# danish public holidays 2025-2027 (store bededag ended in 2024)
holidays <- as_date(c(
  "2025-01-01", "2025-04-17", "2025-04-18", "2025-04-20", "2025-04-21", "2025-05-29", "2025-06-08", "2025-06-09",
  "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31",
  "2026-01-01", "2026-04-02", "2026-04-03", "2026-04-05", "2026-04-06", "2026-05-14", "2026-05-24", "2026-05-25",
  "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
  "2027-01-01", "2027-03-25", "2027-03-26", "2027-03-28", "2027-03-29", "2027-05-06", "2027-05-16", "2027-05-17",
  "2027-12-24", "2027-12-25", "2027-12-26", "2027-12-31"))

local_hour <- function(d, col = "time_utc") {
  t <- with_tz(as_datetime(d[[col]]), "Europe/Copenhagen")
  mutate(d, date = as_date(t), hour = hour(t))
}

# net auction (or measured) flow per cable, danish date and hour, only days with 24 hours on every cable
read_flows <- function(type_ = "auction", file = "data/flows_hourly.csv") {
  f <- read_csv(file, show_col_types = FALSE) |> filter(type == type_) |> local_hour()
  full <- f |> count(date, cable) |> summarise(ok = all(n == 24) && n() == length(cables), .by = date) |>
    filter(ok) |> pull(date)
  f |> filter(date %in% full) |> select(date, hour, cable, net)
}

# day-ahead prices per zone, wide
read_prices <- function(file = "data/prices_hourly.csv") {
  read_csv(file, show_col_types = FALSE) |> local_hour() |>
    summarise(price = mean(price), .by = c(date, hour, zone)) |>
    pivot_wider(names_from = zone, values_from = price, names_prefix = "p_")
}

# our dk1 price forecast: the ensemble of the price repo (backtest, or saved live before the auction)
price_forecasts <- function(live = FALSE) {
  if (!live) {
    read_csv(paste0(price_repo, "results/backtest_forecasts.csv"), show_col_types = FALSE) |>
      transmute(date = as_date(date), hour, pf = (bmtx + learx + xgbx) / 3)
  } else {
    read_csv(paste0(price_repo, "forecasts/forecasts_live.csv"), show_col_types = FALSE) |>
      mutate(date = as_date(date)) |> distinct(date, hour, .keep_all = TRUE) |>
      transmute(date, hour, pf = ensemble)
  }
}

# our wind and solar forecasts (backtest, or saved live before the auction), MW
wind_forecasts <- function(live = FALSE) {
  f <- if (!live) read_csv(paste0(wind_repo, "results/final_forecasts.csv"), show_col_types = FALSE) else
    read_csv(paste0(wind_repo, "forecasts/live_forecasts.csv"), show_col_types = FALSE)
  f |> mutate(time_utc = force_tz(as_datetime(time), "UTC")) |> local_hour() |>
    summarise(forecast = mean(forecast), .by = c(date, hour, target)) |>
    pivot_wider(names_from = target, values_from = forecast) |>
    select(date, hour, any_of(c("offshore", "onshore", "solar")))
}

# one row per day, hour and cable with everything the model may use for that day (known before noon the day before)
build <- function(flows, prices, pf, wf, dates = NULL) {
  grid <- if (is.null(dates)) distinct(flows, date) else tibble(date = dates)
  grid <- tidyr::crossing(grid, hour = 0:23, cable = cables)
  nb   <- prices |> mutate(date = date + 1) |> rename_with(\(x) paste0(x, "_d1"), starts_with("p_"))
  lag1 <- flows |> transmute(date = date + 1, hour, cable, flow_d1 = net)
  lag7 <- flows |> transmute(date = date + 7, hour, cable, flow_d7 = net)
  grid |>
    left_join(flows |> rename(actual = net), by = c("date", "hour", "cable")) |>
    left_join(pf, by = c("date", "hour")) |>
    left_join(wf, by = c("date", "hour")) |>
    left_join(nb, by = c("date", "hour")) |>
    left_join(lag1, by = c("date", "hour", "cable")) |>
    left_join(lag7, by = c("date", "hour", "cable")) |>
    mutate(weekday = wday(date, week_start = 1), holiday = as.integer(date %in% holidays))
}

feature_cols <- c("pf", "offshore", "onshore", "solar", paste0("p_", zones, "_d1"), "flow_d1", "flow_d7")

# design matrix: numeric inputs plus hour and weekday as dummies
design <- function(d) {
  x <- as.matrix(d[, feature_cols])
  hr <- outer(d$hour, 1:23, "==") * 1; colnames(hr) <- paste0("h", 1:23)
  wd <- outer(d$weekday, 2:7, "==") * 1; colnames(wd) <- paste0("wd", 2:7)
  cbind(x, hr, wd, holiday = d$holiday)
}

complete_rows <- function(d) d[stats::complete.cases(d[, feature_cols]), ]
