# northern europe from the rebase grid api (grid.rebase.energy): generation by fuel, load and day-ahead price per price
# zone, and the measured flow on every border between them. hourly, danish time.
# the key is read from REBASE_API_KEY (a github secret); without it the api still answers, only slower

import os
import time

import pandas as pd
import requests

API = "https://grid.rebase.energy/api/v1"
ZONES = {
    "DK-DK1": ("DK1", "West Denmark", [9.2, 56.2]), "DK-DK2": ("DK2", "East Denmark", [11.9, 55.45]),
    "NO-NO1": ("NO1", "Oslo", [10.8, 60.4]), "NO-NO2": ("NO2", "Southwest Norway", [7.6, 58.9]),
    "NO-NO3": ("NO3", "Central Norway", [10.6, 63.4]), "NO-NO4": ("NO4", "North Norway", [17.5, 68.6]),
    "NO-NO5": ("NO5", "West Norway", [6.3, 60.9]), "SE-SE1": ("SE1", "Luleå", [20.6, 66.9]),
    "SE-SE2": ("SE2", "Sundsvall", [16.4, 63.5]), "SE-SE3": ("SE3", "Stockholm", [15.2, 59.4]),
    "SE-SE4": ("SE4", "Malmö", [13.9, 56.3]), "FI": ("FI", "Finland", [25.8, 62.6]),
    "DE-LU": ("DE", "Germany", [10.3, 51.3]), "NL": ("NL", "Netherlands", [5.5, 52.3]),
    "PL": ("PL", "Poland", [19.3, 52.1]), "EE": ("EE", "Estonia", [25.6, 58.7]),
    "LV": ("LV", "Latvia", [25.0, 56.9]), "LT": ("LT", "Lithuania", [23.9, 55.3]),
    "GB": ("GB", "Britain", [-1.8, 53.3]),
}
FUELS = ["fossil", "nuclear", "solar", "hydro", "bio", "wind", "other"]
DK_CABLES = {"DK1-DE": "border:DE-LU~DK-DK1", "DK1-NL": "border:DK-DK1~NL", "DK1-GB": "border:DK-DK1~GB",
             "DK1-NO2": "border:DK-DK1~NO-NO2", "DK1-SE3": "border:DK-DK1~SE-SE3", "DK1-DK2": "border:DK-DK1~DK-DK2"}


def fuel(kind):
    k = kind.lower()
    if "nuclear" in k:
        return "nuclear"
    if "solar" in k:
        return "solar"
    if "wind" in k:
        return "wind"
    if "hydro" in k:
        return "hydro"
    if any(w in k for w in ("biomass", "waste", "renewable", "geothermal", "marine", "bio")):
        return "bio"
    if any(w in k for w in ("fossil", "coal", "gas", "oil", "peat", "lignite")):
        return "fossil"
    return "other"


class Grid:
    def __init__(self):
        self.s = requests.Session()
        key = os.environ.get("REBASE_API_KEY")
        if key:
            self.s.headers["X-API-Key"] = key
        self.keyed = bool(key)

    def call(self, method, path, **kw):
        for attempt in range(6):
            r = self.s.request(method, API + path, timeout=120, **kw)
            if r.status_code in (429, 503):
                time.sleep(float(r.headers.get("Retry-After", 15)) + 1)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"{path}: still rate limited")

    def values(self, series, start, end):
        """many series over one window; one dataframe of (entity, name, valid_time, value)"""
        out, step = [], 2000 if self.keyed else 5
        for i in range(0, len(series), step):
            body = {"series": series[i:i + step], "start": start, "end": end}
            while True:
                j = self.call("POST", "/timeseries/values", json=body)
                for b in j["series"]:
                    for p in b.get("points") or []:
                        out.append((b["entity"], b["name"], p["valid_time"], p["value"]))
                if not j.get("next"):
                    break
                body["cursor"] = j["next"]
        return pd.DataFrame(out, columns=["entity", "name", "valid_time", "value"])


