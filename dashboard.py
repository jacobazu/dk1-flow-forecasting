# dashboard for the flow forecast, built from what the scripts save:
#   site/index.html   map of denmark's cables, hour by hour: energinet's measured flows and generation (energi data service),
#                     the auction flows and our forecast for dk1's cables, through tomorrow
#   site/record.html  track record (backfilled days marked *), tomorrow, backtest and method
#   python dashboard.py   (needs data/ from the actions cache for the auction flows and prices)

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ACCENT, TEAL, RED, GREEN = "#c2700a", "#0f7c86", "#cf5a3c", "#2e9a63"
INK, GREY, LINE, GRID, BEIGE = "#14202b", "#5d6b78", "#d5dbe1", "#e6eaee", "#c3cbd3"
FONT = "IBM Plex Sans, system-ui, sans-serif"
PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js"
CABLES = {"DK1-DE": "Germany", "DK1-NO2": "Norway", "DK1-GB": "Britain",
          "DK1-NL": "Netherlands", "DK1-SE3": "Sweden", "DK1-DK2": "Great Belt (DK2)"}
GITHUB_ICON = ('<svg width="18" height="18" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 '
               '5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13'
               '-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64'
               '-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36'
               '.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95'
               '.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/></svg>')


def mw(x):
    return "not published" if pd.isna(x) else f"{x:,.0f} MW"


def to_html(fig, height):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), font=dict(family=FONT, color=GREY, size=12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      legend=dict(orientation="h", x=0, y=-0.12, font=dict(color=INK)),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor=LINE, font=dict(color=INK, family=FONT)))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINE, color=GREY)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=BEIGE, color=GREY)
    return fig.to_html(full_html=False, include_plotlyjs=False, config=dict(displayModeBar=False, responsive=True))


def card(title, body, note=""):
    return f"<div class='card'><div class='card-title'>{title}</div>{body}{note and f'<p class=note>{note}</p>'}</div>"


def table(df, num=()):
    head = "".join(f"<th{' class=n' if c in num else ''}>{c}</th>" for c in df.columns)
    rows = "".join("<tr>" + "".join(f"<td{' class=n' if c in num else ''}>{v}</td>" for c, v in r.items()) + "</tr>"
                   for _, r in df.iterrows())
    return f"<table><tr>{head}</tr>{rows}</table>"


def actual_flows():
    p = Path("data/flows_hourly.csv")
    if not p.exists():
        return pd.DataFrame(columns=["date", "hour", "cable", "actual"])
    f = pd.read_csv(p, parse_dates=["time_utc"])
    f = f[f["type"] == "auction"]
    t = f["time_utc"].dt.tz_localize("UTC").dt.tz_convert("Europe/Copenhagen") if f["time_utc"].dt.tz is None else \
        f["time_utc"].dt.tz_convert("Europe/Copenhagen")
    return pd.DataFrame({"date": t.dt.strftime("%Y-%m-%d"), "hour": t.dt.hour, "cable": f["cable"], "actual": f["net"]})


def tomorrow_tab(live):
    if live.empty:
        return card("Tomorrow", "<p>No live forecast saved yet.</p>")
    day = live["date"].max()
    d = live[live["date"] == day]
    fig = make_subplots(rows=2, cols=3, subplot_titles=[CABLES[c] for c in CABLES], vertical_spacing=0.14)
    for i, c in enumerate(CABLES):
        x = d[d["cable"] == c].sort_values("hour")
        r, k = i // 3 + 1, i % 3 + 1
        fig.add_trace(go.Scatter(x=x["hour"], y=x["forecast"], name="Forecast", line=dict(color=ACCENT, width=2.5),
                                 showlegend=i == 0, legendgroup="f"), r, k)
        fig.add_trace(go.Scatter(x=x["hour"], y=x["yesterday"], name="Same hour today", line=dict(color=BEIGE, dash="dot"),
                                 showlegend=i == 0, legendgroup="y"), r, k)
    fig.update_annotations(font=dict(color=INK, size=13))
    made = d["made_utc"].iloc[0]
    summary = (d.groupby("cable")[["forecast", "yesterday"]].mean().reindex(list(CABLES)).reset_index())
    summary = pd.DataFrame({"Cable": [CABLES[c] for c in summary["cable"]],
                            "Forecast, day average": summary["forecast"].map(mw),
                            "Today, day average": summary["yesterday"].map(mw)})
    return (card(f"Net auction flow per hour, {day}", to_html(fig, 520),
                 f"MW, plus means export from DK1, minus import. Saved {made} UTC, before the noon auction, and never changed. "
                 "The dotted line is the simplest guess: the same hour today.")
            + card("Day averages", table(summary, num=summary.columns[1:])))


