"""Kasi Wiki - ATM / bank collector (OpenStreetMap via Overpass).

Reads  kasi-data.json   (from the same folder)
Writes kasi-atms.json   (loaded by Main.html's "ATMs" button)

Run:  pip install requests && python fetch_atms.py
Takes a few minutes: it waits between requests to respect the public server.
"""
import json
import math
import time

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "KasiWiki/1.1 (township ATM map; contact: you@example.com)"}
OPERATORS = ["Capitec", "Absa", "FNB", "Standard Bank", "Nedbank", "TymeBank",
             "Independent / White-Label"]


def bbox_for(t):
    """[south, west, north, east] - a square around the township centre.
    Half-side = radius of a circle with the township's area, clamped to 1.5-6 km."""
    lat, lng = t["coordinates"]["lat"], t["coordinates"]["lng"]
    r_km = min(6.0, max(1.5, math.sqrt(t["area_km2"] / math.pi) * 1.3))
    dlat = r_km / 111.0
    dlng = r_km / (111.0 * math.cos(math.radians(lat)))
    return [round(lat - dlat, 5), round(lng - dlng, 5),
            round(lat + dlat, 5), round(lng + dlng, 5)]


def query(bbox):
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:40];
    (
      nwr["amenity"="atm"]({s},{w},{n},{e});
      nwr["amenity"="bank"]({s},{w},{n},{e});
    );
    out center tags;
    """
    for attempt in range(4):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.json().get("elements", [])
            print(f"   HTTP {r.status_code} from {url}, retrying...")
        except Exception as ex:  # network hiccup
            print(f"   {ex.__class__.__name__}: {ex}, retrying...")
        time.sleep(5 * (attempt + 1))
    return None  # failed - don't record as "zero ATMs"


def operator_of(tags):
    raw = (tags.get("operator") or tags.get("brand") or tags.get("name") or "").lower()
    if "capitec" in raw: return "Capitec"
    if "absa" in raw: return "Absa"
    if "fnb" in raw or "first national" in raw: return "FNB"
    if "standard bank" in raw or raw.startswith("standard"): return "Standard Bank"
    if "nedbank" in raw: return "Nedbank"
    if "tyme" in raw: return "TymeBank"
    return "Independent / White-Label"


def process(elements):
    pins, counts, seen = [], {o: 0 for o in OPERATORS}, set()
    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        is_bank = tags.get("amenity") == "bank"
        # a bank only counts here if OSM says it has an ATM
        if is_bank and tags.get("atm") != "yes":
            continue
        key = (el.get("type"), el.get("id"))
        if key in seen:
            continue
        seen.add(key)
        op = operator_of(tags)
        counts[op] += 1
        pins.append({
            "id": f"osm_{el.get('type', 'n')[0]}{el.get('id')}",
            "name": tags.get("name") or f"{op} {'branch' if is_bank else 'ATM'}",
            "operator": op,
            "type": "branch" if is_bank else "atm",
            "lat": round(lat, 6),
            "lng": round(lon, 6),
            "address": tags.get("addr:full") or tags.get("addr:street"),
            "opening_hours": tags.get("opening_hours"),  # None when unknown
        })
    return pins, counts


def main():
    with open("kasi-data.json", encoding="utf-8") as f:
        townships = json.load(f)["townships"]

    out = {}
    for i, t in enumerate(townships, 1):
        bb = bbox_for(t)
        print(f"[{i}/{len(townships)}] {t['name']} {bb}")
        els = query(bb)
        if els is None:
            print("   FAILED - skipped (re-run to retry)")
            continue
        pins, counts = process(els)
        out[t["name"]] = {"bbox": bb, "total": len(pins),
                          "operator_breakdown": counts, "pins": pins}
        print(f"   {len(pins)} ATMs/bank-ATMs")
        time.sleep(2)

    result = {
        "metadata": {
            "source": "OpenStreetMap contributors (ODbL) via Overpass API",
            "generated": time.strftime("%Y-%m-%d"),
            "note": "Coverage depends on OSM mapping; a low count can mean unmapped, not absent.",
        },
        "townships": out,
    }
    with open("kasi-atms.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"Done: {len(out)}/{len(townships)} townships -> kasi-atms.json")


if __name__ == "__main__":
    main()
