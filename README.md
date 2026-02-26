# ein8-proj2-06




## Scripts utiles

### Installation automatique 

```bash
./scripts/setup.sh
```

Ce script cree le venv si besoin et installe les dependances.

### Nettoyage des donnees/cache

```bash
./scripts/clean.sh
```

Pour nettoyer sans confirmation:

```bash
./scripts/clean.sh --yes
```

## Telecharger les donnees gtfs avec les deux scripts 
./scripts/download_gtfs_sncf.py
./scripts/download_osm_bordeaux.py