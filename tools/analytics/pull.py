#!/usr/bin/env python3
"""Pull the last N hours of real nfsu.cc analytics into one data file the deck renders.
Sources (all read live, nothing typed by hand):
  1. Cloudflare Web Analytics (RUM beacon, site nfsu.cc): visits, page views, referers, countries, devices, pages.
  2. Cloudflare zone traffic (httpRequests1hGroups): requests, bytes served, cache share.
  3. r2:nfsu-crash: funnel beacons (rn-funnel-1: did the game reach the race?) and crash reports (rn-crash-1).
Returning visitors: no persistent id exists (RN_SID is per page load, web/boot.js). Proxy = funnel `warm`
(the WASM came from the browser HTTP cache, transferSize 0, web/boot.js:222): that browser downloaded the game before.
Usage: set -a; . ~/.config/cloudflare/credentials.env; set +a; python3 tools/analytics/pull.py [hours=24]
Writes web/plan/analytics/data.js (gitignored: visitor data) and copies deck.html to web/plan/analytics/index.html."""
import collections, datetime as dt, json, os, shutil, statistics, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "web/plan/analytics")
sys.path.insert(0, os.path.join(ROOT, "tools/crash"))
from dump_audit import klass, browser  # same crash taxonomy as AUDIT.md

ZONE = "3fe47e1f0e7d489583c258cc6547e82d"  # nfsu.cc
TOKEN, ACCT = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
HOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 24
NOW = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
SINCE = NOW - dt.timedelta(hours=HOURS)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def cf(path=None, query=None, variables=None):
    url = "https://api.cloudflare.com/client/v4/" + (path or "graphql")
    data = json.dumps({"query": query, "variables": variables}).encode() if query else None
    req = urllib.request.Request(url, data=data, headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    j = json.load(urllib.request.urlopen(req, timeout=60))
    if j.get("errors"):
        raise SystemExit(f"cloudflare: {j['errors']}")
    return j["result"] if path else j["data"]


# 1. Web Analytics (RUM)
site = next(s["site_tag"] for s in cf(f"accounts/{ACCT}/rum/site_info/list") if s.get("ruleset", {}).get("zone_name") == "nfsu.cc")


def rum(dim, limit=25):
    q = """query($a:String!,$t:String!,$s:Time!,$u:Time!){viewer{accounts(filter:{accountTag:$a}){
      g:rumPageloadEventsAdaptiveGroups(limit:%d,filter:{siteTag:$t,datetime_geq:$s,datetime_lt:$u},orderBy:[sum_visits_DESC,count_DESC]){
        count sum{visits} dimensions{%s}}}}}""" % (limit, dim)
    g = cf(query=q, variables={"a": ACCT, "t": site, "s": iso(SINCE), "u": iso(NOW)})["viewer"]["accounts"][0]["g"]
    return [{"k": r["dimensions"][dim] or "", "visits": r["sum"]["visits"], "views": r["count"]} for r in g]


web = {d: rum(d) for d in ("refererHost", "countryName", "deviceType", "userAgentBrowser", "userAgentOS", "requestPath")}
web["hour"] = sorted(rum("datetimeHour", 100), key=lambda r: r["k"])

# 2. Zone traffic, hourly
q = """query($z:String!,$s:Time!,$u:Time!){viewer{zones(filter:{zoneTag:$z}){
  h:httpRequests1hGroups(limit:200,filter:{datetime_geq:$s,datetime_lt:$u},orderBy:[datetime_ASC]){
    dimensions{datetime} sum{requests cachedRequests bytes cachedBytes pageViews threats}}}}}"""
zh = cf(query=q, variables={"z": ZONE, "s": iso(SINCE), "u": iso(NOW)})["viewer"]["zones"][0]["h"]
zone = {"hour": [{"k": r["dimensions"]["datetime"], **r["sum"]} for r in zh]}
zone["total"] = {k: sum(r[k] for r in zone["hour"]) for k in ("requests", "cachedRequests", "bytes", "cachedBytes", "pageViews", "threats")}

# 3. R2 telemetry: copy the UTC days the window touches, keep keys inside the window (key = YYYY-MM-DD/HHMMSS-id.json)
tmp = tempfile.mkdtemp(prefix="nfsu-analytics-")
days = sorted({(SINCE + dt.timedelta(hours=h)).strftime("%Y-%m-%d") for h in range(HOURS + 1)})


def r2(prefix):
    rows = []
    for d in days:
        dst = os.path.join(tmp, prefix.replace("/", "_") + d)
        subprocess.run(["rclone", "copy", f"r2:nfsu-crash/{prefix}{d}/", dst, "--transfers", "32", "-q"], check=True)
        for f in os.listdir(dst) if os.path.isdir(dst) else []:
            t = dt.datetime.strptime(d + f[:6], "%Y-%m-%d%H%M%S").replace(tzinfo=dt.timezone.utc)
            if SINCE <= t < NOW:
                for line in open(os.path.join(dst, f)):
                    if line.strip():
                        r = json.loads(line)
                        r["at_utc"] = iso(t)
                        rows.append(r)
    return rows


funnel, crash = r2("funnel/"), r2("")
shutil.rmtree(tmp)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0


def group(rows, key):
    c = collections.defaultdict(lambda: {"run": 0, "stop": 0, "load": [], "warm": 0})
    for r in rows:
        e = c[key(r)]
        e[r["ev"]] += 1
        e["warm"] += bool(r.get("warm"))
        if r["ev"] == "run":
            e["load"].append(r.get("load_ms", 0))
    return sorted(({"k": k, "run": e["run"], "stop": e["stop"], "warm": e["warm"], "p50": pct(e["load"], .5), "p90": pct(e["load"], .9)}
                   for k, e in c.items()), key=lambda x: -(x["run"] + x["stop"]))


runs = [r for r in funnel if r["ev"] == "run"]
# live build = the build of the newest beacon; deploy_at = its first beacon in the window
live = max(funnel, key=lambda r: r["at_utc"])["v"] if funnel else ""
deploy_at = min((r["at_utc"] for r in funnel if r["v"] == live), default="")
crash_sids = {r.get("sid") for r in crash if r.get("sid")}
tel = {
    "sessions": len(funnel), "runs": len(runs), "stops": len(funnel) - len(runs),
    "warm": sum(bool(r.get("warm")) for r in funnel), "warm_run": sum(bool(r.get("warm")) for r in runs),
    "load": {"p50": pct([r["load_ms"] for r in runs], .5), "p90": pct([r["load_ms"] for r in runs], .9),
             "cold_wasm_p50": pct([r["wasm_ms"] for r in runs if not r.get("warm") and r.get("wasm_ms")], .5),
             "warm_wasm_p50": pct([r["wasm_ms"] for r in runs if r.get("warm") and r.get("wasm_ms")], .5)},
    "os": group(funnel, lambda r: r.get("os") or "?"),
    "country": group(funnel, lambda r: r.get("country") or "?")[:20],
    "tier": group(funnel, lambda r: r.get("tier") or "default"),
    "framed": sum(bool(r.get("framed")) for r in funnel),
    "hour": group(funnel, lambda r: r["at_utc"][:13]),
    "stop_reason": collections.Counter((r.get("reason") or "?")[:70] for r in funnel if r["ev"] == "stop").most_common(8),
    "builds": collections.Counter(r.get("v", "") for r in funnel).most_common(5),
    "live_build": live, "deploy_at": deploy_at,
    "by_build": group(funnel, lambda r: r.get("v") or "?"),
    "crash_after_run": sum(1 for r in runs if r.get("sid") in crash_sids),
}
crash_rows = [{"cls": klass(r), "browser": browser(r.get("ua", "")), "v": r.get("v", ""), "country": r.get("country", ""),
               "mem": r.get("mem", ""), "at": r.get("at", ""), "stop": r.get("stop", "")[:140], "at_utc": r["at_utc"]} for r in crash]
cr = {
    "total": len(crash), "live": sum(r["v"] == live for r in crash_rows),
    "cls": [{"k": k, "n": n, "live": sum(r["cls"] == k and r["v"] == live for r in crash_rows)}
            for k, n in collections.Counter(r["cls"] for r in crash_rows).most_common()],
    "browser": collections.Counter(r["browser"] for r in crash_rows).most_common(8),
    "by_build": collections.Counter(r["v"] for r in crash_rows).most_common(),
    "hour": collections.Counter(r["at_utc"][:13] for r in crash_rows).most_common(),
    "live_top": collections.Counter((r["cls"], r["stop"][:90]) for r in crash_rows if r["v"] == live).most_common(6),
    "latest": sorted((r for r in crash_rows if r["v"] == live), key=lambda r: r["at_utc"])[-6:],
}

data = {"generated": iso(dt.datetime.now(dt.timezone.utc)), "since": iso(SINCE), "until": iso(NOW), "hours": HOURS,
        "web": web, "zone": zone, "tel": tel, "crash": cr,
        "sources": {"web": f"Cloudflare Web Analytics rumPageloadEventsAdaptiveGroups site {site[:8]}",
                    "zone": "Cloudflare GraphQL httpRequests1hGroups zone nfsu.cc",
                    "tel": "r2:nfsu-crash/funnel/<day>/ (rn-funnel-1, tools/crash/worker.js)",
                    "crash": "r2:nfsu-crash/<day>/ (rn-crash-1), classes from tools/crash/dump_audit.py klass()"}}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "data.js"), "w") as f:
    f.write("window.NFSU_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
shutil.copy(os.path.join(HERE, "deck.html"), os.path.join(OUT, "index.html")) if os.path.exists(os.path.join(HERE, "deck.html")) else None
print(f"{iso(SINCE)}..{iso(NOW)} | visits {sum(r['visits'] for r in web['refererHost'])} views {sum(r['views'] for r in web['refererHost'])}"
      f" | requests {zone['total']['requests']} | funnel {tel['sessions']} run {tel['runs']} warm {tel['warm']} | crash {cr['total']} (live {cr['live']}, build {live})")