def score(fc, actual):
    """forecast rows joined to the auction flows, only days with all 24 hours on every cable"""
    s = fc.merge(actual, on=["date", "hour", "cable"]).dropna(subset=["actual"])
    full = s.groupby("date")["hour"].count()
    s = s[s["date"].isin(full[full == 24 * len(CABLES)].index)]
    return s.assign(e_m=(s["actual"] - s["forecast"]).abs(), e_y=(s["actual"] - s["yesterday"]).abs())


def record_tab(live, backfill, actual):
    """one track record: live days and backfilled days (marked *) scored together, files kept apart"""
    fc = pd.concat([backfill.assign(kind="backfill"), live.assign(kind="live")], ignore_index=True)
    title = "Track record"
    if fc.empty:
        return card(title, "<p>No forecast saved yet.</p>")
    s = score(fc, actual)
    if s.empty:
        return card(title, f"<p>From {fc['date'].min()}. The first day is scored once its auction flows are out.</p>")
    g = s.groupby("cable")[["e_m", "e_y"]].mean().reindex(list(CABLES))
    days = s.groupby("cable")["date"].nunique().reindex(g.index)
    bdays = s[s["kind"] == "backfill"].groupby("cable")["date"].nunique().reindex(g.index).fillna(0).astype(int)
    lv = s[s["kind"] == "live"].groupby("cable")[["e_m", "e_y"]].mean().reindex(g.index)
    t = pd.DataFrame({"Cable": [CABLES[c] for c in g.index],
                      "Days": [f"{d} ({b}*)" if b else str(d) for d, b in zip(days.values, bdays.values)],
                      "Error, model": g["e_m"].map(mw), "Error, same hour yesterday": g["e_y"].map(mw),
                      "Model better by": ((1 - g["e_m"] / g["e_y"]) * 100).map(lambda v: "–" if pd.isna(v) else f"{v:.0f}%"),
                      "Better by, live days only": ((1 - lv["e_m"] / lv["e_y"]) * 100).map(
                          lambda v: "–" if pd.isna(v) else f"{v:.0f}%")})
    daily = s.groupby(["date", "cable", "kind"])[["e_m", "e_y"]].mean().reset_index()
    fig = go.Figure()
    for c in CABLES:
        x = daily[daily["cable"] == c]
        fig.add_trace(go.Scatter(x=x["date"], y=x["e_y"] - x["e_m"], name=CABLES[c], mode="lines+markers",
                                 marker=dict(symbol=["star-open" if k == "backfill" else "circle" for k in x["kind"]], size=8),
                                 customdata=x["kind"], hovertemplate="%{x}: %{y:,.0f} MW (%{customdata})<extra>%{fullData.name}</extra>"))
    fig.add_hline(y=0, line=dict(color=BEIGE))
    nb = s.loc[s["kind"] == "backfill", "date"].nunique()
    star = (f"* {nb} of {s['date'].nunique()} days are backfilled: made afterwards, but only from what was published before "
            "each auction and fit only on earlier days, exactly as the live run would have. They are kept in their own file, "
            "forecasts/flow_backfill.csv. All other days were saved before the noon auction and never changed. "
            "Only days with all 24 hours on every cable.") if nb else \
        "Saved before the noon auction and never changed. Only days with all 24 hours on every cable."
    return (card(f"{title}, mean absolute error per hour, {s['date'].min()} to {s['date'].max()}", table(t, num=t.columns[1:]), star)
            + card("Model's gain over yesterday per day", to_html(fig, 320),
                   "MW. Above zero: the model was closer than the same hour yesterday. Stars are backfilled days."))


