"""
Script de génération du profil de trafic horaire Bordeaux Métropole.
Source : Open Data Bordeaux Métropole (ODS API v2.1, sans clé)
Dataset : comptage-du-trafic-2023-bordeaux-metropole
         → colonnes hpm (heure pointe matin), hps (heure pointe soir), tmjo (trafic moyen journalier)

Usage :
    python scripts/build_traffic_profile.py
Sortie :
    data/traffic/bordeaux_profile.json
"""

import requests
import json
import numpy as np
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

ODS_BASE = "https://opendata.bordeaux-metropole.fr/api/explore/v2.1"
DATASET  = "comptage-du-trafic-2023-bordeaux-metropole"
OUTPUT   = Path("data/traffic/bordeaux_profile.json")

# ── 1. Télécharger tous les records du dataset ─────────────────────────────────

def fetch_all_records():
    records = []
    limit   = 100
    offset  = 0

    while True:
        url = (
            f"{ODS_BASE}/catalog/datasets/{DATASET}/records"
            f"?limit={limit}&offset={offset}"
        )
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()

        batch = data.get("results", [])
        records.extend(batch)
        print(f"  Récupérés : {len(records)} / {data.get('total_count', '?')}")

        if len(batch) < limit:
            break
        offset += limit

    return records

# ── 2. Construire le profil horaire ───────────────────────────────────────────

def build_profile(records):
    """
    Le dataset contient :
      - hpm  : débit à l'heure de pointe matin  (~8h)
      - hps  : débit à l'heure de pointe soir   (~17h)
      - tmjo : trafic moyen journalier ouvré

    On reconstruit un profil 24h en interpolant depuis ces 3 points
    et en appliquant une forme réaliste connue du trafic urbain bordelais.
    """
    hpm_vals  = []
    hps_vals  = []
    tmjo_vals = []

    for rec in records:
        try:
            hpm  = float(rec.get("hpm_val")  or 0)
            hps  = float(rec.get("hps_val")  or 0)
            tmjo = float(rec.get("mjo_val")  or 0)
            if hpm > 0 and hps > 0 and tmjo > 0:
                hpm_vals.append(hpm)
                hps_vals.append(hps)
                tmjo_vals.append(tmjo)
        except (ValueError, TypeError):
            continue

    if not hpm_vals:
        print("[WARN] Aucune donnée valide trouvée, utilisation du profil TomTom de secours.")
        return None

    hpm_mean  = float(np.median(hpm_vals))
    hps_mean  = float(np.median(hps_vals))
    tmjo_mean = float(np.median(tmjo_vals))

    print(f"\nDébits médians :")
    print(f"  HPM  (pointe matin ~8h)  : {hpm_mean:.0f} véh/h")
    print(f"  HPS  (pointe soir  ~17h) : {hps_mean:.0f} véh/h")
    print(f"  TMJO (volume journalier) : {tmjo_mean:.0f} véh/jour")

    # TMJO est un volume journalier (véh/jour), HPM/HPS sont horaires (véh/h)
    # On ramène TMJO à un débit horaire sur 16h de circulation active
    tmjo_horaire = tmjo_mean / 16.0
    print(f"  TMJO horaire (~TMJO/16h) : {tmjo_horaire:.0f} véh/h")
    ratio_matin = hpm_mean / tmjo_horaire
    ratio_soir  = hps_mean / tmjo_horaire
    print(f"  Ratio HPM / moy horaire  : {ratio_matin:.2f}")
    print(f"  Ratio HPS / moy horaire  : {ratio_soir:.2f}")

    # Profil horaire de forme (poids relatifs par heure)
    # Basé sur la forme typique d'une ville française (INSEE mobilité)
    # puis re-scalé par les vrais ratios HPM/HPS du dataset
    SHAPE = [
        0.05, 0.04, 0.04, 0.04, 0.06, 0.12,   # 0h-5h
        0.35, 0.75, 1.00, 0.85, 0.55, 0.48,   # 6h-11h  (pic matin = 1.0 à 8h)
        0.52, 0.56, 0.50, 0.55, 0.72, 1.00,   # 12h-17h (pic soir  = 1.0 à 17h)
        0.90, 0.72, 0.50, 0.32, 0.18, 0.09,   # 18h-23h
    ]

    # Scaler les pics selon les vrais ratios mesurés
    # heure 8  → ratio_matin
    # heure 17 → ratio_soir
    # base     → 1.0 dans SHAPE correspond au pic
    # on veut que pic matin donne ratio_matin et pic soir donne ratio_soir
    # donc on construit deux zones et on interpole

    profile = []
    for h, shape_val in enumerate(SHAPE):
        if h <= 12:
            # Zone matin : on scale par rapport au pic matin
            sat = shape_val * ratio_matin * 0.65
        else:
            # Zone soir : on scale par rapport au pic soir
            sat = shape_val * ratio_soir * 0.65

        # Clamp entre 0.04 (nuit) et 0.95 (embouteillage total)
        sat = max(0.04, min(0.95, sat))
        profile.append(round(sat, 2))

    return profile

# ── 3. Affichage ──────────────────────────────────────────────────────────────

def display_profile(profile):
    print("\nPROFIL TRAFIC BORDEAUX GÉNÉRÉ :")
    print("-" * 50)
    for h, v in enumerate(profile):
        bar = "█" * int(v * 35)
        print(f"  {h:02d}h : {v:.2f}  {bar}")
    print("-" * 50)
    print(f"\nBORDEAUX_TRAFFIC_PROFILE = {profile}")

# ── 4. Sauvegarde ─────────────────────────────────────────────────────────────

FALLBACK_PROFILE = [
    0.05, 0.05, 0.05, 0.05, 0.06, 0.10,
    0.25, 0.55, 0.80, 0.70, 0.45, 0.38,
    0.42, 0.45, 0.38, 0.40, 0.55, 0.82,
    0.78, 0.60, 0.40, 0.25, 0.15, 0.08,
]

def main():
    print(f"Téléchargement du dataset : {DATASET}")
    print(f"Source : {ODS_BASE}\n")

    try:
        records = fetch_all_records()
        print(f"\n{len(records)} capteurs chargés.")
    except Exception as e:
        print(f"[ERREUR] Impossible de contacter l'API ODS : {e}")
        print("Utilisation du profil TomTom de secours.")
        profile = FALLBACK_PROFILE
    else:
        profile = build_profile(records)
        if profile is None:
            profile = FALLBACK_PROFILE

    display_profile(profile)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"\nSauvegardé → {OUTPUT}")
    print("Tu peux maintenant lancer l'entraînement, le profil sera chargé automatiquement.")

if __name__ == "__main__":
    main()