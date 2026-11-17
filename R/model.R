# the lasso of RULES.md, shared by the backtest and the live run

library(glmnet)

first_test <- as_date("2026-01-01")
tuning <- \(d) as.integer(d - first_test) %% 7 == 0       # every 7th day from 1 jan 2026, never scored

# fit on the non-tuning days; keep the penalty with the lowest mean absolute error on the tuning days
fit_cable <- function(train) {
  fit_rows <- train[!tuning(train$date), ]; tune_rows <- train[tuning(train$date), ]
  m <- glmnet(design(fit_rows), fit_rows$actual, alpha = 1)
  mae <- colMeans(abs(predict(m, design(tune_rows)) - tune_rows$actual))
  list(model = m, lambda = m$lambda[which.min(mae)])
}

predict_cable <- function(f, rows) as.numeric(predict(f$model, design(rows), s = f$lambda))
