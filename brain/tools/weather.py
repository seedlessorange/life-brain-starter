"""The weather where she actually is, for the morning briefing.

Not decoration. Her August day has a shape — laptop until noon, then physical
work outdoors at Faverolles all afternoon — so rain at three o'clock is a
planning fact, not small talk. The morning plan can move the outdoor task to
the dry half of the day if something says which half is dry.

The place is the whole problem. She moves between four houses across the year
(Burgundy, Ibiza, Florida, campus in Paris) and weather for the wrong one is
worse than none, because it looks right. So the place is stored, it is named
every single time the weather is shown, and changing it is one command.

Open-Meteo: no key, no account, no terms to accept. One request an hour at
most, cached to brain/.weather.json.

    python3 brain/tools/weather.py                # the line, as shown
    python3 brain/tools/weather.py --json
    python3 brain/tools/weather.py --place "Ibiza, Spain"
    python3 brain/tools/weather.py --force        # ignore the cache
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
CACHE = os.path.join(BRAIN, ".weather.json")
CONFIG = os.path.join(BRAIN, "config.json")
UA = "life-brain/1.0 (personal use)"
FRESH_MIN = 60

# WMO codes, said the way a person would say them out loud.
CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}
WET = set(list(range(51, 68)) + list(range(80, 100)))


def _cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(cfg):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG)


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def set_place(name):
    """Resolve a place to coordinates once, and remember it.

    Storing the coordinates rather than re-resolving the name every morning
    keeps the daily path to a single request, and means a geocoder outage
    cannot take the weather down.
    """
    url = ("https://geocoding-api.open-meteo.com/v1/search?"
           + urllib.parse.urlencode({"name": name, "count": 1,
                                     "language": "en", "format": "json"}))
    res = _get(url).get("results") or []
    if not res:
        raise ValueError(f"no place found called {name!r}")
    r = res[0]
    label = ", ".join(x for x in (r.get("name"), r.get("admin1"),
                                  r.get("country")) if x)
    cfg = _cfg()
    cfg["weather"] = {"place": label, "lat": r["latitude"],
                      "lon": r["longitude"]}
    _save_cfg(cfg)
    try:
        os.remove(CACHE)               # the old place's weather is not hers
    except OSError:
        pass
    return cfg["weather"]


def place():
    return (_cfg().get("weather") or {})


def fetch(force=False):
    """Today and tomorrow, plus which half of today is wet."""
    p = place()
    if not p.get("lat"):
        return {}
    if not force:
        try:
            with open(CACHE, encoding="utf-8") as f:
                old = json.load(f)
            age = (datetime.now()
                   - datetime.fromisoformat(old["at"])).total_seconds() / 60
            if age < FRESH_MIN and old.get("place") == p.get("place"):
                return old
        except Exception:
            pass
    url = ("https://api.open-meteo.com/v1/forecast?"
           + urllib.parse.urlencode({
               "latitude": p["lat"], "longitude": p["lon"],
               "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,sunset,"
                         "wind_speed_10m_max"),
               "hourly": "precipitation_probability,weather_code",
               "timezone": "auto", "forecast_days": 2}))
    try:
        raw = _get(url)
    except Exception:
        # Offline is not an error worth shouting about: the briefing simply
        # goes without a weather line, exactly as it did before this existed.
        try:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    d = raw.get("daily") or {}
    hh = raw.get("hourly") or {}
    # Morning and afternoon told apart, because that is the decision her day
    # actually turns on — the laptop half and the outdoors half.
    times = hh.get("time") or []
    probs = hh.get("precipitation_probability") or []
    today = (d.get("time") or [""])[0]
    am = [pr for t, pr in zip(times, probs)
          if t.startswith(today) and 7 <= int(t[11:13]) < 13 and pr is not None]
    pm = [pr for t, pr in zip(times, probs)
          if t.startswith(today) and 13 <= int(t[11:13]) < 20 and pr is not None]
    out = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "place": p.get("place", ""),
        "today": {
            "date": today,
            "code": (d.get("weather_code") or [None])[0],
            "high": (d.get("temperature_2m_max") or [None])[0],
            "low": (d.get("temperature_2m_min") or [None])[0],
            "rain": (d.get("precipitation_probability_max") or [None])[0],
            "sunset": ((d.get("sunset") or [""])[0] or "")[11:16],
            "wind": (d.get("wind_speed_10m_max") or [None])[0],
            "am_rain": max(am) if am else None,
            "pm_rain": max(pm) if pm else None,
        },
        "tomorrow": {
            "code": (d.get("weather_code") or [None, None])[1],
            "high": (d.get("temperature_2m_max") or [None, None])[1],
            "low": (d.get("temperature_2m_min") or [None, None])[1],
            "rain": (d.get("precipitation_probability_max")
                     or [None, None])[1],
        },
    }
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    except OSError:
        pass
    return out


def words(w=None):
    """One line, and the place said out loud in it.

    The place is never implied. Weather for the house she left on Tuesday
    looks exactly like weather for the house she is in, and that is the one
    way this feature can quietly lie to her.
    """
    w = w or fetch()
    t = (w or {}).get("today") or {}
    if t.get("high") is None:
        return ""
    # A cached forecast that is not for today is not weather, it is a
    # souvenir. Offline for two days, this would otherwise go on cheerfully
    # describing Tuesday.
    if t.get("date") and t["date"] != datetime.now().date().isoformat():
        return ""
    sky = CODES.get(t.get("code"), "")
    # The town, not the full geocoder label: enough to notice it is the wrong
    # house, short enough to sit above the plan without becoming the headline.
    where = (w.get("place") or "").split(",")[0].strip()
    line = f"{where}: {sky}, {round(t['low'])}–{round(t['high'])}°"
    am, pm = t.get("am_rain"), t.get("pm_rain")
    # Which HALF is wet, not just whether the day is. An afternoon of hedges
    # and floors at Faverolles is a different question from a wet morning at
    # the laptop, and the answer decides which one moves.
    if am is not None and pm is not None:
        if pm >= 50 and am < 50:
            line += f" · wet afternoon ({round(pm)}%) — outdoor work to the morning"
        elif am >= 50 and pm < 50:
            line += f" · wet morning ({round(am)}%), afternoon clears"
        elif max(am, pm) >= 50:
            line += f" · rain most of the day ({round(max(am, pm))}%)"
        elif max(am, pm) >= 25:
            line += f" · a chance of rain ({round(max(am, pm))}%)"
    return line


def main():
    args = sys.argv[1:]
    if "--place" in args:
        try:
            p = set_place(args[args.index("--place") + 1])
        except (IndexError, ValueError) as e:
            print("Could not set the place:", e)
            return
        print("Weather is now for", p["place"])
        return
    if not place().get("lat"):
        print("No place set yet — run:  python3 brain/tools/weather.py "
              '--place "Vanvey, France"')
        return
    w = fetch(force="--force" in args)
    if "--json" in args:
        print(json.dumps(w, indent=1))
    else:
        print(words(w) or "No weather right now.")


if __name__ == "__main__":
    main()
