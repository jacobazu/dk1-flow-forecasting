# forecasts for the days between the end of the backtest (10 oct 2026) and the first live forecast, made afterwards
# exactly as the live run would have made them: same inputs, each saved before the auction by the other repos,
# and the model fit only on days before the first of the month of the day it was made. days without every input
# (our wind forecast was not live from 12 oct to 10 nov) are left out. days already in the live file are skipped.
# adds to forecasts/flow_backfill.csv, kept apart from the live record; days already there are never remade

source("R/inputs.R")
source("R/model.R")

out_file <- "forecasts/flow_backfill.csv"
live_file <- "forecasts/flow_live.csv"
first_day <- as_date("2026-10-11")
now <- with_tz(Sys.time(), "Europe/Copenhagen")
last_day <- as_date(now) + if (hour(now) >= 13) 1 else 0       # tomorrow once its inputs are all out
live_days <- if (file.exists(live_file)) as_date(read_csv(live_file, show_col_types = FALSE)$date) else as_date(character())
# days already backfilled stay as they were made; only missing days are added
old <- if (file.exists(out_file)) read_csv(out_file, col_types = cols(made_utc = col_character())) |> mutate(date = as_date(date)) else
  tibble(date = as_date(character()))

pf_b <- price_forecasts(); wf_b <- wind_forecasts()
pf <- bind_rows(pf_b, price_forecasts(live = TRUE) |> filter(date > max(pf_b$date)))
wf <- bind_rows(wf_b, wind_forecasts(live = TRUE) |> filter(date > max(wf_b$date)))
flows <- read_flows(); prices <- read_prices()

all_train <- build(flows, prices, pf, wf) |> filter(date >= first_test, !is.na(actual)) |> complete_rows()
days <- setdiff(seq(first_day, last_day, by = "day"), c(live_days, unique(old$date))) |> as_date()
new <- build(flows, prices, pf, wf, dates = days) |> complete_rows() |>
  filter(n() == 24 * length(cables), .by = date)                 # only days with every input for every hour
message("days with every input: ", n_distinct(new$date), " of ", length(days))
if (nrow(new) == 0) { message("nothing new to backfill"); quit(status = 0) }

# the live run for day D is made on D-1, so it is fit on days before the first of D-1's month
new <- new |> mutate(fit_before = floor_date(date - 1, "month"))
rows <- list()
for (m in sort(unique(new$fit_before))) for (cb in cables) {
  m <- as_date(m)
  f <- fit_cable(filter(all_train, cable == cb, date < m))
  r <- filter(new, cable == cb, fit_before == m)
  rows[[length(rows) + 1]] <- tibble(date = r$date, hour = r$hour, cable = cb,
                                     forecast = round(predict_cable(f, r), 1), yesterday = r$flow_d1)
}
out <- bind_rows(rows) |> arrange(date, cable, hour) |>
  mutate(made_utc = format(Sys.time(), "%Y-%m-%d %H:%M", tz = "UTC"), .before = 1)
out <- bind_rows(old, out) |> arrange(date, cable, hour)

dir.create("forecasts", showWarnings = FALSE)
write_csv(out, out_file)
print(as.data.frame(out |> summarise(hours = n(), .by = date)))