def hourly(df, idx):
    """values to danish hours, averaged; returns {(entity, name): [value per hour]}"""
    if df.empty:
        return {}
    t = pd.to_datetime(df["valid_time"], utc=True).dt.tz_convert("Europe/Copenhagen").dt.strftime("%Y-%m-%d %H")
    g = df.assign(key=t, value=pd.to_numeric(df["value"], errors="coerce")).groupby(["entity", "name", "key"])["value"].mean()
    out = {}
    for (e, n, k), v in g.items():
        if k in idx and pd.notna(v):
            out.setdefault((e, n), [None] * len(idx))[idx[k]] = float(v)
    return out


def region(hours):
    """everything the map needs for the region, on the given danish hours ("YYYY-MM-DD HH")"""
    grid = Grid()
    idx = {h: i for i, h in enumerate(hours)}
    t0 = pd.Timestamp(hours[0]).tz_localize("Europe/Copenhagen").tz_convert("UTC")
    t1 = pd.Timestamp(hours[-1]).tz_localize("Europe/Copenhagen").tz_convert("UTC") + pd.Timedelta(minutes=59)
    start, end = t0.strftime("%Y-%m-%dT%H:%M:%SZ"), t1.strftime("%Y-%m-%dT%H:%M:%SZ")

    series, borders, gen_names = [], {}, {}
    for z in ZONES:
        e = grid.call("GET", f"/entities/{z}")
        names = grid.call("GET", f"/entities/{z}/timeseries")["timeseries"]
        prov = "bmrs" if z == "GB" else "entsoe"
        gen = [t["name"] for t in names if t["provider"] == prov
               and t["name"].startswith("production.realised_output.actual_generation_per_type.")]
        gen_names[z] = gen
        series += [{"entity": z, "name": n, "provider": prov} for n in gen]
        for n in ("consumption.realised_load.total_load", "price.day_ahead.day_ahead_auction_price"):
            if any(t["name"] == n and t["provider"] == "entsoe" for t in names):
                series.append({"entity": z, "name": n, "provider": "entsoe"})
        for r in e.get("relations", []):
            a, b = (r.get("between") or [None, None])[:2]
            if r.get("kind") == "border" and a in ZONES and b in ZONES and r["id"] not in borders:
                first = r["positive"].split(" → ")[0]
                borders[r["id"]] = (first, b if first == a else a)
    series += [{"entity": bid, "name": "exchange.physical_flow.physical_flow", "provider": "entsoe"} for bid in borders]
    print(f"rebase: {len(series)} series, {len(borders)} borders")

    h = hourly(grid.values(series, start, end), idx)
    blank = lambda: [None] * len(hours)
    gen, load, price = {}, {}, {}
    for z, (short, _, _) in ZONES.items():
        g = {f: blank() for f in FUELS}
        for n in gen_names[z]:
            v = h.get((z, n))
            if not v or "consumption" in n:
                continue
            f = fuel(n.split(".")[-1])
            for i, x in enumerate(v):
                if x is not None:
                    g[f][i] = (g[f][i] or 0) + max(x, 0)
        gen[short] = {f: [None if x is None else round(x) for x in v] for f, v in g.items()}
        load[short] = [None if x is None else round(x) for x in h.get((z, "consumption.realised_load.total_load"), blank())]
        price[short] = [None if x is None else round(x, 1) for x in h.get((z, "price.day_ahead.day_ahead_auction_price"), blank())]
    flows = [{"id": bid, "a": ZONES[a][0], "b": ZONES[b][0],
              "v": [None if x is None else round(x) for x in h.get((bid, "exchange.physical_flow.physical_flow"), blank())]}
             for bid, (a, b) in borders.items()]

    return {"zones": [{"id": s, "name": n, "at": at} for s, n, at in ZONES.values()],
            "gen": gen, "load": load, "price": price, "flows": flows}
