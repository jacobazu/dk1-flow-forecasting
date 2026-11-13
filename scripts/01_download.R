# download dk1's cable flows from entso-e, from 2023 to tomorrow, and the neighbours' day-ahead prices.
#   auction flows: scheduled commercial exchanges, day-ahead (A09)
#   measured flows: physical flows (A11)
#   prices: day-ahead prices (A44) for dk1 and the neighbours
# entso-e leaves out a point when it repeats the one before (curve type A03), so every period is rebuilt to its
# full length and the gaps take the last value given. quarter-hours are averaged to hours (utc).
# a run with the files already there only fetches from three days before their last hour.
# writes data/flows_hourly.csv (time_utc, cable, type, export, import, net; + = out of dk1) and data/prices_hourly.csv

library(httr2)
library(xml2)
library(dplyr)
library(tidyr)
library(readr)
library(lubridate)

dk1 <- "10YDK-1--------W"
nb <- c(DE = "10Y1001A1001A82H", NL = "10YNL----------L", GB = "10YGB----------A",
        NO2 = "10YNO-2--------T", SE3 = "10Y1001A1001A46L", DK2 = "10YDK-2--------M")
zones <- c(DK1 = dk1, nb[names(nb) != "GB"])
first_day <- as_datetime("2023-01-01")
end <- floor_date(now("UTC"), "day") + days(2)
token <- Sys.getenv("ENTSOE_TOKEN")
if (token == "") stop("ENTSOE_TOKEN is not set")

entsoe_xml <- function(q) {
  resp <- request("https://web-api.tp.entsoe.eu/api") |>
    req_url_query(securityToken = token, !!!q) |> req_timeout(120) |>
    req_retry(max_tries = 4, backoff = \(i) 10 * i, is_transient = \(r) resp_status(r) %in% c(429, 500, 502, 503)) |>
    req_error(is_error = \(r) FALSE) |> req_perform()
  raw <- resp_body_raw(resp)
  if (length(raw) > 2 && raw[1] == as.raw(0x50) && raw[2] == as.raw(0x4b)) {      # zipped: one xml per file
    zf <- tempfile(fileext = ".zip"); writeBin(raw, zf); d <- tempfile(); unzip(zf, exdir = d)
    return(lapply(list.files(d, full.names = TRUE), read_xml))
  }
  list(read_xml(raw))
}

# every point of every period, gaps filled with the last value given
points <- function(doc, value = "quantity") {
  xml_ns_strip(doc)
  if (xml_name(doc) == "Acknowledgement_MarketDocument") return(tibble())
  bind_rows(lapply(xml_find_all(doc, "//TimeSeries/Period"), \(p) {
    start <- ymd_hm(xml_text(xml_find_first(p, "timeInterval/start")))
    stop_ <- ymd_hm(xml_text(xml_find_first(p, "timeInterval/end")))
    res <- xml_text(xml_find_first(p, "resolution"))
    step <- switch(res, PT15M = 15, PT30M = 30, PT60M = 60, stop("resolution ", res))
    n <- as.numeric(difftime(stop_, start, units = "mins")) / step
    pos <- as.integer(xml_text(xml_find_all(p, "Point/position")))
    val <- as.numeric(xml_text(xml_find_all(p, paste0("Point/", value))))
    full <- rep(NA_real_, n); full[pos] <- val
    for (i in seq_len(n)[-1]) if (is.na(full[i])) full[i] <- full[i - 1]
    tibble(time = start + minutes(step * (seq_len(n) - 1)), step = step, value = full)
  }))
}

chunks <- function(from) {
  s <- seq(floor_date(from, "quarter"), end, by = "3 months")
  tibble(from = pmax(s, from), to = pmin(s + months(3), end))
}

