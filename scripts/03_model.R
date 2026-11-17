# the lasso model of RULES.md, backtested on the test period and scored against "same hour yesterday".
# per cable: refit on the first day of each month on all earlier test-period days; the penalty is the one with the
# lowest mean absolute error on the earlier tuning days (every 7th day from 1 jan 2026), which are never scored.
# writes results/model_forecasts.csv, results/model_scores.csv, results/model_coefs.csv

library(glmnet)
source("R/inputs.R")

first_test <- as_date("2026-01-01"); first_scored <- as_date("2026-03-01"); last_test <- as_date("2026-10-10")
tuning <- \(d) as.integer(d - first_test) %% 7 == 0

flows <- read_flows()
d <- build(flows, read_prices(), price_forecasts(), wind_forecasts()) |>
  filter(date >= first_test, date <= last_test, !is.na(actual)) |> complete_rows()
message("rows with every input: ", nrow(d), " (", n_distinct(d$date), " days)")

fit_cable <- function(train) {
  fit_rows <- train[!tuning(train$date), ]; tune_rows <- train[tuning(train$date), ]
  m <- glmnet(design(fit_rows), fit_rows$actual, alpha = 1)
  mae <- colMeans(abs(predict(m, design(tune_rows)) - tune_rows$actual))
  list(model = m, lambda = m$lambda[which.min(mae)])
}

months <- seq(floor_date(first_scored, "month"), floor_date(last_test, "month"), by = "month")
out <- list(); coefs <- list()
for (cb in cables) for (k in seq_along(months)) {
  m0 <- months[k]; m1 <- m0 %m+% months(1)
  train <- d |> filter(cable == cb, date < m0)
  test  <- d |> filter(cable == cb, date >= m0, date < m1)
  if (!nrow(test)) next
  f <- fit_cable(train)
  out[[length(out) + 1]] <- test |> transmute(date, hour, cable, actual, model = as.numeric(predict(f$model, design(test), s = f$lambda)),
                                               yesterday = flow_d1, last_week = flow_d7)
  if (k == length(months)) {
    b <- as.matrix(coef(f$model, s = f$lambda))
    coefs[[cb]] <- tibble(cable = cb, term = rownames(b), coef = b[, 1]) |> filter(coef != 0)
  }
}
fc <- bind_rows(out)

# scored days: not tuning days, from 1 march, every cable forecast for all 24 hours
scored <- fc |> filter(date >= first_scored, !tuning(date)) |>
  filter(n() == 24 * length(cables), .by = date)

nw_test <- function(x, lags = 7) {
  x <- x - mean(x); n <- length(x)
  v <- sum(x^2) / n + 2 * sum(sapply(1:lags, \(k) (1 - k / (lags + 1)) * sum(x[-(1:k)] * x[1:(n - k)]) / n))
  v
}
dm <- function(dd) {
  d_ <- dd$yesterday - dd$model; n <- length(d_); m <- mean(d_)
  t <- m / sqrt(nw_test(d_) / n)
  c(gain = m, t = t, p = 2 * pnorm(-abs(t)))
}
daily <- scored |> summarise(model = mean(abs(actual - model)), yesterday = mean(abs(actual - yesterday)),
                             last_week = mean(abs(actual - last_week)), .by = c(cable, date)) |> arrange(cable, date)
scores <- daily |> group_by(cable) |> group_modify(\(x, ...) {
  t <- dm(x)
  tibble(days = nrow(x), mae_model = mean(x$model), mae_yesterday = mean(x$yesterday), mae_last_week = mean(x$last_week),
         gain_mw = t[["gain"]], dm_t = t[["t"]], p = t[["p"]])
}) |> ungroup() |>
  left_join(scored |> summarise(bias_model = mean(actual - model), mean_abs_flow = mean(abs(actual)), .by = cable), by = "cable") |>
  mutate(p_holm = p.adjust(p, "holm"), beats_yesterday = gain_mw > 0 & p_holm < 0.05,
         better_pct = 100 * gain_mw / mae_yesterday)

dir.create("results", showWarnings = FALSE)
write_csv(fc |> mutate(across(c(model), \(x) round(x, 1))), "results/model_forecasts.csv")
write_csv(scores |> mutate(across(where(is.double), \(x) round(x, 4))), "results/model_scores.csv")
write_csv(bind_rows(coefs) |> mutate(coef = round(coef, 4)), "results/model_coefs.csv")
print(as.data.frame(scores |> mutate(across(where(is.double), \(x) round(x, 3)))))
