from pathlib import Path
import pandas as pd
import unicodedata
import re


INPUT_DIR = Path("data/gtfs")
OUTPUT_DIR = Path("data/gtfs_bordeaux")
ALLOWED_STATIONS = [

# centre / sud-ouest
"Begles",
"Talence Medoquine",
"Pessac",
"Pessac Alouette",

# ouest
"Cauderan Merignac",
"Merignac Arlac",

# nord-ouest
"Le Bouscat Sainte Germaine",
"Bruges",
"Blanquefort",

# est (rive droite)
"Cenon",
"Bassens",

# sud-ouest
"Gazinet Cestas"
"Villenave d'Ornon"

]
# Saint-Jean à exclure
SAINT_JEAN_PATTERNS = [
    "bordeaux saint jean",
    "bordeaux st jean",
]

def normalize_text(text):
    if pd.isna(text):
        return ""

    text = str(text).lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = text.replace("/", " ")

    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def resolve_file(base_name):
    """
    Cherche un fichier GTFS dans INPUT_DIR :
    """
    csv_path = INPUT_DIR / f"{base_name}.csv"


    if csv_path.exists():
        return csv_path

    return None


def load_table(base_name, required=False):
    """
    Charge une table GTFS si elle existe.
    """
    path = resolve_file(base_name)
    if path is None:
        if required:
            raise FileNotFoundError(f"Fichier requis introuvable : {base_name}.csv ou {base_name}.txt")
        return None

    print(f"Chargement : {path}")
    return pd.read_csv(path, dtype=str)


def save_table(df, file_name):
    """ 
    Sauvegarde un DataFrame dans OUTPUT_DIR en CSV.
    """
    if df is not None:
        out_path = OUTPUT_DIR / file_name
        df.to_csv(out_path, index=False)
        print(f"Sauvegardé : {out_path} ({len(df)} lignes)")


def _clean_gtfs_table(df, required_columns=None, dedup_subset=None, table_name="table"):
    """
    Nettoyage strict d'une table GTFS:
    - retire les lignes avec valeurs None/NaN/vides sur les colonnes requises
    - retire les doublons
    """
    if df is None:
        return None

    cleaned = df.copy().astype("string")

    # Normalise les chaînes vides / variantes textuelles de null.
    cleaned = cleaned.replace(r"^\s*$", pd.NA, regex=True)
    cleaned = cleaned.replace(
        ["None", "none", "NULL", "null", "NaN", "nan"],
        pd.NA,
    )

    if required_columns:
        present_required = [col for col in required_columns if col in cleaned.columns]
        if present_required:
            before = len(cleaned)
            cleaned = cleaned.dropna(subset=present_required)
            removed = before - len(cleaned)
            if removed > 0:
                print(f"[{table_name}] lignes supprimées (None/vides): {removed}")

    before_dup = len(cleaned)
    if dedup_subset:
        present_subset = [col for col in dedup_subset if col in cleaned.columns]
        cleaned = cleaned.drop_duplicates(subset=present_subset, keep="first")
    else:
        cleaned = cleaned.drop_duplicates(keep="first")
    removed_dup = before_dup - len(cleaned)
    if removed_dup > 0:
        print(f"[{table_name}] doublons supprimés: {removed_dup}")

    return cleaned


def load_gtfs():
    """
    Charge les tables GTFS importantes.
    """
    gtfs = {}
    gtfs["stops"] = load_table("stops", required=True)
    gtfs["stop_times"] = load_table("stop_times", required=True)
    gtfs["trips"] = load_table("trips", required=True)
    gtfs["routes"] = load_table("routes", required=True)
    gtfs["calendar_dates"] = load_table("calendar_dates", required=False)
    gtfs["agency"] = load_table("agency", required=False)
    gtfs["feed_info"] = load_table("feed_info", required=False)
    gtfs["transfers"] = load_table("transfers", required=False)
    return gtfs


def is_saint_jean(stop_name_normalized):
    """
    Vérifie si un arrêt correspond à Bordeaux Saint-Jean.
    """
    for pattern in SAINT_JEAN_PATTERNS:
        if pattern in stop_name_normalized:
            return True
    return False


def matches_allowed_station(stop_name_normalized, allowed_normalized):
    """
    Vérifie si le nom normalisé d'un arrêt correspond à une gare autorisée.
    On accepte :
    - inclusion du nom autorisé dans le nom du stop
    - ou inversement
    """
    for station in allowed_normalized:
        if station in stop_name_normalized or stop_name_normalized in station:
            return True
    return False

