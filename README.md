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


## 🗺️ Génération du réseau SUMO

Le fichier `network.net.xml` est trop lourd pour Git (206MB).
Chacun doit le regénérer localement :
````bash
./scripts/generate_network.sh
````

## 🚗 Lancer la simulation
````bash
# Sans interface
cd simu
sumo -c confing/simu.sumocfg
"les fichiers output/summary.xml output/tripinfo.xml vont etre générés"

# Avec interface graphique
sumo-gui -c confing/simu.sumocfg
````

## Démarrer l'API en local

```bash
source venv/bin/activate && \
lsof -ti:8000 | xargs -r kill -9 && \
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Démarrer l'ui version linux

```bash
cd ui && \
flutter run -d linux
```

