"""
cities_config.py — Swiss cities configuration for CityPulse pipeline.
"""

from typing import Dict, Any

SWISS_CITIES: Dict[str, Dict[str, Any]] = {
    "Zurich": {
        "lat": 47.3769,
        "lon": 8.5417,
    },
    "Geneva": {
        "lat": 46.2044,
        "lon": 6.1432,
    },
    "Bern": {
        "lat": 46.9481,
        "lon": 7.4474,
    },
    "Lucerne": {
        "lat": 47.0502,
        "lon": 8.3093,
    },
    "Basel": {
        "lat": 47.5596,
        "lon": 7.5886,
    },
    "Interlaken": {
        "lat": 46.6863,
        "lon": 7.8632,
    },
    "Lausanne": {
        "lat": 46.5197,
        "lon": 6.6323,
    },
    "Zermatt": {
        "lat": 46.0207,
        "lon": 7.7491,
    },
}

CITY_NAMES = list(SWISS_CITIES.keys())
