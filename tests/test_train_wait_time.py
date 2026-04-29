import math
import sys
from pathlib import Path

import pytest

from src.gtfs_service import GTFSService


@pytest.fixture
def service_from_data_csv():
	repo_root = Path(__file__).resolve().parents[1]
	candidates = [repo_root / "data" / "gtfs_bordeaux", repo_root / "data" / "gtfs"]

	gtfs_dir = None
	for candidate in candidates:
		if candidate.exists():
			gtfs_dir = candidate
			break

	if gtfs_dir is None:
		pytest.skip("Aucun dossier GTFS trouvé dans data/gtfs_bordeaux ou data/gtfs")

	return GTFSService(gtfs_dir=str(gtfs_dir))


def _pick_valid_origin_dest(service: GTFSService):
	st = service._stop_times.sort_values(["trip_id", "stop_sequence"])

	for _, group in st.groupby("trip_id"):
		ordered = group.sort_values("stop_sequence")
		stop_ids = ordered["stop_id"].astype(str).tolist()
		if len(stop_ids) < 2:
			continue

		origin = stop_ids[0]
		dest = stop_ids[-1]
		departures = _valid_departures(service, origin, dest)
		if len(departures) > 0:
			return origin, dest, departures

	raise AssertionError("Impossible de trouver une paire origin/dest valide dans les donnees GTFS")


def _valid_departures(service: GTFSService, origin: str, dest: str):
	trips_origin = service._stop_to_trips.get(str(origin), set())
	trips_dest = service._stop_to_trips.get(str(dest), set())
	common_trips = trips_origin & trips_dest

	st = service._stop_times[service._stop_times["trip_id"].isin(common_trips)].copy()
	origin_rows = st[st["stop_id"] == str(origin)][["trip_id", "stop_sequence", "departure_min"]].rename(
		columns={"stop_sequence": "seq_orig", "departure_min": "dep_orig"}
	)
	dest_rows = st[st["stop_id"] == str(dest)][["trip_id", "stop_sequence"]].rename(
		columns={"stop_sequence": "seq_dest"}
	)
	merged = origin_rows.merge(dest_rows, on="trip_id")
	valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()
	return valid["dep_orig"].dropna().astype(float).values


def _to_hhmmss(minute_value: float) -> str:
	minute_int = int(minute_value)
	hours = minute_int // 60
	minutes = minute_int % 60
	return f"{hours:02d}:{minutes:02d}:00"


def test_wait_time_is_zero_at_exact_departure(service_from_data_csv):
	origin, dest, departures = _pick_valid_origin_dest(service_from_data_csv)
	exact_departure = float(min(departures))

	wait = service_from_data_csv.train_wait_time_from_trips(origin, dest, exact_departure)
	assert wait == 0.0


def test_wait_time_accepts_hhmmss_current_time(service_from_data_csv):
	origin, dest, departures = _pick_valid_origin_dest(service_from_data_csv)
	t = float(min(departures))

	wait_float = service_from_data_csv.train_wait_time_from_trips(origin, dest, t)
	wait_str = service_from_data_csv.train_wait_time_from_trips(origin, dest, _to_hhmmss(t))
	assert wait_float == wait_str


def test_wait_time_rolls_over_to_next_cycle(service_from_data_csv):
	origin, dest, departures = _pick_valid_origin_dest(service_from_data_csv)

	current_after_all = float(max(departures) + 1.0)
	expected = (24 * 60 - current_after_all) + float(min(departures))
	wait = service_from_data_csv.train_wait_time_from_trips(origin, dest, current_after_all)

	assert wait == expected


def test_wait_time_returns_inf_when_no_common_trip(service_from_data_csv):
	wait = service_from_data_csv.train_wait_time_from_trips("__UNKNOWN_ORIGIN__", "__UNKNOWN_DEST__", 8 * 60)
	assert math.isinf(wait)


if __name__ == "__main__":
	# Allows running this module directly: python -m tests.test_train_wait_time
	raise SystemExit(pytest.main([__file__]))

