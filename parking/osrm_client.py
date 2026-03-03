
import time
import json
import ast
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests


class OSRMClient:
    def __init__(
        self,
        use_public_api: bool = True,
        local_url: str = None,
        profile: str = "walking",   
        rate_limit_s: float = 0.3,
    ):
        if use_public_api:
            self.base_url = "https://router.project-osrm.org"
            self.rate_limit = max(0.0, rate_limit_s)
        else:
            self.base_url = local_url or "http://localhost:5000"
            self.rate_limit = 0.0

        self.profile = profile
        self.last_request = 0.0
        self._cache: Dict[Tuple[float, float, float, float], Dict] = {}

    def load_cache(self, filepath: Path):
        filepath = Path(filepath)
        if not filepath.exists():
            return
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for k_str, v in raw.items():
            self._cache[ast.literal_eval(k_str)] = v
        print(f"✅ Cache OSRM chargé: {len(self._cache)} entrées")

    def save_cache(self, filepath: Path):
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        raw = {str(k): v for k, v in self._cache.items()}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        print(f"✅ Cache OSRM sauvegardé: {filepath}")

    def get_route(
        self,
        lon1: float, lat1: float,
        lon2: float, lat2: float,
        timeout: int = 10,
        retry: int = 3,
    ) -> Optional[Dict]:
        """
        Retourne {distance_m, duration_s, duration_min} ou None si erreur.
        """
        key = (round(lon1, 6), round(lat1, 6), round(lon2, 6), round(lat2, 6))
        if key in self._cache:
            return self._cache[key]

        url = f"{self.base_url}/route/v1/{self.profile}/{lon1},{lat1};{lon2},{lat2}"
        params = {"overview": "false", "steps": "false", "alternatives": "false"}

        for attempt in range(1, retry + 1):
            try:
                r = requests.get(url, params=params, timeout=timeout)
                self.last_request = time.time()
                r.raise_for_status()
                data = r.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    result = {
                        "distance_m": float(route["distance"]),
                        "duration_s": float(route["duration"]),
                        "duration_min": float(route["duration"]) / 60.0,
                    }
                    self._cache[key] = result
                    return result

            except requests.exceptions.Timeout:
                time.sleep(0.8 * attempt)
            except Exception:
                time.sleep(0.8 * attempt)

        return None