def record_summary(live, backfill, actual):
    """a few numbers for the map's side panel"""
    out = []
    fc = pd.concat([backfill.assign(kind="backfill"), live.assign(kind="live")], ignore_index=True)
    s = score(fc, actual) if not fc.empty else fc
    if not s.empty:
        m, y = s["e_m"].mean(), s["e_y"].mean()
        nb = s.loc[s["kind"] == "backfill", "date"].nunique()
        tail = f", {nb} of them backfilled*" if nb else ""
        out.append(f"<p><b>{m:,.0f} MW</b> over {s['date'].nunique()} days{tail}, against {y:,.0f} MW for the same hour yesterday</p>")
    sc = pd.read_csv("results/model_scores.csv")
    for _, r in sc[sc["beats_yesterday"]].iterrows():
        out.append(f"<p><b>−{r['better_pct']:.0f}%</b> error on the cable to {CABLES[r['cable']]} in the backtest</p>")
    return "".join(out)


def backtest_tab():
    sc = pd.read_csv("results/model_scores.csv").set_index("cable").reindex(list(CABLES))
    t = pd.DataFrame({
        "Cable": [CABLES[c] for c in sc.index], "Days": sc["days"].astype(int).values,
        "Model": sc["mae_model"].map(mw), "Same hour yesterday": sc["mae_yesterday"].map(mw),
        "Same hour last week": sc["mae_last_week"].map(mw), "Better by": sc["better_pct"].map(lambda v: f"{v:.0f}%"),
        "p (Holm)": sc["p_holm"].map(lambda v: "<0.001" if v < 0.001 else f"{v:.3f}"),
        "Beats yesterday": sc["beats_yesterday"].map(lambda b: "Yes" if b else "No")})
    fig = go.Figure()
    names = [CABLES[c] for c in sc.index]
    fig.add_bar(x=names, y=sc["mae_model"], name="Model", marker_color=ACCENT)
    fig.add_bar(x=names, y=sc["mae_yesterday"], name="Same hour yesterday", marker_color=TEAL)
    fig.add_bar(x=names, y=sc["mae_last_week"], name="Same hour last week", marker_color=BEIGE)
    fig.update_layout(barmode="group", yaxis_title="MW")
    ma = pd.read_csv("results/measured_vs_auction.csv").set_index("cable").reindex(list(CABLES))
    m = pd.DataFrame({"Cable": [CABLES[c] for c in ma.index], "Average |measured − auction|": ma["mean_abs_diff_mw"].map(mw),
                      "Average measured − auction": ma["mean_diff_mw"].map(mw)})
    wins = [CABLES[c] for c in sc.index if sc.loc[c, "beats_yesterday"]]
    lead = (f"The model beats the same hour yesterday on {len(wins)} of 6 cables by the rules ({', '.join(wins) or 'none'}). "
            "It is closer on most cables, but on the others the gain is too small to rule out luck after correcting for six tests.")
    return (card("Backtest, 1 Mar – 10 Oct 2026, mean absolute error per hour", f"<p>{lead}</p>" + table(t, num=t.columns[1:7]),
                 "Days where the price and wind backtests exist. Tuning days (every 7th) are left out. Diebold-Mariano on daily "
                 "errors with Newey-West (7 lags), Holm over the six cables, p < 0.05. Rules written before any result: RULES.md.")
            + card("Error per cable", to_html(fig, 340))
            + card("Measured flow against the auction flow (shown, not forecast)", table(m, num=m.columns[1:]),
                   "ENTSO-E physical flows minus scheduled day-ahead flows, same days. Plus: more flowed out of DK1 than the auction set."))


def method_tab():
    return card("How it works", """
<p>Each morning before the noon auction, the model forecasts tomorrow's net flow on each of DK1's six cables, hour by hour,
from what is known by then: our DK1 price forecast, our offshore, onshore and solar forecasts, the neighbours' prices and the
cable's flow for the same hour today and a week ago, plus hour, weekday and holidays.</p>
<p>One lasso regression per cable, refit on the first of each month on earlier days. The penalty is the one that did best on the
earlier tuning days (every 7th day), which are never scored. The benchmark is the same hour yesterday, the better of the two
simple guesses on every cable.</p>
<p>Data: ENTSO-E (auction and measured flows, prices), and the forecasts saved by
<a href="https://jacobazu.github.io/dk1-price-forecasting">the price forecast</a> and
<a href="https://jacobazu.github.io/dk1-renewables-forecasting">the wind forecast</a>.</p>""")


