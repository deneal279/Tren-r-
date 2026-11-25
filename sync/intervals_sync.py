#!/usr/bin/env python3
"""Stáhne aktivity a wellness z intervals.icu a připraví měsíční dokumenty pro Triatlon Kokpit.

Použití:  python3 -I sync/intervals_sync.py <athlete_id> <out_dir> [pocet_mesicu]

API klíč se nikde neuvádí: v Claude Code cloud prostředí ho do požadavků
na intervals.icu vkládá síťová proxy. Pro jiné prostředí nastav proměnnou
INTERVALS_API_KEY.

Výstup: <out_dir>/activities-YYYY-MM.json a <out_dir>/wellness-YYYY-MM.json,
každý ve tvaru {"month": "YYYY-MM", "items": [...]}. Zapisuje se do databáze
artefaktu do kolekcí "activities" a "wellness" s doc_id = YYYY-MM.
Stahuje celé měsíce, takže dokument měsíce lze vždy celý přepsat (set).
"""
import base64, collections, datetime, json, os, sys, urllib.request

SPORT = {"Swim": "swim", "OpenWaterSwim": "swim", "Ride": "bike", "VirtualRide": "bike",
         "MountainBikeRide": "bike", "GravelRide": "bike", "TrackRide": "bike", "Cyclocross": "bike",
         "Run": "run", "VirtualRun": "run", "TrailRun": "run", "WeightTraining": "strength"}


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "triatlon-kokpit-sync/1.0"})
    key = os.environ.get("INTERVALS_API_KEY")
    if key:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"API_KEY:{key}".encode()).decode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def convert_activity(x):
    sport = SPORT.get(x.get("type"), "other")
    secs = x.get("moving_time") or x.get("elapsed_time") or 0
    if not secs:
        return None
    dur = round(secs / 60)
    dist = round((x.get("distance") or 0) / 1000, 2 if sport == "swim" else 1)
    z = x.get("icu_hr_zone_times")
    if z:
        zz = [s / 60 for s in z[:5]] + [0] * max(0, 5 - len(z))
        zz[4] += sum(z[5:]) / 60
        z = [round(v) for v in zz]
    tss = x.get("icu_training_load")
    return {"id": "icu-" + str(x["id"]), "date": x["start_date_local"][:10], "sport": sport,
            "name": (x.get("name") or x.get("type") or "Trénink")[:80], "type": x.get("type"),
            "dur": dur, "dist": dist, "tss": round(tss if tss is not None else dur * 0.5),
            "hr": x.get("average_heartrate"), "elev": round(x.get("total_elevation_gain") or 0), "z": z}


def convert_wellness(w):
    e = {"date": w["id"]}
    if w.get("hrv"): e["hrv"] = round(w["hrv"])
    if w.get("restingHR"): e["rhr"] = w["restingHR"]
    if w.get("sleepSecs"): e["sleep"] = round(w["sleepSecs"] / 3600, 1)
    if w.get("sleepScore"): e["sleepScore"] = round(w["sleepScore"])
    if w.get("weight"): e["weight"] = w["weight"]
    if w.get("steps"): e["steps"] = w["steps"]
    if w.get("stress"): e["stress"] = round(w["stress"])
    return e if len(e) > 1 else None


def main():
    athlete, out = sys.argv[1], sys.argv[2]
    months = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    today = datetime.date.today()
    first = today.replace(day=1)
    for _ in range(months - 1):
        first = (first - datetime.timedelta(days=1)).replace(day=1)
    base = f"https://intervals.icu/api/v1/athlete/{athlete}"
    q = f"?oldest={first.isoformat()}&newest={today.isoformat()}"
    acts = get(base + "/activities" + q)
    well = get(base + "/wellness" + q)
    groups = {"activities": collections.defaultdict(list), "wellness": collections.defaultdict(list)}
    for x in acts:
        a = convert_activity(x)
        if a: groups["activities"][a["date"][:7]].append(a)
    for w in well:
        e = convert_wellness(w)
        if e: groups["wellness"][e["date"][:7]].append(e)
    os.makedirs(out, exist_ok=True)
    m = first
    written = []
    while m <= today:  # každý měsíc v rozsahu, i prázdný, aby se smazané aktivity propsaly
        k = m.strftime("%Y-%m")
        for name, g in groups.items():
            path = os.path.join(out, f"{name}-{k}.json")
            with open(path, "w") as f:
                json.dump({"month": k, "items": sorted(g.get(k, []), key=lambda i: i["date"])}, f, ensure_ascii=False)
            written.append(f"{name}/{k}: {len(g.get(k, []))}")
        m = (m + datetime.timedelta(days=32)).replace(day=1)
    print("\n".join(written))


if __name__ == "__main__":
    main()
