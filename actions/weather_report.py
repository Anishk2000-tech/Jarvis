"""
weather_report — the actual weather, spoken, not just a search page.

Uses Open-Meteo (free, no API key): the city is geocoded, then current
conditions and a short forecast are fetched and returned as facts the assistant
can say. With no city given, the city stored in memory is used. If the service
cannot be reached, a weather search opens in the browser as before.
"""
import webbrowser
from urllib.parse import quote_plus

_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
    81: "showers", 82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def _remembered_city() -> str:
    try:
        from memory.memory_manager import load_memory
        ident = load_memory().get("identity", {})
        for key in ("city", "location", "home_city", "hometown"):
            e = ident.get(key)
            v = (e.get("value") if isinstance(e, dict) else e) or ""
            if str(v).strip():
                return str(v).strip()
    except Exception:
        pass
    return ""


def _fetch(city: str, when: str) -> str:
    import requests
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "en", "format": "json"}, timeout=10)
    g.raise_for_status()
    res = (g.json().get("results") or [])
    if not res:
        return f"I could not find a place called {city}."
    place = res[0]
    label = ", ".join(x for x in (place.get("name"), place.get("admin1"), place.get("country")) if x)
    f = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "forecast_days": 3,
    })
    f.raise_for_status()
    data = f.json()
    cur, day = data.get("current", {}), data.get("daily", {})
    lines = [f"Weather for {label}:"]
    if cur:
        lines.append(
            f"Now {cur.get('temperature_2m')}°C (feels like {cur.get('apparent_temperature')}°C), "
            f"{_CODES.get(cur.get('weather_code'), 'unknown conditions')}, humidity "
            f"{cur.get('relative_humidity_2m')}%, wind {cur.get('wind_speed_10m')} km/h"
            + (f", {cur.get('precipitation')} mm precipitation" if cur.get("precipitation") else "") + ".")
    names = ["Today", "Tomorrow", "Day after tomorrow"]
    for i in range(min(3, len(day.get("time", [])))):
        lines.append(
            f"{names[i]}: {_CODES.get(day['weather_code'][i], '')}, {day['temperature_2m_min'][i]}–"
            f"{day['temperature_2m_max'][i]}°C, rain chance {day['precipitation_probability_max'][i]}%"
            + (f", sunrise {day['sunrise'][i][-5:]}, sunset {day['sunset'][i][-5:]}" if i == 0 else "") + ".")
    w = (when or "").lower()
    if "tomorrow" in w and len(lines) > 3:
        lines = [lines[0], lines[3], lines[1]]
    return "\n".join(lines)


def weather_action(parameters: dict, player=None, session_memory=None) -> str:
    city = str((parameters or {}).get("city") or "").strip() or _remembered_city()
    when = str((parameters or {}).get("time") or "today").strip()
    if not city:
        return ("Which city? I don't have the user's city in memory yet — ask them, and save it with "
                "save_memory (identity / city).")
    try:
        text = _fetch(city, when)
        _log(text.splitlines()[0], player)
        return text
    except Exception as e:
        url = f"https://www.google.com/search?q={quote_plus(f'weather in {city} {when}')}"
        try:
            webbrowser.open(url)
            return f"The weather service did not answer ({type(e).__name__}); I opened a weather search for {city}."
        except Exception:
            return f"The weather service did not answer: {e}"


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"SYS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "weather_report",
    "description": ("Current weather and a 3-day forecast for a city (temperature, conditions, rain chance, "
                    "wind, sunrise/sunset). With no city, uses the user's city from memory."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {"type": "STRING", "description": "City name (optional if known from memory)"},
            "time": {"type": "STRING", "description": "today | tomorrow"},
        },
        "required": [],
    },
    "handler": weather_action,
}
