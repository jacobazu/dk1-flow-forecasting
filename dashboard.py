# dashboard for the flow forecast, built from what the scripts save:
#   site/index.html   map of denmark's cables, hour by hour: energinet's measured flows and generation (energi data service),
#                     the auction flows and our forecast for dk1's cables, through tomorrow
#   site/record.html  live record, backfilled days, tomorrow, backtest and method
#   python dashboard.py   (needs data/ from the actions cache for the auction flows and prices)

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ACCENT, TEAL, RED, GREEN = "#e9b949", "#3c8ed8", "#c8553a", "#1b9a85"
INK, GREY, LINE, GRID, BEIGE = "#ececec", "#8b9099", "#24262b", "#1b1d21", "#4a4e56"
FONT = "Inter, system-ui, sans-serif"
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
                      hoverlabel=dict(bgcolor="#16181b", bordercolor=LINE, font=dict(color=INK, family=FONT)))
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


def record_tab(fc, actual, title, empty, note):
    if fc.empty:
        return card(title, f"<p>{empty}</p>")
    s = score(fc, actual)
    if s.empty:
        return card(title, f"<p>From {fc['date'].min()}. The first day is scored once its auction flows are out.</p>")
    g = s.groupby("cable")[["e_m", "e_y"]].mean().reindex(list(CABLES))
    t = pd.DataFrame({"Cable": [CABLES[c] for c in g.index], "Days": s.groupby("cable")["date"].nunique().reindex(g.index).values,
                      "Error, model": g["e_m"].map(mw), "Error, same hour yesterday": g["e_y"].map(mw),
                      "Model better by": ((1 - g["e_m"] / g["e_y"]) * 100).map(lambda v: "–" if pd.isna(v) else f"{v:.0f}%")})
    daily = s.groupby(["date", "cable"])[["e_m", "e_y"]].mean().reset_index()
    fig = go.Figure()
    for c in CABLES:
        x = daily[daily["cable"] == c]
        fig.add_trace(go.Scatter(x=x["date"], y=x["e_y"] - x["e_m"], name=CABLES[c], mode="lines+markers"))
    fig.add_hline(y=0, line=dict(color=BEIGE))
    return (card(f"{title}, mean absolute error per hour, {s['date'].min()} to {s['date'].max()}", table(t, num=t.columns[1:]), note)
            + card("Model's gain over yesterday per day", to_html(fig, 320), "MW. Above zero: the model was closer than the same hour yesterday."))