def render(tabs):
    built = datetime.now(timezone.utc)
    nav = "".join(f"<button data-tab='t{i}'{' class=active' if i == 0 else ''}>{k}</button>" for i, k in enumerate(tabs))
    panes = "".join(f"<section id='t{i}'{' class=active' if i == 0 else ''}>{v}</section>" for i, v in enumerate(tabs.values()))
    updated = pd.Timestamp(built).tz_convert("Europe/Copenhagen").strftime("%d %b %Y %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DK1 cable flow forecast</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="{PLOTLY_JS}"></script>
<style>
  body {{ margin: 0; color: {INK}; font: 15px/1.5 {FONT}; background: #f3f5f7; }}
  header {{ background: #ffffff; padding: 8px 20px; border-bottom: 1px solid {LINE}; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 20px; }}
  header h1 {{ font-size: 17px; font-weight: 600; margin: 10px 8px 10px 0; }}
  nav {{ display: flex; flex-wrap: wrap; gap: 2px; }}
  nav button {{ font: 500 14.5px {FONT}; color: {GREY}; background: none; border: 0; padding: 7px 15px; border-radius: 99px; cursor: pointer; }}
  nav button:hover {{ color: {INK}; }}
  nav button.active {{ color: #ffffff; background: {INK}; }}
  header .links {{ margin-left: auto; font-size: 14px; display: flex; align-items: center; gap: 16px; }}
  header .links a {{ color: {GREY}; text-decoration: none; }}
  header .links svg {{ display: block; fill: {INK}; }}
  main {{ max-width: 1280px; margin: 0 auto; padding: 18px 16px 40px; }}
  section {{ display: none; }} section.active {{ display: block; }}
  .card {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 14px; padding: 16px 20px; margin-bottom: 18px; min-width: 0; }}
  .card-title {{ font-weight: 500; margin-bottom: 8px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ text-align: left; padding: 7px 8px 7px 0; border-bottom: 1px solid {LINE}; }}
  th {{ color: {GREY}; font-weight: 500; font-size: 13px; }}
  .n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  p {{ color: #33414e; max-width: 900px; }}
  .note {{ color: {GREY}; font-size: 13px; margin-bottom: 0; }}
  a {{ color: {ACCENT}; }}
  footer {{ color: {GREY}; font-size: 12px; text-align: center; padding-bottom: 24px; }}
  @media (max-width: 900px) {{ header .links {{ margin-left: 0; }} }}
</style>
</head>
<body>
<header><h1>DK1 cable flow forecast</h1><nav>{nav}</nav>
<span class="links"><a href="index.html">Map</a><a href="https://jacobazu.github.io/">jacobazu.github.io</a><a href="https://github.com/jacobazu/dk1-flow-forecasting" aria-label="GitHub">{GITHUB_ICON}</a></span></header>
<main>{panes}</main>
<footer>Updated {updated} (Danish time). Data: ENTSO-E Transparency Platform, Energi Data Service (Energinet), Open-Meteo.com (CC BY 4.0)</footer>
<script>
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("nav button, section").forEach(e => e.classList.remove("active"));
  b.classList.add("active"); document.getElementById(b.dataset.tab).classList.add("active");
  window.dispatchEvent(new Event("resize"));
}});
</script>
</body>
</html>"""


EDS = "https://api.energidataservice.dk/dataset/"
EXCHANGES = {"DK1": {"ExchangeGermany": "DK1-DE", "ExchangeNetherlands": "DK1-NL", "ExchangeGreatBritain": "DK1-GB",
                     "ExchangeNorway": "DK1-NO2", "ExchangeSweden": "DK1-SE3", "ExchangeGreatBelt": "DK1-DK2"},
             "DK2": {"ExchangeGermany": "DK2-DE", "ExchangeSweden": "DK2-SE4", "BornholmSE4": "BH-SE4"}}
SOURCES = {"OnshoreWindPower": "onshore", "ProductionGe100MW": "large", "OffshoreWindPower": "offshore",
           "SolarPower": "solar", "ProductionLt100MW": "small"}


def eds(dataset, start, end):
    """one energi data service dataset between two danish times; waits out the rate limit"""
    import re
    import time
    import requests
    for attempt in range(6):
        r = requests.get(EDS + dataset, params={"start": start, "end": end, "limit": 0}, timeout=90)
        if r.status_code == 429:
            wait = re.search(r"(\d+) seconds", r.text)
            time.sleep(int(wait.group(1)) + 2 if wait else 30)
            continue
        r.raise_for_status()
        return pd.DataFrame(r.json()["records"])
    raise RuntimeError(f"{dataset}: rate limited")


def measured(start, end):
    """energinet's real-time generation and cable flows, five-minute readings averaged to danish hours.
    flows are turned to + = out of the danish side (energinet gives + = into the area)"""
    try:
        d = eds("ElectricityProdex5MinRealtime", start, end)
    except Exception as e:                                   # the map still shows the forecast without it
        print("energi data service failed:", e)
        return pd.DataFrame()
    d["hour"] = pd.to_datetime(d["Minutes5DK"]).dt.floor("h")
    cols = list(SOURCES) + sorted({c for m in EXCHANGES.values() for c in m})
    d[cols] = d[cols].apply(pd.to_numeric, errors="coerce")
    return d.groupby(["PriceArea", "hour"])[cols].mean().reset_index()


def local(df, col="time_utc"):
    t = pd.to_datetime(df[col], utc=True).dt.tz_convert("Europe/Copenhagen")
    return df.assign(key=t.dt.strftime("%Y-%m-%d %H"))


def map_data(live, backfill, actual):
    import rebase
    now = pd.Timestamp.now(tz="Europe/Copenhagen")
    start = (now.normalize() - pd.Timedelta(days=7)).tz_localize(None)
    hours = [t.strftime("%Y-%m-%d %H") for t in pd.date_range(start, start + pd.Timedelta(days=8, hours=23), freq="h")]
    idx = {h: i for i, h in enumerate(hours)}
    blank = lambda: [None] * len(hours)

    # the region from the rebase grid api; the page still works for denmark if it fails
    try:
        R = rebase.region(hours)
    except Exception as e:
        print("rebase failed:", e)
        R = {"zones": [{"id": s_, "name": n, "at": at} for s_, n, at in rebase.ZONES.values()],
             "gen": {}, "load": {}, "price": {}, "flows": []}

    # denmark's generation from energinet's real-time data: fresher, and split into wind, solar and thermal plants
    m = measured(start.strftime("%Y-%m-%dT%H:%M"), now.tz_localize(None).strftime("%Y-%m-%dT%H:%M"))
    detail = {a: {k: blank() for k in SOURCES.values()} for a in ("DK1", "DK2")}
    if not m.empty:
        cur_key = now.strftime("%Y-%m-%d %H")
        for _, r in m.iterrows():
            k = r["hour"].strftime("%Y-%m-%d %H")
            if k not in idx or k == cur_key or r["PriceArea"] not in detail:
                continue
            for c, name in SOURCES.items():
                if pd.notna(r[c]):
                    detail[r["PriceArea"]][name][idx[k]] = round(float(r[c]))
        for a, d in detail.items():
            g = {f: blank() for f in rebase.FUELS}
            for i in range(len(hours)):
                if d["offshore"][i] is None:
                    continue
                for f in rebase.FUELS:
                    g[f][i] = 0
                g["wind"][i] = (d["offshore"][i] or 0) + (d["onshore"][i] or 0)
                g["solar"][i] = d["solar"][i] or 0
                g["other"][i] = (d["large"][i] or 0) + (d["small"][i] or 0)
            R["gen"][a] = g

    # prices from our own entso-e download where the api has none
    p = Path("data/prices_hourly.csv")
    if p.exists():
        pr = local(pd.read_csv(p))
        pr = pr[pr["key"].isin(idx)].groupby(["zone", "key"])["price"].mean().reset_index()
        for z, g in pr.groupby("zone"):
            cur = R["price"].setdefault(z, blank())
            for _, r in g.iterrows():
                if cur[idx[r["key"]]] is None:
                    cur[idx[r["key"]]] = round(float(r["price"]), 1)

    # dk1's cables: auction flows and our forecast, turned to each border's own direction
    sign = {c: (1 if b.split(":")[1].split("~")[0] == "DK-DK1" else -1) for c, b in rebase.DK_CABLES.items()}
    auc = {b: blank() for b in rebase.DK_CABLES.values()}
    fcs = {b: blank() for b in rebase.DK_CABLES.values()}
    kind = blank()
    dk1_auc, dk1_fc = blank(), blank()
    if not actual.empty:
        a_ = actual.assign(key=actual["date"] + " " + actual["hour"].astype(int).map("{:02d}".format))
        for _, r in a_[a_["key"].isin(idx)].iterrows():
            auc[rebase.DK_CABLES[r["cable"]]][idx[r["key"]]] = round(sign[r["cable"]] * float(r["actual"]))
    fc = pd.concat([backfill.assign(kind="backfill"), live.assign(kind="live")])
    fc = fc.drop_duplicates(["date", "hour", "cable"], keep="last")
    fc["key"] = fc["date"].astype(str) + " " + fc["hour"].astype(int).map("{:02d}".format)
    for _, r in fc[fc["key"].isin(idx)].iterrows():
        fcs[rebase.DK_CABLES[r["cable"]]][idx[r["key"]]] = round(sign[r["cable"]] * float(r["forecast"]))
        kind[idx[r["key"]]] = r["kind"]
    for i in range(len(hours)):
        for src, out in ((auc, dk1_auc), (fcs, dk1_fc)):
            v = [src[rebase.DK_CABLES[c]][i] for c in rebase.DK_CABLES]
            if all(x is not None for x in v):
                out[i] = sum(sign[c] * src[rebase.DK_CABLES[c]][i] for c in rebase.DK_CABLES)

    # the latest hour most zones have generation for
    def has(z, i):
        g = R["gen"].get(z)
        return bool(g) and any(g[f][i] is not None for f in g)
    zs = [z["id"] for z in R["zones"]]
    measured_hours = [i for i in range(len(hours)) if sum(has(z, i) for z in zs) >= max(1, 0.6 * len(zs))
                      or (len(R["gen"]) <= 2 and has("DK1", i))]
    last_measured = max(measured_hours) if measured_hours else -1

    keep = [i for i in range(len(hours)) if i <= last_measured or kind[i] is not None or dk1_auc[i] is not None
            or (R["price"].get("DK1") and R["price"]["DK1"][i] is not None)]
    n = max(keep) + 1 if keep else len(hours)
    cut = lambda v: v[:n]
    deep = lambda d: {k: (deep(v) if isinstance(v, dict) else cut(v)) for k, v in d.items()}
    return {"hours": hours[:n], "last_measured": last_measured, "fuels": rebase.FUELS, "zones": R["zones"],
            "gen": deep(R["gen"]), "load": deep(R["load"]), "price": deep(R["price"]),
            "flows": [dict(f, v=cut(f["v"])) for f in R["flows"]], "dk_detail": deep(detail),
            "cables": {c: b for c, b in rebase.DK_CABLES.items()}, "auc": deep(auc), "fc": deep(fcs),
            "fc_kind": cut(kind), "dk1_auc": cut(dk1_auc), "dk1_fc": cut(dk1_fc),
            "record_html": record_summary(live, backfill, actual)}


def read_fc(name):
    p = Path(f"forecasts/{name}")
    cols = ["made_utc", "date", "hour", "cable", "forecast", "yesterday"]
    return pd.read_csv(p, dtype={"date": str}) if p.exists() else pd.DataFrame(columns=cols)


def main():
    import json
    live, backfill, actual = read_fc("flow_live.csv"), read_fc("flow_backfill.csv"), actual_flows()
    if not backfill.empty and not live.empty:
        backfill = backfill[~backfill["date"].isin(set(live["date"]))]
    Path("site").mkdir(exist_ok=True)
    data = map_data(live, backfill, actual)
    page = Path("assets/map.html").read_text(encoding="utf-8")
    page = page.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    Path("site/index.html").write_text(page, encoding="utf-8")
    tabs = {"Track record": record_tab(live, backfill, actual),
            "Tomorrow": tomorrow_tab(live if not live.empty else backfill),
            "Backtest": backtest_tab(), "Method": method_tab()}
    Path("site/record.html").write_text(render(tabs), encoding="utf-8")
    print("wrote site/index.html and site/record.html,", len(data["hours"]), "hours, last measured", data["last_measured"],
          len(data["flows"]), "borders")


if __name__ == "__main__":
    main()
