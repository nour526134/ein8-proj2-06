import math
import random
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
import json
from datetime import datetime
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.osm.itinerary_manager import ItineraryManager
from src.gtfs_service import GTFSService


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance Haversine en mètres."""
    R = 6371000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(R * c)


_profile_path = Path(__file__).resolve().parent.parent.parent / "data/traffic/bordeaux_profile.json"
if _profile_path.exists():
    with open(_profile_path) as _f:
        BORDEAUX_TRAFFIC_PROFILE = json.load(_f)
else:
    BORDEAUX_TRAFFIC_PROFILE = [
        0.04, 0.04, 0.04, 0.04, 0.04, 0.09,
        0.26, 0.56, 0.74, 0.63, 0.41, 0.36,
        0.39, 0.45, 0.40, 0.44, 0.58, 0.81,
        0.73, 0.58, 0.40, 0.26, 0.15, 0.07,
    ]


class CarSimulator:
    """
    Simulateur de voiture orienté RL.

    Scénarios au reset (contrôlés par scenario_prob) :
      - scenario=0 (probabilité 1 - scenario_prob) : scénario aléatoire classique
      - scenario=1 (probabilité scenario_prob)     : scénario train favorable
          → gare choisie parmi celles proches d'un parking (via ParkingServiceRT)
          → destination = meilleure selon find_best_destination_by_wait (TransitRealtimeService)
          → un point de détour OSM est injecté pour allonger le trajet voiture

    Interface principale :
    - reset(seed=None, k_stations=1, parking_service=None, transit_service=None)
    - advance(dt_min)
    - get_metrics()
    - get_state()
    - get_k_stations()
    - load_station(station)
    - simulate_to_station(station, dt_min, ...)
    - sync_realtime_callback : callable optionnel appelé au reset pour synchroniser les APIs
    """

    def __init__(
        self,
        graphml_path: Optional[str] = None,
        v_max_kmh: float = 50.0,
        v_min_kmh: float = 10.0,
        noise_amp: float = 0.05,
        seed: Optional[int] = None,
        use_real_traffic: bool = False,
        scenario_prob: float = 0.5,
        detour_factor: float = 1.5,
        sync_realtime_callback: Optional[Callable] = None,
    ):
        self.v_max = float(v_max_kmh)
        self.v_min = float(v_min_kmh)
        self.noise_amp = float(noise_amp)
        self.rng = random.Random(seed)

        self.use_real_traffic = use_real_traffic

        # Probabilité de tirer le scénario train favorable (1) vs aléatoire (0)
        self.scenario_prob = float(np.clip(scenario_prob, 0.0, 1.0))
        # Facteur multiplicatif pour le détour voiture dans le scénario 1
        self.detour_factor = float(detour_factor)
        # Scénario courant (défini au reset)
        self.current_scenario: int = 0

        # Callback optionnel de synchronisation temps réel (appelé au début de reset)
        self.sync_realtime_callback: Optional[Callable] = sync_realtime_callback

        # Parking éventuel
        self.parking = None
        self.dist_to_parking_km = 0.0
        self.time_to_parking_min = 0.0

        # Services
        self.gtfs_service = GTFSService()
        self.stations = self.gtfs_service.load_stops()

        # Routeur OSM
        self.router = ItineraryManager()

        if not hasattr(self.router, "G"):
            raise ValueError("ItineraryManager doit exposer un graphe via self.G")

        # Etat interne
        self.current_hour = 8.0
        self.current_saturation = 0.0
        self.current_speed_kmh = self.v_max

        self.position_lat = None
        self.position_lon = None
        self.position_node = None

        self.current_index = 0
        self.station_path_nodes: List[Any] = []

        self.closest_station_id = None
        self.station_lat = None
        self.station_lon = None
        self.station = None

        self.dest_id = None
        self.dest_station_lat = None
        self.dest_station_lon = None

        self.remaining_distance_km = 0.0
        self.road_dist_to_dest_km = 0.0
        self.air_dist_to_dest_km = 0.0

        self.time_to_station = 0.0
        self.total_car_time_to_dest_min = 0.0

        self.k_stations = []

        # Nœud de détour (scénario 1 uniquement)
        self._detour_node = None

    # -------------------------------------------------------------------------
    # Outils internes
    # -------------------------------------------------------------------------

    def _safe_path_distance_km(self, path):
        if path is None or len(path) < 2:
            return None
        return self.router.path_distance_km(path)

    def _safe_nearest_node(self, lat, lon):
        return self.router.nearest_node(lat, lon)

    def _safe_shortest_path(self, node_a, node_b):
        try:
            return self.router.shortest_path_nodes(node_a, node_b)
        except Exception:
            return None

    def _compute_speed_from_saturation(self, saturation: float) -> float:
        return self.v_min + (1.0 - saturation) * (self.v_max - self.v_min)

    def _compute_saturation_from_speed(self, speed: float) -> float:
        if self.v_max <= self.v_min:
            return 0.0
        sat = 1.0 - (speed - self.v_min) / (self.v_max - self.v_min)
        return max(0.0, min(1.0, sat))

    # -------------------------------------------------------------------------
    # Trafic
    # -------------------------------------------------------------------------

    def traffic_level(self, hour: float) -> float:
        """
        Trafic basé sur le profil réel de Bordeaux Métropole.
        """
        hour = hour % 24.0
        h0 = int(hour) % 24
        h1 = (h0 + 1) % 24
        frac = hour - int(hour)
        base = BORDEAUX_TRAFFIC_PROFILE[h0] * (1 - frac) + BORDEAUX_TRAFFIC_PROFILE[h1] * frac
        noise = self.rng.uniform(-self.noise_amp, self.noise_amp)
        return float(max(0.0, min(base + noise, 1.0)))

    def compute_average_traffic(self, total_time_min: float, step_min: float = 1.0) -> float:
        if total_time_min <= 0:
            return self.current_saturation

        t = self.current_hour
        total = 0.0
        n = 0

        time_elapsed = 0.0

        while time_elapsed < total_time_min:
            traffic = self.traffic_level(t)
            total += traffic
            n += 1

            t += step_min / 60.0
            time_elapsed += step_min

        return total / max(n, 1)

    def fetch_real_traffic_speed(self, lat: float, lon: float) -> Optional[Dict[str, float]]:
        """
        Point d'extension pour trafic réel (API TomTom, HERE, etc.).
        Retourne None par défaut → fallback sur profil historique.
        """
        return None

    def update_traffic(self):
        """
        Met à jour current_saturation et current_speed_kmh.
        """
        if self.use_real_traffic and self.position_lat is not None and self.position_lon is not None:
            traffic = self.fetch_real_traffic_speed(self.position_lat, self.position_lon)
            if traffic is not None and "current_speed" in traffic:
                speed = float(traffic["current_speed"])
                speed = max(self.v_min, min(speed, self.v_max))
                self.current_speed_kmh = speed
                free_flow = traffic.get("free_flow_speed")
                if free_flow is not None and free_flow > 0:
                    sat = 1.0 - speed / float(free_flow)
                    self.current_saturation = max(0.0, min(1.0, sat))
                else:
                    self.current_saturation = self._compute_saturation_from_speed(speed)
                return

        self.current_saturation = self.traffic_level(self.current_hour)
        self.current_speed_kmh = self._compute_speed_from_saturation(self.current_saturation)

    # -------------------------------------------------------------------------
    # Recherche station / destination
    # -------------------------------------------------------------------------

    def find_k_closest_stations(self, lat: float, lon: float, k: int = 1):
        distances = []
        for sid, sdata in self.stations.items():
            dist = haversine_m(lat, lon, sdata["lat"], sdata["lon"]) / 1000.0
            distances.append((sid, dist))
        distances.sort(key=lambda x: x[1])
        return distances[:k]

    def _current_real_hour(self) -> float:
        """Retourne l'heure réelle actuelle en heures décimales (ex: 8h30 → 8.5)."""
        now = datetime.now()
        return now.hour + now.minute / 60.0 + now.second / 3600.0

    def _recompute_dest_metrics(self):
        if self.position_lat is None or self.position_lon is None:
            return

        if self.dest_station_lat is None or self.dest_station_lon is None:
            self.air_dist_to_dest_km = 0.0
            self.road_dist_to_dest_km = 0.0
            self.total_car_time_to_dest_min = 0.0
            return

        self.air_dist_to_dest_km = (
            haversine_m(
                self.position_lat,
                self.position_lon,
                self.dest_station_lat,
                self.dest_station_lon,
            ) / 1000.0
        )

        current_node = self._safe_nearest_node(self.position_lat, self.position_lon)
        dest_node = self._safe_nearest_node(self.dest_station_lat, self.dest_station_lon)

        # Cas scénario train favorable : garder le détour
        if self.current_scenario == 1 and self._detour_node is not None:
            try:
                path1 = self._safe_shortest_path(current_node, self._detour_node)
                path2 = self._safe_shortest_path(self._detour_node, dest_node)

                d1 = self._safe_path_distance_km(path1)
                d2 = self._safe_path_distance_km(path2)

                if d1 is not None and d2 is not None:
                    self.road_dist_to_dest_km = d1 + d2
                    self.total_car_time_to_dest_min = (
                        60.0 * self.road_dist_to_dest_km / max(self.current_speed_kmh, 1e-6)
                    )
                    return
            except Exception:
                pass

        # Cas normal : chemin optimal
        try:
            path = self._safe_shortest_path(current_node, dest_node)
            road_dist = self._safe_path_distance_km(path)

            if road_dist is None:
                road_dist = self.air_dist_to_dest_km

            self.road_dist_to_dest_km = road_dist

        except Exception:
            self.road_dist_to_dest_km = self.air_dist_to_dest_km

        self.total_car_time_to_dest_min = (
            60.0 * self.road_dist_to_dest_km / max(self.current_speed_kmh, 1e-6)
        )
    # -------------------------------------------------------------------------
    # Détour (scénario train favorable)
    # -------------------------------------------------------------------------

    def _find_detour_node(self, origin_node, dest_node) -> Optional[Any]:
        """
        Cherche un nœud OSM de détour tel que le chemin origin → detour → dest
        soit significativement plus long que le chemin direct origin → dest.

        Stratégie : on échantillonne des nœuds du graphe dans une direction
        perpendiculaire à l'axe origin→dest, à une distance ~detour_factor × dist_directe.
        On retient le nœud qui maximise la distance totale passant par lui.
        """
        try:
            lat_o, lon_o = self.router.get_node_coords(origin_node)
            lat_d, lon_d = self.router.get_node_coords(dest_node)

            direct_path = self._safe_shortest_path(origin_node, dest_node)
            direct_dist = self._safe_path_distance_km(direct_path)
            if direct_dist is None or direct_dist < 0.5:
                return None

            # Centre du segment et vecteur perpendiculaire
            mid_lat = (lat_o + lat_d) / 2.0
            mid_lon = (lon_o + lon_d) / 2.0
            vec_lat = lat_d - lat_o
            vec_lon = lon_d - lon_o
            norm = math.sqrt(vec_lat ** 2 + vec_lon ** 2)
            if norm < 1e-9:
                return None
            perp_lat = -vec_lon / norm
            perp_lon = vec_lat / norm

            # Rayon de recherche : ~detour_factor × distance directe (en degrés approx.)
            radius_deg = (self.detour_factor * direct_dist) / 111.0

            all_nodes = list(self.router.G.nodes())
            candidates = []
            for n in self.rng.sample(all_nodes, min(300, len(all_nodes))):
                try:
                    nlat, nlon = self.router.get_node_coords(n)
                except Exception:
                    continue
                # Garder les nœuds proches de l'axe perpendiculaire au milieu
                proj = (nlat - mid_lat) * perp_lat + (nlon - mid_lon) * perp_lon
                if abs(proj) < radius_deg * 0.2:
                    continue
                dist_from_mid = math.sqrt((nlat - mid_lat) ** 2 + (nlon - mid_lon) ** 2)
                if dist_from_mid > radius_deg * 1.5:
                    continue
                candidates.append(n)

            if not candidates:
                return None

            best_node = None
            best_total = 0.0

            for cn in candidates[:50]:
                p1 = self._safe_shortest_path(origin_node, cn)
                p2 = self._safe_shortest_path(cn, dest_node)
                d1 = self._safe_path_distance_km(p1)
                d2 = self._safe_path_distance_km(p2)
                if d1 is None or d2 is None:
                    continue
                total = d1 + d2
                if total > best_total and total > self.detour_factor * direct_dist:
                    best_total = total
                    best_node = cn

            return best_node

        except Exception as e:
            print(f"[CarSimulator] _find_detour_node error: {e}")
            return None

    def _build_detour_path(self, origin_node, dest_node) -> Optional[List]:
        """
        Construit le chemin origin → detour_node → dest en passant par un nœud
        de détour. Retourne None si aucun détour valide n'est trouvé.
        """
        detour = self._find_detour_node(origin_node, dest_node)
        if detour is None:
            return None
        self._detour_node = detour
        p1 = self._safe_shortest_path(origin_node, detour)
        p2 = self._safe_shortest_path(detour, dest_node)
        if p1 is None or p2 is None:
            return None
        # Concatène en évitant le nœud doublon à la jonction
        return p1 + p2[1:]

    # -------------------------------------------------------------------------
    # Reset principal
    # -------------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        k_stations: int = 1,
        parking_service=None,
        transit_service=None,
    ):
        """
        Réinitialise le simulateur.

        Parameters
        ----------
        seed            : graine aléatoire
        k_stations      : nombre de gares candidates à considérer
        parking_service : instance de ParkingServiceRT (nécessaire pour scénario 1)
        transit_service : instance de TransitRealtimeService (nécessaire pour scénario 1)
        """
        if seed is not None:
            self.rng.seed(seed)

        # ── Synchronisation temps réel via callback ──────────────────────────
        if self.sync_realtime_callback is not None:
            try:
                self.sync_realtime_callback()
            except Exception as e:
                print(f"[CarSimulator] sync_realtime_callback error: {e}")

        # ── Tirage du scénario ───────────────────────────────────────────────
        self.current_scenario = 1 if random.random() < 0.5 else 0
        if self.current_scenario == 1 and parking_service is not None and transit_service is not None:
            result = self._reset_train_favorable(seed, k_stations, parking_service, transit_service)
            if result is not None:
                return result
            # Fallback vers scénario aléatoire si le scénario 1 échoue
            print("[CarSimulator] Scénario 1 échoué → fallback scénario 0")
            self.current_scenario = 0

        return self._reset_random(seed, k_stations)

    # ── Scénario 0 : aléatoire ────────────────────────────────────────────────

    def _reset_random(self, seed: Optional[int] = None, k_stations: int = 1):
        """Scénario aléatoire classique (comportement original)."""
        all_nodes = list(self.router.G.nodes())
        max_retries = 20
        self._detour_node = None

        for _ in range(max_retries):
            self.current_hour = self._current_real_hour()

            candidate_node = self.rng.choice(all_nodes)
            candidate_lat, candidate_lon = self.router.get_node_coords(candidate_node)

            closest = self.find_k_closest_stations(candidate_lat, candidate_lon, k=k_stations)
            possible_stations = []

            for sid, _ in closest:
                sdata = self.stations[sid]
                station_node = self._safe_nearest_node(sdata["lat"], sdata["lon"])
                path = self._safe_shortest_path(candidate_node, station_node)
                road_dist = self._safe_path_distance_km(path)
                if road_dist is None:
                    continue
                possible_stations.append({
                    "id": sid,
                    "lat": sdata["lat"],
                    "lon": sdata["lon"],
                    "dist_km": road_dist,
                    "path": path,
                    "node": station_node,
                })

            if not possible_stations:
                continue

            possible_stations.sort(key=lambda x: x["dist_km"])
            best = possible_stations[0]

            if best["dist_km"] < 0.2:
                continue

            reachable = self.gtfs_service.get_reachable_stations(best["id"])
            if reachable.empty:
                continue

            reachable_records = reachable.to_dict(orient="records")
            far_destinations = [
                r for r in reachable_records
                if self.gtfs_service.train_trip_time(best["id"], r["destination_station_id"]) >= 15.0
            ]

            if not far_destinations:
                continue

            dest_row = self.rng.choice(far_destinations)
            dest_lat = dest_row["destination_lat"]
            dest_lon = dest_row["destination_lon"]
            dest_node = self._safe_nearest_node(dest_lat, dest_lon)

            dist_candidate_to_station = haversine_m(candidate_lat, candidate_lon, best["lat"], best["lon"])
            dist_candidate_to_dest = haversine_m(candidate_lat, candidate_lon, dest_lat, dest_lon)
            dist_station_to_dest = haversine_m(best["lat"], best["lon"], dest_lat, dest_lon)

            if dist_candidate_to_dest < dist_candidate_to_station:
                continue
            if dist_station_to_dest > dist_candidate_to_dest:
                continue

            path_to_dest = self._safe_shortest_path(candidate_node, dest_node)
            total_dist = self._safe_path_distance_km(path_to_dest)

            if total_dist is None or total_dist < 0.5:
                continue

            self.position_lat = candidate_lat
            self.position_lon = candidate_lon
            self.position_node = candidate_node
            self.current_index = 0

            self.update_traffic()
            est_car_time = 60.0 * total_dist / max(self.current_speed_kmh, 1e-6)

            if est_car_time < 20.0:
                continue

            self.k_stations = possible_stations
            self.closest_station_id = best["id"]
            self.station_lat = best["lat"]
            self.station_lon = best["lon"]
            self.station = {
                "id": best["id"],
                "lat": best["lat"],
                "lon": best["lon"],
            }
            self.station_path_nodes = best["path"]

            self.dest_id = dest_row["destination_station_id"]
            self.dest_station_lat = dest_lat
            self.dest_station_lon = dest_lon

            self.remaining_distance_km = best["dist_km"]
            self.time_to_station = 60.0 * self.remaining_distance_km / max(self.current_speed_kmh, 1e-6)

            self.road_dist_to_dest_km = total_dist
            self.air_dist_to_dest_km = haversine_m(candidate_lat, candidate_lon, dest_lat, dest_lon) / 1000.0
            self.total_car_time_to_dest_min = est_car_time

            self.dist_to_parking_km = 0.0
            self.time_to_parking_min = 0.0
            return self.get_state()

        return self._reset_fallback()

    # ── Scénario 1 : train favorable ──────────────────────────────────────────

    def _reset_train_favorable(
        self,
        seed: Optional[int],
        k_stations: int,
        parking_service,
        transit_service,
    ):
        """
        Scénario train favorable :
        1. Choisit aléatoirement une gare parmi les top-k les plus proches de leur parking.
        2. Choisit la meilleure destination selon le temps d'attente.
        3. Place la voiture juste à côté du parking de cette gare.
        4. Allonge le trajet voiture vers la destination avec un détour.
        """

        self._detour_node = None

        if seed is not None:
            self.rng.seed(seed)

        self.current_hour = self._current_real_hour()

        try:
            station_parking_pairs = parking_service.find_stations_closest_to_their_parking(
                stations=self.stations,
                top_k=6,
            )
        except Exception as e:
            print(f"[CarSimulator] _reset_train_favorable: erreur find_stations_closest: {e}")
            return None

        if not station_parking_pairs:
            return None

        pair = self.rng.choice(station_parking_pairs)

        station_id = pair["station_id"]
        sdata = self.stations.get(station_id)
        parking = pair.get("parking")

        if sdata is None or parking is None:
            return None

        # Placer la voiture juste à côté du parking (~50 m)
        offset_deg = 50.0 / 111_000.0

        start_lat = parking["lat"] + offset_deg
        start_lon = parking["lon"] + offset_deg

        candidate_node = self._safe_nearest_node(start_lat, start_lon)
        candidate_lat, candidate_lon = self.router.get_node_coords(candidate_node)

        station_node = self._safe_nearest_node(sdata["lat"], sdata["lon"])

        path_to_station = self._safe_shortest_path(candidate_node, station_node)
        road_dist_station = self._safe_path_distance_km(path_to_station)

        if road_dist_station is None:
            road_dist_station = haversine_m(
                candidate_lat,
                candidate_lon,
                sdata["lat"],
                sdata["lon"],
            ) / 1000.0
            path_to_station = []

        # Heure d'arrivée estimée à la gare pour chercher le bon train
        walk_to_station = parking.get("walk_min", 0.0)
        current_time_min = self.current_hour * 60.0
        arrival_for_train = current_time_min + walk_to_station

        try:
            best_dest_info = transit_service.find_best_destination_by_wait(
                origin_id=station_id,
                current_time_min=arrival_for_train,
            )
        except Exception as e:
            print(f"[CarSimulator] find_best_destination_by_wait error: {e}")
            return None

        if best_dest_info is None:
            return None

        dest_id = best_dest_info["destination"]
        dest_sdata = self.stations.get(dest_id)

        if dest_sdata is None:
            try:
                dest_stops = transit_service.gtfs.load_stops()
                dest_sdata = dest_stops.get(dest_id)
            except Exception:
                pass

        if dest_sdata is None:
            return None

        dest_lat = dest_sdata["lat"]
        dest_lon = dest_sdata["lon"]

        train_trip = self.gtfs_service.train_trip_time(station_id, dest_id)

        if not np.isfinite(train_trip) :
            return None

        dest_node = self._safe_nearest_node(dest_lat, dest_lon)

        # Chemin voiture vers destination avec détour
        detour_path = self._build_detour_path(candidate_node, dest_node)

        if detour_path is not None:
            path_to_dest = detour_path
            total_dist = self._safe_path_distance_km(path_to_dest)
        else:
            path_to_dest = self._safe_shortest_path(candidate_node, dest_node)
            total_dist = self._safe_path_distance_km(path_to_dest)

        if total_dist is None or total_dist < 0.5:
            return None

        self.update_traffic()

        est_car_time = 60.0 * total_dist / max(self.current_speed_kmh, 1e-6)

        if est_car_time < 20.0:
            return None

        # Commit état
        self.position_lat = candidate_lat
        self.position_lon = candidate_lon
        self.position_node = candidate_node
        self.current_index = 0

        closest = self.find_k_closest_stations(candidate_lat, candidate_lon, k=k_stations)

        possible_stations = []

        for sid, _ in closest:
            s = self.stations[sid]
            sn = self._safe_nearest_node(s["lat"], s["lon"])
            p = self._safe_shortest_path(candidate_node, sn)
            rd = self._safe_path_distance_km(p)

            if rd is None:
                continue

            possible_stations.append({
                "id": sid,
                "lat": s["lat"],
                "lon": s["lon"],
                "dist_km": rd,
                "path": p,
                "node": sn,
            })

        self.k_stations = possible_stations

        self.closest_station_id = station_id
        self.station_lat = sdata["lat"]
        self.station_lon = sdata["lon"]
        self.station = {
            "id": station_id,
            "lat": sdata["lat"],
            "lon": sdata["lon"],
        }

        self.station_path_nodes = path_to_station

        self.dest_id = dest_id
        self.dest_station_lat = dest_lat
        self.dest_station_lon = dest_lon

        self.remaining_distance_km = road_dist_station
        self.time_to_station = (
            60.0 * road_dist_station / max(self.current_speed_kmh, 1e-6)
        )

        self.road_dist_to_dest_km = total_dist
        self.air_dist_to_dest_km = (
            haversine_m(candidate_lat, candidate_lon, dest_lat, dest_lon) / 1000.0
        )
        self.total_car_time_to_dest_min = est_car_time

        self.route_to_dest_nodes = path_to_dest if path_to_dest else []

        # Parking : voiture placée à côté du parking
        dist_to_parking = haversine_m(
            candidate_lat,
            candidate_lon,
            parking["lat"],
            parking["lon"],
        ) / 1000.0

        self.parking = parking
        self.dist_to_parking_km = dist_to_parking
        self.time_to_parking_min = (
            60.0 * dist_to_parking / max(self.current_speed_kmh, 1e-6)
        )
        return self.get_state()

    # ── Fallback neutre ───────────────────────────────────────────────────────

    def _reset_fallback(self):
        """Fallback neutre si tous les essais échouent."""
        start_station_id = next(iter(self.stations))
        start_station = self.stations[start_station_id]

        self.current_hour = self._current_real_hour()
        self.position_lat = start_station["lat"]
        self.position_lon = start_station["lon"]
        self.position_node = self._safe_nearest_node(self.position_lat, self.position_lon)
        self.current_index = 0

        self.closest_station_id = start_station_id
        self.station_lat = start_station["lat"]
        self.station_lon = start_station["lon"]
        self.station = {
            "id": start_station_id,
            "lat": start_station["lat"],
            "lon": start_station["lon"],
        }
        self.station_path_nodes = []

        self.dest_id = start_station_id
        self.dest_station_lat = start_station["lat"]
        self.dest_station_lon = start_station["lon"]

        self.remaining_distance_km = 0.0
        self.k_stations = []
        self._detour_node = None

        self.update_traffic()
        self.time_to_station = 0.0
        self.road_dist_to_dest_km = 0.0
        self.air_dist_to_dest_km = 0.0
        self.total_car_time_to_dest_min = 0.0
        self.dist_to_parking_km = 0.0
        self.time_to_parking_min = 0.0

        return self.get_state()

    # -------------------------------------------------------------------------
    # Snapshot / restore
    # -------------------------------------------------------------------------

    def snapshot(self):
        return {
            "current_hour": self.current_hour,
            "current_saturation": self.current_saturation,
            "current_speed_kmh": self.current_speed_kmh,
            "position_lat": self.position_lat,
            "position_lon": self.position_lon,
            "position_node": self.position_node,
            "current_index": self.current_index,
            "station_path_nodes": list(self.station_path_nodes),
            "closest_station_id": self.closest_station_id,
            "station_lat": self.station_lat,
            "station_lon": self.station_lon,
            "station": self.station,
            "dest_id": self.dest_id,
            "dest_station_lat": self.dest_station_lat,
            "dest_station_lon": self.dest_station_lon,
            "remaining_distance_km": self.remaining_distance_km,
            "road_dist_to_dest_km": self.road_dist_to_dest_km,
            "air_dist_to_dest_km": self.air_dist_to_dest_km,
            "time_to_station": self.time_to_station,
            "total_car_time_to_dest_min": self.total_car_time_to_dest_min,
            "dist_to_parking_km": self.dist_to_parking_km,
            "time_to_parking_min": self.time_to_parking_min,
            "parking": self.parking,
            "k_stations": list(self.k_stations),
            "current_scenario": self.current_scenario,
            "_detour_node": self._detour_node,
        }

    def restore(self, snap):
        for k, v in snap.items():
            setattr(self, k, v)

    # -------------------------------------------------------------------------
    # Station loading
    # -------------------------------------------------------------------------

    def load_station(self, station: Dict[str, Any]):
        current_node = self._safe_nearest_node(self.position_lat, self.position_lon)
        next_node = station["node"]

        path = self._safe_shortest_path(current_node, next_node)
        road_dist = self._safe_path_distance_km(path)

        if road_dist is None:
            raise ValueError(f"Impossible de calculer un chemin vers la station {station['id']}")

        self.station_path_nodes = path
        self.current_index = 0

        self.closest_station_id = station["id"]
        self.station_lat = station["lat"]
        self.station_lon = station["lon"]
        self.station = {
            "id": station["id"],
            "lat": station["lat"],
            "lon": station["lon"],
        }

        self.remaining_distance_km = road_dist
        self.time_to_station = 60.0 * road_dist / max(self.current_speed_kmh, 1e-6)

    # -------------------------------------------------------------------------
    # Avance du véhicule
    # -------------------------------------------------------------------------

    def advance(self, dt_min: float):
        if dt_min <= 0:
            return

        self.update_traffic()
        speed = self.current_speed_kmh
        distance_step = speed * dt_min / 60.0
        distance_traveled = 0.0

        while distance_step > 0 and self.current_index < len(self.station_path_nodes) - 1:
            n1 = self.station_path_nodes[self.current_index]
            n2 = self.station_path_nodes[self.current_index + 1]

            d = self.router.get_edge_length_km(n1, n2)
            if d <= 0:
                self.current_index += 1
                continue

            if distance_step >= d:
                self.current_index += 1
                self.position_lat, self.position_lon = self.router.get_node_coords(n2)
                self.position_node = n2
                distance_step -= d
                distance_traveled += d
            else:
                ratio = distance_step / d
                lat1, lon1 = self.router.get_node_coords(n1)
                lat2, lon2 = self.router.get_node_coords(n2)
                self.position_lat = lat1 + ratio * (lat2 - lat1)
                self.position_lon = lon1 + ratio * (lon2 - lon1)
                distance_traveled += distance_step
                distance_step = 0.0

        self.remaining_distance_km = max(0.0, self.remaining_distance_km - distance_traveled)
        self.current_hour += dt_min / 60.0

        self.update_traffic()

        self.time_to_station = (
            60.0 * self.remaining_distance_km / max(self.current_speed_kmh, 1e-6)
        )

        self._recompute_dest_metrics()

        if self.parking is not None:
            self._update_parking_metrics()

    def _update_parking_metrics(self):
        try:
            path = self._safe_shortest_path(
                self._safe_nearest_node(self.position_lat, self.position_lon),
                self._safe_nearest_node(self.parking["lat"], self.parking["lon"]),
            )
            dist = self._safe_path_distance_km(path)
            if dist is None:
                raise ValueError("Pas de chemin routier vers parking")
        except Exception:
            dist = haversine_m(
                self.position_lat, self.position_lon,
                self.parking["lat"], self.parking["lon"],
            ) / 1000.0

        self.dist_to_parking_km = dist
        self.time_to_parking_min = 60.0 * dist / max(self.current_speed_kmh, 1e-6)

    # -------------------------------------------------------------------------
    # Simulation auxiliaire
    # -------------------------------------------------------------------------

    def simulate_to_station(
        self,
        station: Dict[str, Any],
        dt_min: float,
        max_iterations: int = 200,
        decision_distance_km: float = 0.05,
    ):
        snap = self.snapshot()
        try:
            self.load_station(station)
        except Exception:
            self.restore(snap)
            return None

        for _ in range(max_iterations):
            self.advance(dt_min)
            if self.remaining_distance_km <= decision_distance_km:
                result = {
                    "station_id": station["id"],
                    "time_elapsed_min": (self.current_hour - snap["current_hour"]) * 60.0,
                    "dist_to_dest_km": self.road_dist_to_dest_km,
                }
                self.restore(snap)
                return result

        self.restore(snap)
        return None

    # -------------------------------------------------------------------------
    # Interface RL
    # -------------------------------------------------------------------------

    def get_metrics(self):
        return {
            "time_min": self.current_hour * 60.0,
            "traffic": self.current_saturation,
            "speed_kmh": self.current_speed_kmh,
            "dist_to_station_km": self.remaining_distance_km,
            "dist_to_dest_km": self.road_dist_to_dest_km,
            "dist_to_dest_air_km": self.air_dist_to_dest_km,
            "time_to_station_min": self.time_to_station,
            "car_time_to_dest_min": self.total_car_time_to_dest_min,
            "dist_to_parking_km": self.dist_to_parking_km,
            "time_to_parking_min": self.time_to_parking_min,
            "scenario": self.current_scenario,
        }

    def get_state(self):
        return {
            "hour": self.current_hour,
            "traffic": self.current_saturation,
            "speed_kmh": self.current_speed_kmh,
            "dist_to_station_km": self.remaining_distance_km,
            "time_to_station_min": self.time_to_station,
            "dist_to_dest_km": self.road_dist_to_dest_km,
            "car_time_to_dest_min": self.total_car_time_to_dest_min,
            "closest_station_id": self.closest_station_id,
            "dest_id": self.dest_id,
            "position_lat": self.position_lat,
            "position_lon": self.position_lon,
            "scenario": self.current_scenario,
        }

    def get_dist_to_station_km(self):
        return self.remaining_distance_km

    def get_closest_station(self):
        return self.station

    def get_dest_id(self):
        return self.dest_id

    def get_time_min(self):
        return self.current_hour * 60.0

    def car_time_to_station(self):
        return self.time_to_station

    def car_time_to_dest(self):
        return self.total_car_time_to_dest_min

    def get_k_stations(self):
        return self.k_stations

    def distance_to(self, lat: float, lon: float) -> float:
        try:
            path = self._safe_shortest_path(
                self._safe_nearest_node(self.position_lat, self.position_lon),
                self._safe_nearest_node(lat, lon),
            )
            dist = self._safe_path_distance_km(path)
            if dist is None:
                raise ValueError("Pas de chemin")
            return dist
        except Exception:
            return haversine_m(self.position_lat, self.position_lon, lat, lon) / 1000.0

    def set_parking(self, parking: Dict[str, Any]):
        self.parking = parking
        self._update_parking_metrics()

    def car_time_to_parking(self, parking: Dict[str, Any], max_est_car_time: int) -> float:
        if parking is None:
            return max_est_car_time
        speed = max(self.current_speed_kmh, 1e-6)
        try:
            path = self._safe_shortest_path(
                self._safe_nearest_node(self.position_lat, self.position_lon),
                self._safe_nearest_node(parking["lat"], parking["lon"]),
            )
            dist = self._safe_path_distance_km(path)
            if dist is None:
                raise ValueError("Pas de chemin parking")
        except Exception:
            dist = haversine_m(
                self.position_lat, self.position_lon,
                parking["lat"], parking["lon"],
            ) / 1000.0
        return 60.0 * dist / speed


if __name__ == "__main__":
    sim = CarSimulator(seed=42, use_real_traffic=False, scenario_prob=0.5)

    state = sim.reset(seed=42, k_stations=3)

    print("=== RESET ===")
    print(state)
    print("Scénario:", state.get("scenario"))
    print(sim.get_closest_station())
    print(sim.get_metrics())

    print("\n=== AVANCE 5 MIN ===")
    sim.advance(dt_min=5)
    print(sim.get_state())
    print(sim.get_metrics())

    print("\n=== TEST K STATIONS ===")
    for s in sim.get_k_stations():
        print(s["id"], s["dist_km"])

    if sim.get_k_stations():
        station_test = sim.get_k_stations()[0]
        result = sim.simulate_to_station(station_test, dt_min=2, max_iterations=100)
        print("\n=== SIMULATE TO STATION ===")
        print(result)