def build_allowed_stops(stops_df):
    """
    Construit l'ensemble des stop_id qu'on veut garder.
    On garde :
    - les gares de Bordeaux Métropole listées dans ALLOWED_STATIONS
    - leurs éventuels enfants via parent_station
    On exclut :
    - Bordeaux-Saint-Jean
    """
    stops = stops_df.copy()

    if "stop_name" not in stops.columns:
        raise ValueError("Le fichier stops doit contenir une colonne 'stop_name'")

    stops["stop_name_norm"] = stops["stop_name"].apply(normalize_text)
    allowed_normalized = [normalize_text(x) for x in ALLOWED_STATIONS]
    # Stops principaux retenus
    selected_main = stops[
        stops["stop_name_norm"].apply(
            lambda x: matches_allowed_station(x, allowed_normalized) and not is_saint_jean(x)
        )
    ].copy()

    selected_stop_ids = set(selected_main["stop_id"].dropna())

    # Si parent_station existe, on garde aussi les enfants des gares sélectionnées
    if "parent_station" in stops.columns:
        children = stops[stops["parent_station"].isin(selected_stop_ids)].copy()
        selected_stop_ids.update(children["stop_id"].dropna())

    # on garde aussi le parent pour garder 
    if "parent_station" in stops.columns:
        parents = stops[stops["stop_id"].isin(stops.loc[stops["stop_id"].isin(selected_stop_ids), "parent_station"].dropna())]
        selected_stop_ids.update(parents["stop_id"].dropna())

    selected_stops = stops[stops["stop_id"].isin(selected_stop_ids)].copy()

    # Nettoyage colonne temporaire
    selected_stops = selected_stops.drop(columns=["stop_name_norm"], errors="ignore")
    selected_main_names = selected_main["stop_name"].dropna().unique().tolist()

    return selected_stops, sorted(selected_main_names)


def filter_gtfs(gtfs):
    """
    Filtre le GTFS complet à partir des stops retenus.
    """
    filtered = {}

    stops = gtfs["stops"].copy()
    stop_times = gtfs["stop_times"].copy()
    trips = gtfs["trips"].copy()
    routes = gtfs["routes"].copy()

    # Stops retenus
    kept_stops, kept_station_names = build_allowed_stops(stops)
    kept_stops = _clean_gtfs_table(
        kept_stops,
        required_columns=["stop_id", "stop_name"],
        dedup_subset=["stop_id"],
        table_name="stops",
    )
    kept_stop_ids = set(kept_stops["stop_id"].dropna())

    # Stop times liés à ces stops
    filtered_stop_times = stop_times[stop_times["stop_id"].isin(kept_stop_ids)].copy()
    filtered_stop_times = _clean_gtfs_table(
        filtered_stop_times,
        required_columns=["trip_id", "stop_id"],
        dedup_subset=["trip_id", "stop_id", "stop_sequence"],
        table_name="stop_times",
    )
    kept_trip_ids = set(filtered_stop_times["trip_id"].dropna())

    # Trips liés
    filtered_trips = trips[trips["trip_id"].isin(kept_trip_ids)].copy()
    filtered_trips = _clean_gtfs_table(
        filtered_trips,
        required_columns=["trip_id", "route_id", "service_id"],
        dedup_subset=["trip_id"],
        table_name="trips",
    )
    kept_route_ids = set(filtered_trips["route_id"].dropna()) if "route_id" in filtered_trips.columns else set()
    kept_service_ids = set(filtered_trips["service_id"].dropna()) if "service_id" in filtered_trips.columns else set()
    kept_shape_ids = set(filtered_trips["shape_id"].dropna()) if "shape_id" in filtered_trips.columns else set()

    # Routes liées
    filtered_routes = routes[routes["route_id"].isin(kept_route_ids)].copy() if "route_id" in routes.columns else routes.iloc[0:0].copy()
    filtered_routes = _clean_gtfs_table(
        filtered_routes,
        required_columns=["route_id"],
        dedup_subset=["route_id"],
        table_name="routes",
    )

    # calendar_dates
    calendar_dates = gtfs.get("calendar_dates")
    if calendar_dates is not None and "service_id" in calendar_dates.columns:
        filtered_calendar_dates = calendar_dates[calendar_dates["service_id"].isin(kept_service_ids)].copy()
        filtered["calendar_dates"] = _clean_gtfs_table(
            filtered_calendar_dates,
            required_columns=["service_id", "date", "exception_type"],
            dedup_subset=["service_id", "date", "exception_type"],
            table_name="calendar_dates",
        )
    else:
        filtered["calendar_dates"] = calendar_dates

    # Tables principales
    filtered["stops"] = kept_stops
    filtered["stop_times"] = filtered_stop_times
    filtered["trips"] = filtered_trips
    filtered["routes"] = filtered_routes

    return filtered, kept_station_names

def main_download_filter_bordeaux():
    print("=" * 60)
    print("FILTRAGE GTFS BORDEAUX MÉTROPOLE (SANS SAINT-JEAN)")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gtfs = load_gtfs()
    filtered, kept_station_names = filter_gtfs(gtfs)

    print("\nGares principales gardées :")
    for name in kept_station_names:
        print(f" - {name}")

    print("\nSauvegarde des fichiers filtrés...")
    save_table(filtered["stops"], "stops.csv")
    save_table(filtered["stop_times"], "stop_times.csv")
    save_table(filtered["trips"], "trips.csv")
    save_table(filtered["routes"], "routes.csv")
    save_table(filtered.get("calendar_dates"), "calendar_dates.csv")
    print("\nTerminé.")
    print(f"Données filtrées disponibles dans : {OUTPUT_DIR}")


if __name__ == "__main__":
    main_download_filter_bordeaux()