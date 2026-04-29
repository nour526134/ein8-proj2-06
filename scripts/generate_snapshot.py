# parking/build_static_snapshot.py
"""
Lance ce script une fois pour générer data/parkings_static.csv
python parking/build_static_snapshot.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import csv
from parking.parking_utils import fetch_parkings, parse_parking

def generate_snapshot():
    OUTPUT = "data/parkings_static.csv"
    os.makedirs("data", exist_ok=True)

    records = fetch_parkings()
    parkings = [p for p in (parse_parking(r) for r in records) if p]

    # Filtrer les parkings avec nb_total=0
    parkings = [p for p in parkings if p.get("nb_total", 0) > 0]

    # Dédoublonner par parking_id (garde la première occurrence)
    seen_ids = set()
    unique_parkings = []
    for p in parkings:
        pid = p["parking_id"]
        if pid not in seen_ids:
            seen_ids.add(pid)
            unique_parkings.append(p)
    parkings = unique_parkings

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["parking_id", "nom", "lat", "lon", "nb_total", "gestionnaire"])
        writer.writeheader()
        for p in parkings:
            # Ignorer les lignes où les champs essentiels sont vides
            if not p.get("parking_id") or not p.get("nom") or p.get("lat") is None or p.get("lon") is None:
                continue
            writer.writerow({
                "parking_id":   p["parking_id"],
                "nom":          p["nom"],
                "lat":          p["lat"],
                "lon":          p["lon"],
                "nb_total":     p["nb_total"],
                "gestionnaire": p["gestionnaire"],
            })

    print(f"{len(parkings)} parkings sauvegardés dans {OUTPUT}") 