# GTFS Bordeaux Metropole

## Dataset filtre

Ce dossier contient les donnees GTFS filtrees pour Bordeaux Metropole.

### Zone geographique
- Centre: Bordeaux Saint-Jean (44.8378, -0.5792)
- Rayon: 30 km

### Fichiers inclus
- stops.csv : Gares dans la zone
- stop_times.csv : Horaires des trains
- trips.csv : Voyages
- routes.csv : Lignes
- calendar_dates.csv : Calendrier
- agency.csv : Agences (si disponible)

### Utilisation

```python
from src.gtfs_service import GTFSService

service = GTFSService('data/gtfs_bordeaux')
bordeaux = service.find_station('Bordeaux')
```

### Generation

Dataset genere avec:
```
python scripts/extract_bordeaux_data.py
```

Pour changer le rayon:
```
python scripts/extract_bordeaux_data.py --radius 50
```