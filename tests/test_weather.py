from actions import weather_report as w


class R:
    def __init__(self, data):
        self._d = data
    def raise_for_status(self):
        pass
    def json(self):
        return self._d


def test_weather_summary(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return R({"results": [{"name": "Pune", "admin1": "Maharashtra", "country": "India",
                                   "latitude": 18.5, "longitude": 73.8}]})
        return R({"current": {"temperature_2m": 27.1, "apparent_temperature": 29.0, "relative_humidity_2m": 70,
                              "precipitation": 0, "weather_code": 2, "wind_speed_10m": 11},
                  "daily": {"time": ["d1", "d2", "d3"], "weather_code": [61, 3, 0],
                            "temperature_2m_max": [30, 29, 31], "temperature_2m_min": [22, 21, 23],
                            "precipitation_probability_max": [80, 20, 5],
                            "sunrise": ["2026-09-27T06:20"] * 3, "sunset": ["2026-09-27T18:25"] * 3}})
    import requests
    monkeypatch.setattr(requests, "get", fake_get)
    out = w.weather_action({"city": "pune"})
    assert "Pune, Maharashtra, India" in out and "27.1°C" in out and "partly cloudy" in out
    assert "Today: light rain, 22–30°C, rain chance 80%" in out
    assert "sunrise 06:20" in out
    tom = w.weather_action({"city": "pune", "time": "tomorrow"})
    assert tom.splitlines()[1].startswith("Tomorrow")