def record_summary(live, backfill, actual):
    """two short lines for the map's side panel"""
    out = []
    for fc, name in ((live, "Live"), (backfill, "Backfilled")):
        if fc.empty:
            out.append(f"<p>{name}: no days yet.</p>" if name == "Live" else "")
            continue
        s = score(fc, actual)
        if s.empty:
            out.append(f"<p>{name}: from {fc['date'].min()}, scored once the auction flows are out.</p>")
            continue
        m, y = s["e_m"].mean(), s["e_y"].mean()
        out.append(f"<p>{name}, {s['date'].nunique()} days: off by {m:,.0f} MW per cable and hour, against {y:,.0f} MW "
                   f"for the same hour yesterday ({(1 - m / y) * 100:+.0f}%).</p>".replace("(+", "(better by ").replace("(-", "(worse by "))
    out.append("<p>Backtest, 186 days: better than yesterday on all cables but Sweden and the Great Belt; "
               "only Germany passes the test (16%).</p>")
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@600&display=swap" rel="stylesheet">
<script src="{PLOTLY_JS}"></script>
<style>
  body {{ margin: 0; color: {INK}; font: 15px/1.5 {FONT}; background: #0b0c0e; }}
  header {{ padding: 8px 20px; border-bottom: 1px solid {LINE}; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 20px; }}
  header h1 {{ font-size: 17px; font-weight: 600; margin: 10px 8px 10px 0; }}
  nav {{ display: flex; flex-wrap: wrap; gap: 2px; }}
  nav button {{ font: 500 14.5px {FONT}; color: {GREY}; background: none; border: 0; padding: 7px 15px; border-radius: 99px; cursor: pointer; }}
  nav button:hover {{ color: {INK}; }}
  nav button.active {{ color: #0b0c0e; background: {INK}; }}
  header .links {{ margin-left: auto; font-size: 14px; display: flex; align-items: center; gap: 16px; }}
  header .links a {{ color: {GREY}; text-decoration: none; }}
  header .links svg {{ display: block; fill: {INK}; }}
  header h1 {{ font-family: "Inter Tight", {FONT}; }}
  main {{ max-width: 1280px; margin: 0 auto; padding: 18px 16px 40px; }}
  section {{ display: none; }} section.active {{ display: block; }}
  .card {{ border: 1px solid {LINE}; border-radius: 14px; padding: 16px 20px; margin-bottom: 18px; min-width: 0; }}
  .card-title {{ font-weight: 500; margin-bottom: 8px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ text-align: left; padding: 7px 8px 7px 0; border-bottom: 1px solid {LINE}; }}
  th {{ color: {GREY}; font-weight: 500; font-size: 13px; }}
  .n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  p {{ color: #c9ccd2; max-width: 900px; }}
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
    now = pd.Timestamp.now(tz="Europe/Copenhagen")
    start = (now.normalize() - pd.Timedelta(days=7)).tz_localize(None)
    m = measured(start.strftime("%Y-%m-%dT%H:%M"), now.tz_localize(None).strftime("%Y-%m-%dT%H:%M"))
    fc = pd.concat([backfill.assign(kind="backfill"), live.assign(kind="live")])
    fc = fc.drop_duplicates(["date", "hour", "cable"], keep="last")
    fc["key"] = fc["date"].astype(str) + " " + fc["hour"].astype(int).map("{:02d}".format)
    last = start + pd.Timedelta(days=8, hours=23)                            # through tomorrow
    hours = [t.strftime("%Y-%m-%d %H") for t in pd.date_range(start, last, freq="h")]
    idx = {h: i for i, h in enumerate(hours)}
    blank = lambda: [None] * len(hours)

    gen = {a: {k: blank() for k in SOURCES.values()} for a in ("DK1", "DK2")}
    ex = {c: blank() for m_ in EXCHANGES.values() for c in m_.values()}
    last_measured = -1
    if not m.empty:
        for _, r in m.iterrows():
            i = idx.get(r["hour"].strftime("%Y-%m-%d %H"))
            a = r["PriceArea"]
            if i is None or a not in gen:
                continue
            for c, k in SOURCES.items():
                if pd.notna(r[c]):
                    gen[a][k][i] = round(float(r[c]))
            for c, cab in EXCHANGES[a].items():
                if pd.notna(r[c]):
                    ex[cab][i] = round(-float(r[c]))
            if pd.notna(r["OffshoreWindPower"]) and a == "DK1":
                last_measured = max(last_measured, i)
        # the current hour is still filling up; show the last complete one
        cur_key = now.strftime("%Y-%m-%d %H")
        if last_measured >= 0 and hours[last_measured] == cur_key:
            last_measured -= 1
            for a in gen:
                for k in gen[a]:
                    gen[a][k][last_measured + 1] = None
            for c in ex:
                ex[c][last_measured + 1] = None

    auc = {c: blank() for c in CABLES}
    if not actual.empty:
        a = actual.assign(key=actual["date"] + " " + actual["hour"].astype(int).map("{:02d}".format))
        for _, r in a[a["key"].isin(idx)].iterrows():
            auc[r["cable"]][idx[r["key"]]] = round(float(r["actual"]))
    fcs = {c: blank() for c in CABLES}
    kind = blank()
    for _, r in fc[fc["key"].isin(idx)].iterrows():
        fcs[r["cable"]][idx[r["key"]]] = round(float(r["forecast"]))
        kind[idx[r["key"]]] = r["kind"]

    price = {}
    p = Path("data/prices_hourly.csv")
    if p.exists():
        pr = local(pd.read_csv(p))
        pr = pr[pr["key"].isin(idx)].groupby(["zone", "key"])["price"].mean().reset_index()
        for z, g in pr.groupby("zone"):
            price[z] = blank()
            for _, r in g.iterrows():
                price[z][idx[r["key"]]] = round(float(r["price"]), 1)

    def dk1_sum(src):
        out = []
        for i in range(len(hours)):
            v = [src[c][i] for c in CABLES]
            out.append(None if any(x is None for x in v) else sum(v))
        return out

    # trim trailing hours with nothing at all
    has = [i for i in range(len(hours)) if fcs["DK1-DE"][i] is not None or auc["DK1-DE"][i] is not None
           or (price.get("DK1") and price["DK1"][i] is not None) or i <= last_measured]
    n = (max(has) + 1) if has else len(hours)
    cut = lambda v: v[:n]
    return {"hours": hours[:n], "last_measured": last_measured,
            "gen": {a: {k: cut(v) for k, v in g.items()} for a, g in gen.items()},
            "ex": {c: cut(v) for c, v in ex.items()}, "auc": {c: cut(v) for c, v in auc.items()},
            "fc": {c: cut(v) for c, v in fcs.items()}, "fc_kind": cut(kind),
            "price": {z: cut(v) for z, v in price.items()},
            "dk1_auc": cut(dk1_sum(auc)), "dk1_fc": cut(dk1_sum(fcs)),
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
    page = page.replace("__GEO__", Path("assets/countries.json").read_text(encoding="utf-8"))
    Path("site/index.html").write_text(page, encoding="utf-8")
    tabs = {"Live record": record_tab(live, actual, "Live record", "No live forecast saved yet.",
                                      "Saved before the noon auction and never changed. Only days with all 24 hours on every cable."),
            "Backfilled": record_tab(backfill, actual, "Backfilled days", "No backfilled days.",
                                     "Made afterwards, but only from what was published before each auction, and fit only on earlier "
                                     "days, exactly as the live run would have. Kept apart from the live record."),
            "Tomorrow": tomorrow_tab(live if not live.empty else backfill),
            "Backtest": backtest_tab(), "Method": method_tab()}
    Path("site/record.html").write_text(render(tabs), encoding="utf-8")
    print("wrote site/index.html and site/record.html,", len(data["hours"]), "hours, last measured", data["last_measured"])


if __name__ == "__main__":
    main()
