# what flow data is there, before any rule or model is written. for each of dk1's cables and both directions:
# the auction flow (entso-e scheduled commercial exchanges, day-ahead), the measured flow (entso-e physical flows)
# and the capacity offered to the auction. one week now and one week in each earlier january, to see how far back
# each goes. also energinet's measured exchanges per cable. writes results/data_check.csv

library(httr2)
library(dplyr)
library(readr)
library(lubridate)

dk1 <- "10YDK-1--------W"
nb  <- c(DE = "10Y1001A1001A82H", NO2 = "10YNO-2--------T", SE3 = "10Y1001A1001A46L",
         NL = "10YNL----------L", GB = "10YGB----------A", DK2 = "10YDK-2--------M")
docs <- list(
  auction  = list(documentType = "A09", contract_MarketAgreement.Type = "A01"),
  measured = list(documentType = "A11"),
  capacity = list(documentType = "A61", contract_MarketAgreement.Type = "A01"))
weeks <- list(now = floor_date(Sys.time(), "day") - days(7), y2025 = as_datetime("2025-01-06"),
              y2024 = as_datetime("2024-01-08"), y2023 = as_datetime("2023-01-09"))

tag <- \(x, name) regmatches(x, gregexpr(paste0("(?<=<", name, ">)[^<]*"), x, perl = TRUE))[[1]]

entsoe <- function(doc, from, to, into, out) {
  q <- c(list(securityToken = Sys.getenv("ENTSOE_TOKEN"), in_Domain = into, out_Domain = out,
              periodStart = format(from, "%Y%m%d%H%M", tz = "UTC"), periodEnd = format(to, "%Y%m%d%H%M", tz = "UTC")), doc)
  resp <- request("https://web-api.tp.entsoe.eu/api") |> req_url_query(!!!q) |> req_timeout(60) |>
    req_retry(max_tries = 3) |> req_error(is_error = \(r) FALSE) |> req_perform()
  raw <- resp_body_raw(resp)
  txt <- if (length(raw) > 2 && raw[1] == as.raw(0x50) && raw[2] == as.raw(0x4b)) {
    zf <- tempfile(fileext = ".zip"); writeBin(raw, zf); d <- tempfile(); unzip(zf, exdir = d)
    paste(vapply(list.files(d, full.names = TRUE), \(f) paste(readLines(f, warn = FALSE), collapse = "\n"), ""), collapse = "\n")
  } else rawToChar(raw)
  qty <- as.numeric(tag(txt, "quantity"))
  res <- unique(tag(txt, "resolution"))
  why <- paste(tag(txt, "text"), collapse = " ")
  tibble(status = resp_status(resp), points = length(qty), resolution = paste(res, collapse = "/"),
         mean_mw = if (length(qty)) round(mean(qty), 1) else NA, max_mw = if (length(qty)) max(qty) else NA,
         note = substr(why, 1, 120))
}

if (Sys.getenv("ENTSOE_TOKEN") == "") stop("ENTSOE_TOKEN is not set")
out <- list()
for (w in names(weeks)) for (d in names(docs)) for (b in names(nb)) for (dir in c("export", "import")) {
  if (d == "measured" && w != "now" && dir == "import") next
  into <- if (dir == "export") nb[[b]] else dk1; from_ <- if (dir == "export") dk1 else nb[[b]]
  r <- tryCatch(entsoe(docs[[d]], weeks[[w]], weeks[[w]] + days(7), into, from_),
                error = \(e) tibble(status = NA, points = 0, resolution = "", mean_mw = NA, max_mw = NA, note = conditionMessage(e)))
  out[[length(out) + 1]] <- mutate(r, source = "entso-e", data = d, cable = paste0("DK1-", b), direction = dir, week = w, .before = 1)
  message(w, " ", d, " DK1-", b, " ", dir, ": ", r$points, " points ", r$resolution, " ", r$note)
  Sys.sleep(0.5)
}

# energinet's measured exchange per cable, hourly settlement
eds <- tryCatch({
  x <- request("https://api.energidataservice.dk/dataset/ProductionConsumptionSettlement") |>
    req_url_query(start = format(Sys.Date() - 30), end = format(Sys.Date()), filter = '{"PriceArea":["DK1"]}', limit = 0) |>
    req_retry(max_tries = 3) |> req_perform() |> resp_body_json(simplifyVector = TRUE)
  r <- x$records
  cols <- grep("^Exchange", names(r), value = TRUE)
  tibble(source = "energi data service", data = "measured, settlement", cable = cols, direction = "net",
         week = "last 30 days", status = 200, points = vapply(cols, \(c) sum(!is.na(r[[c]])), 1),
         resolution = "hourly", mean_mw = vapply(cols, \(c) round(mean(r[[c]], na.rm = TRUE), 1), 1),
         max_mw = vapply(cols, \(c) suppressWarnings(max(abs(r[[c]]), na.rm = TRUE)), 1), note = "")
}, error = \(e) tibble(source = "energi data service", data = "measured, settlement", note = conditionMessage(e)))

dir.create("results", showWarnings = FALSE)
res <- bind_rows(bind_rows(out), eds)
write_csv(res, "results/data_check.csv")
print(as.data.frame(res |> filter(source == "entso-e") |> group_by(week, data) |>
  summarise(cables_with_data = n_distinct(cable[points > 0]), .groups = "drop")))
