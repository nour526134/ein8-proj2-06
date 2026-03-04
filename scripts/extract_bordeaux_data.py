import pandas as pd
from pathlib import Path
import shutil, json
from math import radians, cos, sin, sqrt, atan2

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return R * (2 * atan2(sqrt(a), sqrt(1 - a)))

def _read_gtfs_file(folder: Path, base: str):
    for ext in (".csv", ".txt"):
        p = folder / f"{base}{ext}"
        if p.exists():
            return p, pd.read_csv(p)
    return None, None

def extract_bordeaux_gtfs(
    input_dir="data/gtfs",
    output_dir="data/gtfs_bordeaux",
    center_lat=44.8378,
    center_lon=-0.5792,
    radius_km=30.0
):
    input_path, output_path = Path(input_dir), Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stops_path, stops = _read_gtfs_file(input_path, "stops")
    if stops is None:
        raise FileNotFoundError("stops.csv/txt introuvable")

    stops["distance_km"] = stops.apply(
        lambda r: haversine_km(center_lat, center_lon, r["stop_lat"], r["stop_lon"])
        if pd.notna(r.get("stop_lat")) and pd.notna(r.get("stop_lon")) else 999,
        axis=1
    )
    b_stops = stops[stops["distance_km"] <= radius_km].drop(columns=["distance_km"])
    stop_ext = stops_path.suffix
    b_stops.to_csv(output_path / f"stops{stop_ext}", index=False)
    stop_ids = set(b_stops["stop_id"])

    st_path, stop_times = _read_gtfs_file(input_path, "stop_times")
    if stop_times is None:
        raise FileNotFoundError("stop_times.csv/txt introuvable")
    b_stop_times = stop_times[stop_times["stop_id"].isin(stop_ids)]
    st_ext = st_path.suffix
    b_stop_times.to_csv(output_path / f"stop_times{st_ext}", index=False)
    trip_ids = set(b_stop_times["trip_id"])

    trips_path, trips = _read_gtfs_file(input_path, "trips")
    if trips is None:
        raise FileNotFoundError("trips.csv/txt introuvable")
    b_trips = trips[trips["trip_id"].isin(trip_ids)]
    trips_ext = trips_path.suffix
    b_trips.to_csv(output_path / f"trips{trips_ext}", index=False)
    route_ids = set(b_trips["route_id"])

    routes_path, routes = _read_gtfs_file(input_path, "routes")
    if routes is None:
        raise FileNotFoundError("routes.csv/txt introuvable")
    b_routes = routes[routes["route_id"].isin(route_ids)]
    routes_ext = routes_path.suffix
    b_routes.to_csv(output_path / f"routes{routes_ext}", index=False)

    cal_path, cal = _read_gtfs_file(input_path, "calendar_dates")
    if cal is not None:
        cal_ext = cal_path.suffix
        if "service_id" in b_trips.columns and "service_id" in cal.columns:
            service_ids = set(b_trips["service_id"])
            cal = cal[cal["service_id"].isin(service_ids)]
        cal.to_csv(output_path / f"calendar_dates{cal_ext}", index=False)

    agency_path, _ = _read_gtfs_file(input_path, "agency")
    if agency_path is not None:
        shutil.copy2(agency_path, output_path / agency_path.name)

    return output_path

def create_readme(output_dir="data/gtfs_bordeaux"):
    p = Path(output_dir) / "README.md"
    p.write_text(
        "\n".join([
            "# GTFS Bordeaux Metropole",
            "",
            "Dataset GTFS filtré autour de Bordeaux (centre 44.8378, -0.5792) - rayon 30 km.",
            "",
            "Fichiers: stops, stop_times, trips, routes, calendar_dates (si dispo), agency (si dispo).",
        ]),
        encoding="utf-8"
    )

def create_extra_files(output_dir="data/gtfs_bordeaux"):
    out = Path(output_dir)
    meta = {"source": "GTFS Bordeaux Métropole", "date_generation": pd.Timestamp.now().isoformat(), "fichiers": []}

    for f in ["stops.csv","stops.txt","stop_times.csv","stop_times.txt","trips.csv","trips.txt","routes.csv","routes.txt","calendar_dates.csv","calendar_dates.txt","agency.csv","agency.txt"]:
        fp = out / f
        if fp.exists():
            meta["fichiers"].append({"nom": f, "taille": fp.stat().st_size, "date": pd.Timestamp.fromtimestamp(fp.stat().st_mtime).isoformat()})

    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    stops_file = out / "stops.csv"
    if stops_file.exists():
        s = pd.read_csv(stops_file)
        s[["stop_id","stop_name","stop_lat","stop_lon"]].to_csv(out / "stations_simple.csv", index=False, encoding="utf-8")

    summary = []
    for t, f in [("Gares","stops.csv"),("Horaires","stop_times.csv"),("Voyages","trips.csv"),("Lignes","routes.csv")]:
        fp = out / f
        if fp.exists():
            summary.append({"type": t, "fichier": f, "nombre": len(pd.read_csv(fp))})
    if summary:
        pd.DataFrame(summary).to_csv(out / "summary.csv", index=False, encoding="utf-8")

def run_extraction():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/gtfs")
    parser.add_argument("--output", default="data/gtfs_bordeaux")
    parser.add_argument("--radius", type=float, default=30.0)
    parser.add_argument("--lat", type=float, default=44.8378)
    parser.add_argument("--lon", type=float, default=-0.5792)
    args = parser.parse_args()

    extract_bordeaux_gtfs(args.input, args.output, args.lat, args.lon, args.radius)
    create_readme(args.output)
    create_extra_files(args.output)

    print("✅ Téléchargement / extraction OK : dataset prêt dans data/gtfs_bordeaux/")
    
if __name__ == "__main__":
    run_extraction()