# hourly means; where a series comes both in quarter-hours and in hours, the quarter-hours are used
hourly <- function(x) {
  keys <- setdiff(names(x), c("time", "step", "value"))
  x |> mutate(time_utc = floor_date(time, "hour")) |>
    filter(step == min(step), .by = all_of(c(keys, "time_utc"))) |>
    distinct(across(all_of(keys)), time, .keep_all = TRUE) |>
    summarise(value = mean(value, na.rm = TRUE), .by = all_of(c(keys, "time_utc")))
}

flows_file <- "data/flows_hourly.csv"; prices_file <- "data/prices_hourly.csv"
fmt <- \(t) format(t, "%Y%m%d%H%M", tz = "UTC")
docs <- list(auction = list(documentType = "A09", contract_MarketAgreement.Type = "A01"),
             measured = list(documentType = "A11"))
dir.create("data", showWarnings = FALSE)

# each file is rewritten after every quarter, so a run that is stopped keeps what it got and the next run
# carries on from there. a quarter where any request failed is not written, so it is fetched again next time
fetch <- function(file, requests, shape, arrange_by) {
  old <- if (file.exists(file)) read_csv(file, show_col_types = FALSE) else NULL
  from <- if (is.null(old)) first_day else floor_date(max(old$time_utc), "day") - days(3)
  message(file, ": from ", from, " to ", end)
  ch <- chunks(from)
  for (k in seq_len(nrow(ch))) {
    got <- list(); ok <- TRUE
    for (r in requests) {
      q <- c(r$q, list(periodStart = fmt(ch$from[k]), periodEnd = fmt(ch$to[k])))
      pts <- tryCatch(bind_rows(lapply(entsoe_xml(q), points, value = r$value)),
                      error = \(e) { message("  failed: ", conditionMessage(e)); ok <<- FALSE; tibble() })
      message(format(ch$from[k], "%Y-%m-%d"), " ", r$label, ": ", nrow(pts), " points")
      if (nrow(pts)) got[[length(got) + 1]] <- mutate(pts, !!!as.list(r$tags))
      Sys.sleep(0.3)
    }
    if (!ok) { message("stopped: a request failed, ", format(ch$from[k], "%Y-%m-%d"), " is fetched again next run"); break }
    new <- shape(bind_rows(got))
    keep <- if (is.null(old)) NULL else filter(old, time_utc < ch$from[k])
    old <- bind_rows(keep, filter(new, time_utc >= ch$from[k])) |> arrange(across(all_of(arrange_by)))
    write_csv(old, file)
  }
  old
}

price_requests <- lapply(names(zones), \(z) list(
  q = list(documentType = "A44", in_Domain = zones[[z]], out_Domain = zones[[z]]),
  value = "price.amount", label = paste("price", z), tags = tibble(zone = z)))
prices <- fetch(prices_file, price_requests, \(x) hourly(x) |> rename(price = value), c("zone", "time_utc"))

flow_requests <- list()
for (type in names(docs)) for (b in names(nb)) for (dir in c("export", "import")) {
  if (type == "measured" && b == "GB") next                     # britain publishes no measured flows here
  into <- if (dir == "export") nb[[b]] else dk1; out <- if (dir == "export") dk1 else nb[[b]]
  flow_requests[[length(flow_requests) + 1]] <- list(
    q = c(docs[[type]], list(in_Domain = into, out_Domain = out)), value = "quantity",
    label = paste(type, paste0("DK1-", b), dir), tags = tibble(cable = paste0("DK1-", b), type = type, direction = dir))
}
flows <- fetch(flows_file, flow_requests, \(x) hourly(x) |>
  pivot_wider(names_from = direction, values_from = value) |>
  mutate(export = coalesce(export, 0), import = coalesce(import, 0), net = export - import),
  c("type", "cable", "time_utc"))

print(as.data.frame(flows |> summarise(hours = n(), first = min(time_utc), last = max(time_utc),
                                       mean_net = round(mean(net), 1), .by = c(type, cable))))
print(as.data.frame(prices |> summarise(hours = n(), first = min(time_utc), last = max(time_utc), .by = zone)))
