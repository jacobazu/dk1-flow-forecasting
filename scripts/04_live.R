# tomorrow's net auction flow per cable and hour, saved once before 12:00 danish time and never changed.
# the model is fit as in the backtest: on all test-period days before the first of this month, penalty from the
# tuning days. inputs are the price and wind forecasts saved live before the auction, today's auction flows and
# prices (published yesterday) and the flows a week before. writes forecasts/flow_live.csv

source("R/inputs.R")
source("R/model.R")

now <- with_tz(Sys.time(), "Europe/Copenhagen")
tomorrow <- as_date(now) + 1
out_file <- "forecasts/flow_live.csv"
old <- if (file.exists(out_file)) read_csv(out_file, show_col_types = FALSE) else tibble(date = as_date(character()))
if (tomorrow %in% as_date(old$date)) { message("flows for ", tomorrow, " already saved"); quit(status = 0) }
if (hour(now) >= 12) { message("after 12:00: the auction has closed, nothing saved for ", tomorrow); quit(status = 0) }

# backtest inputs up to where they end, live ones after
pf_b <- price_forecasts(); wf_b <- wind_forecasts()
pf <- bind_rows(pf_b, price_forecasts(live = TRUE) |> filter(date > max(pf_b$date)))
wf <- bind_rows(wf_b, wind_forecasts(live = TRUE) |> filter(date > max(wf_b$date)))
flows <- read_flows(); prices <- read_prices()

train <- build(flows, prices, pf, wf) |>
  filter(date >= first_test, date < floor_date(as_date(now), "month"), !is.na(actual)) |> complete_rows()
new <- build(flows, prices, pf, wf, dates = tomorrow)
miss <- feature_cols[colSums(is.na(new[, feature_cols])) > 0]
if (length(miss)) { message("not all inputs for ", tomorrow, " yet, missing: ", paste(miss, collapse = ", ")); quit(status = 0) }
message("training on ", n_distinct(train$date), " days, ", min(train$date), " to ", max(train$date))

rows <- bind_rows(lapply(cables, \(cb) {
  f <- fit_cable(filter(train, cable == cb))
  r <- filter(new, cable == cb)
  tibble(date = tomorrow, hour = r$hour, cable = cb, forecast = round(predict_cable(f, r), 1), yesterday = r$flow_d1)
})) |> mutate(made_utc = format(Sys.time(), "%Y-%m-%d %H:%M", tz = "UTC"), .before = 1)

dir.create("forecasts", showWarnings = FALSE)
write_csv(bind_rows(old |> mutate(date = as_date(date)), rows), out_file)
print(as.data.frame(rows |> summarise(mean_forecast = round(mean(forecast)), mean_yesterday = round(mean(yesterday)), .by = cable)))
