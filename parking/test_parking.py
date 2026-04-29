"""
tests/test_parking_service.py
==============================
Tests de récupération des données parking en temps réel.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from parking_servicert import ParkingServiceRT


def test_get_all_parkings():
    """Vérifie que l'API retourne une liste non vide de parkings valides."""
    svc = ParkingServiceRT()
    parkings = svc.get_all_parkings()

    assert len(parkings) > 0, "Aucun parking récupéré — vérifier la connexion ou l'API"

    # Vérifie que chaque parking a les champs obligatoires
    for p in parkings:
        assert "parking_id"   in p, f"Champ 'parking_id' manquant : {p}"
        assert "nom"          in p, f"Champ 'nom' manquant : {p}"
        assert "lat"          in p, f"Champ 'lat' manquant : {p}"
        assert "lon"          in p, f"Champ 'lon' manquant : {p}"
        assert "nb_libre"     in p, f"Champ 'nb_libre' manquant : {p}"
        assert "nb_total"     in p, f"Champ 'nb_total' manquant : {p}"
        assert "ouvert"       in p, f"Champ 'ouvert' manquant : {p}"
        assert isinstance(p["lat"], float), f"'lat' devrait être un float : {p}"
        assert isinstance(p["lon"], float), f"'lon' devrait être un float : {p}"

    print(f"[OK] {len(parkings)} parkings récupérés et valides.")


def test_get_best_parking_for_station():
    """Vérifie que le meilleur parking est trouvé pour une station réelle (Bordeaux St-Jean)."""
    svc = ParkingServiceRT()

    # Gare de Bordeaux Saint-Jean
    station = {
        "id":  "87581009",
        "lat": 44.8259,
        "lon": -0.5561,
    }

    parking = svc.get_best_parking_for_station(station)

    assert parking is not None, (
        "Aucun parking trouvé près de Bordeaux St-Jean — "
        "vérifier max_walk_km ou les données temps réel"
    )
    assert parking["dist_km"] <= svc.max_walk_km, (
        f"Parking trop loin : {parking['dist_km']} km > {svc.max_walk_km} km"
    )
    assert parking["walk_min"] > 0, "walk_min devrait être positif"
    assert parking["ouvert"] is True, "Le parking retourné devrait être ouvert"

    print(
        f"[OK] Meilleur parking : {parking['nom']} "
        f"à {parking['dist_km']} km ({parking['walk_min']} min à pied), "
        f"{parking['nb_libre']} places libres."
    )
    station = {'id': 'StopPoint:OCETrain TER-87582700', 'lat': 44.701059, 'lon': -0.450174}


    station = {'id': 'StopPoint:OCETrain TER-87582700', 'lat': 44.701059, 'lon': -0.450174}


    print("=== Test get_best_parking_for_station ===")
    best = svc.get_best_parking_for_station(station)
    if best:
        print(f"Meilleur parking : {best.get('nom', 'N/A')}")
        print(f"  Distance       : {best.get('dist_km', '?')} km")
        print(f"  Temps de marche: {best.get('walk_min', '?')} min")
        print(f"  Places libres  : {best.get('nb_libre', '?')} / {best.get('nb_total', '?')}")
        print(f"  Ouvert         : {best.get('ouvert', '?')}")
    else:
        print("Aucun parking trouvé dans le rayon max_walk_km =", svc.max_walk_km, "km")

    print("\n=== Test get_walk_time_station_parking ===")
    walk = svc.get_walk_time_station_parking(station)
    print(f"Temps de marche : {walk:.1f} min")

    print("\n=== Test get_parking_availability ===")
    taux, ouvert = svc.get_parking_availability(station)
    print(f"Taux libre : {taux:.0%} | Ouvert : {'Oui' if ouvert else 'Non'}")

    print("\n=== Test get_nearest_parking (sans contrainte rayon) ===")
    nearest = svc.get_nearest_parking(station['lat'], station['lon'])
    if nearest:
        print(f"Parking le plus proche : {nearest.get('nom', 'N/A')}")
        print(f"  Distance             : {nearest.get('dist_km', '?')} km")
    else:
        print("Aucun parking retourné")

    print("\n=== Tous les parkings chargés ===")
    all_p = svc.get_all_parkings()
    print(f"{len(all_p)} parkings au total")



if __name__ == "__main__":
    print("=== Test 1 : récupération de tous les parkings ===")
    test_get_all_parkings()

    print("\n=== Test 2 : meilleur parking pour Bordeaux St-Jean ===")
    test_get_best_parking_for_station()

    print("\n=== Tous les tests sont passés ===")