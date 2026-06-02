#!/usr/bin/env python3
"""
World Cup 2026 ticket-price tracker.

Reads config.json, queries each enabled source for the cheapest current listing
for every match, then appends to docs/data/history.csv and rewrites
docs/data/latest.json (which the dashboard reads).

Designed to run on GitHub Actions on a daily schedule. It is deliberately
fault-tolerant: if a source is down or blocked, that data point is recorded as
empty and the run still succeeds, so the history never gets a gap that breaks
the build.

Optional secrets (set as GitHub Actions repository secrets):
  SEATGEEK_CLIENT_ID   - free SeatGeek API client id (enables SeatGeek prices)
  STUBHUB_API_TOKEN    - StubHub API bearer token (enables StubHub prices)

No secret => that source is skipped gracefully (recorded as no data).
"""

import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
DATA_DIR = os.path.join(ROOT, "docs", "data")
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")

CSV_FIELDS = [
    "timestamp", "venue", "match_id", "match_label", "match_date",
    "round", "source", "min_price", "listing_count", "currency", "url",
]

USER_AGENT = "Mozilla/5.0 (compatible; WC26TicketTracker/1.0)"
TIMEOUT = 25


def log(*args):
    print(*args, file=sys.stderr)


def http_get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# Source adapters. Each returns a dict or None.
#   { "min_price": float|None, "listing_count": int|None, "url": str }
# Never raise: catch everything and return None so one bad source can't break
# the whole run.
# --------------------------------------------------------------------------- #

def source_seatgeek(match, venue):
    """SeatGeek public API. Needs SEATGEEK_CLIENT_ID. Matches by date + venue."""
    client_id = os.environ.get("SEATGEEK_CLIENT_ID")
    fallback_url = "https://seatgeek.com/search?q=" + urllib.parse.quote(match["query"])
    if not client_id:
        return {"min_price": None, "listing_count": None, "url": fallback_url, "note": "no SEATGEEK_CLIENT_ID"}
    try:
        date = match["date"]
        nxt = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
        params = {
            "client_id": client_id,
            "q": match["query"],
            "datetime_local.gte": date + "T00:00:00",
            "datetime_local.lte": nxt + "T00:00:00",
            "per_page": 50,
        }
        url = "https://api.seatgeek.com/2/events?" + urllib.parse.urlencode(params)
        data = http_get_json(url)
        events = data.get("events", [])
        # Prefer an event whose venue name matches; otherwise take the first.
        chosen = None
        vname = venue["name"].lower()
        for ev in events:
            ev_venue = (ev.get("venue", {}) or {}).get("name", "").lower()
            if vname.split()[0] in ev_venue:
                chosen = ev
                break
        if chosen is None and events:
            chosen = events[0]
        if not chosen:
            return {"min_price": None, "listing_count": None, "url": fallback_url}
        stats = chosen.get("stats", {}) or {}
        return {
            "min_price": stats.get("lowest_price"),
            "listing_count": stats.get("listing_count"),
            "url": chosen.get("url") or fallback_url,
        }
    except Exception as e:  # noqa: BLE001
        log(f"  seatgeek error for {match['id']}: {e}")
        return {"min_price": None, "listing_count": None, "url": fallback_url}


def source_stubhub(match, venue):
    """StubHub. Needs STUBHUB_API_TOKEN (catalog/inventory API). Best-effort."""
    token = os.environ.get("STUBHUB_API_TOKEN")
    fallback_url = "https://www.stubhub.com/find/s/?q=" + urllib.parse.quote(match["query"])
    if not token:
        return {"min_price": None, "listing_count": None, "url": fallback_url, "note": "no STUBHUB_API_TOKEN"}
    try:
        params = {"q": match["query"], "rows": 25}
        url = "https://api.stubhub.com/sellers/search/events/v3?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Authorization": f"Bearer {token}"})
        events = data.get("events", []) or data.get("Events", [])
        date = match["date"]
        chosen = None
        for ev in events:
            ev_date = (ev.get("eventDateLocal") or ev.get("EventDateLocal") or "")[:10]
            if ev_date == date:
                chosen = ev
                break
        if chosen is None and events:
            chosen = events[0]
        if not chosen:
            return {"min_price": None, "listing_count": None, "url": fallback_url}
        min_price = chosen.get("minTicketPrice") or chosen.get("MinTicketPrice")
        ticket_count = chosen.get("totalTickets") or chosen.get("TotalTickets")
        ev_url = chosen.get("webURI") or chosen.get("url") or fallback_url
        return {"min_price": min_price, "listing_count": ticket_count, "url": ev_url}
    except Exception as e:  # noqa: BLE001
        log(f"  stubhub error for {match['id']}: {e}")
        return {"min_price": None, "listing_count": None, "url": fallback_url}


def source_fifa(match, venue):
    """FIFA official resale has no public price API. Record a direct link only."""
    return {
        "min_price": None,
        "listing_count": None,
        "url": venue.get("fifa_resale_url", ""),
        "note": "manual: FIFA resale has no public price API",
    }


SOURCES = {
    "seatgeek": source_seatgeek,
    "stubhub": source_stubhub,
    "fifa": source_fifa,
}


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    currency = cfg.get("currency", "USD")
    enabled = [s for s, v in cfg.get("sources", {}).items() if v.get("enabled")]
    os.makedirs(DATA_DIR, exist_ok=True)

    timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    latest = {"generated_at": timestamp, "currency": currency, "matches": []}

    for m in cfg["matches"]:
        venue = cfg["venues"][m["venue"]]
        match_entry = {
            "id": m["id"], "venue": m["venue"], "venue_name": venue["name"],
            "date": m["date"], "round": m["round"], "label": m["label"],
            "sources": {},
        }
        log(f"{m['id']} {venue['name']} {m['date']} {m['label']}")
        for src in enabled:
            adapter = SOURCES.get(src)
            if not adapter:
                continue
            result = adapter(m, venue) or {}
            min_price = result.get("min_price")
            listing_count = result.get("listing_count")
            url = result.get("url", "")
            match_entry["sources"][src] = {
                "min_price": min_price,
                "listing_count": listing_count,
                "url": url,
                "note": result.get("note", ""),
            }
            rows.append({
                "timestamp": timestamp,
                "venue": venue["name"],
                "match_id": m["id"],
                "match_label": m["label"],
                "match_date": m["date"],
                "round": m["round"],
                "source": src,
                "min_price": "" if min_price is None else min_price,
                "listing_count": "" if listing_count is None else listing_count,
                "currency": currency,
                "url": url,
            })
            price_str = "n/a" if min_price is None else f"{currency} {min_price}"
            log(f"    {src:9s} {price_str}")
        latest["matches"].append(match_entry)

    # Append to history (create with header if missing).
    new_file = not os.path.exists(HISTORY_CSV)
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2)

    log(f"\nWrote {len(rows)} rows to {HISTORY_CSV}")
    log(f"Updated {LATEST_JSON}")


if __name__ == "__main__":
    main()
