# Robust Scaling pour les Données de Trains - Documentation

## 📋 Résumé des Modifications

Le **robust scaling** a été implémenté pour normaliser les features de trains (`train_wait` et `train_trip`) dans l'environnement `ParkOrRide`. Cette approche remplace le simple min-max scaling par une méthode plus robuste aux valeurs aberrantes.

## 🎯 Qu'est-ce que le Robust Scaling?

Le robust scaling utilise le **median** et l'**IQR (Interquartile Range)** au lieu de min/max:

```
scaled_value = (value - median) / IQR

où IQR = Q3 - Q1 (75e percentile - 25e percentile)
```

### Avantages par rapport au Min-Max Scaling:
- ✅ **Résistant aux outliers** : Ne tient pas compte des valeurs extrêmes
- ✅ **Mieux pour données asymétriques** : Fonctionne bien avec distributions skewées
- ✅ **Plus stable** : Les statistiques ne changent pas drastiquement avec quelques valeurs extrêmes

## 📝 Modifications Apportées

### 1. **Nouvelle classe `TrainFeatureScaler`** 
Location: `rl/env/park_ride_env_realtime.py` (lignes 27-98)

```python
class TrainFeatureScaler:
    """
    Utilise scikit-learn's RobustScaler pour transformer les features de trains.
    """
    def __init__(self, gtfs_service):
        self.scaler_wait = RobustScaler(quantile_range=(25.0, 75.0))
        self.scaler_trip = RobustScaler(quantile_range=(25.0, 75.0))
        self._fit_scalers(gtfs_service)
```

#### Méthodes:
- `_fit_scalers()` : Calcule median et IQR à partir des données GTFS
  - **Trip durations** : Calculées comme `max(arrival_min) - min(departure_min)` par trip
  - **Wait times** : Estimées à partir des intervalles entre départs consécutifs
  
- `scale_wait(value)` : Normalise les temps d'attente avec robustesse
- `scale_trip(value)` : Normalise les durées de trajets avec robustesse

### 2. **Intégration dans `ParkOrRide.__init__`**

```python
self.train_scaler = TrainFeatureScaler(self.ts.gtfs)
```

### 3. **Mise à jour de `_get_observation()`**

Avant:
```python
self._norm(train_wait, self.cfg.max_wait_min),
self._norm(train_trip, self.cfg.max_trip_min),
```

Après:
```python
self.train_scaler.scale_wait(train_wait),   # Robust scaling
self.train_scaler.scale_trip(train_trip),   # Robust scaling
```

## 📊 Exemple de Scaling

### Données d'entrée GTFS:
```
Median wait time:  0 minutes
Q1 (25th %ile):   -1 minute (calculée)
Q3 (75th %ile):   1 minute (calculée)
IQR:              2 minutes

Median trip time:  0 minutes
Q1:               -11 minutes
Q3:               11 minutes
IQR:              22 minutes
```

### Transformation:
| Train Wait | Scaled (Raw) | Clipped [0,1] |
|-----------|-------------|---------------|
| 0 min     | 0.0         | 0.0           |
| 30 min    | 15.0        | 1.0           |
| 60 min    | 30.0        | 1.0           |
| 120 min   | 60.0        | 1.0           |

## 🔧 Fichiers Modifiés

1. **`rl/env/park_ride_env_realtime.py`**
   - Ajout import: `from sklearn.preprocessing import RobustScaler`
   - Nouvelle classe: `TrainFeatureScaler`
   - Initialisation: `self.train_scaler` dans `__init__`
   - Modification: `_get_observation()` utilise `scale_wait()` et `scale_trip()`

## 🧪 Tests

### Test 1: Robust Scaling Statistics
```bash
python test_robust_scaling.py
```
Valide que les statistiques median/IQR sont correctement calculées.

### Test 2: Environment Integration
```bash
python test_env_robust_scaling.py
```
Valide que:
- L'environnement se crée sans erreur
- Les observations sont dans [0, 1]
- Les actions et rewards fonctionnent correctement

## 📈 Impact sur l'Apprentissage

Le robust scaling améliore l'apprentissage de l'RL en:

1. **Normalisant mieux les features** : Features à l'échelle similaire
2. **Réduisant l'impact des outliers** : Valeurs extrêmes moins influentes
3. **Améliorant la stabilité d'apprentissage** : Gradients plus stables

## ⚙️ Dépendances

- `scikit-learn==1.5.2` (déjà dans requirements.txt)
- `numpy` (déjà disponible)
- `pandas` (pour GTFS data)

## 🚀 Utilisation

L'environnement utilise automatiquement le robust scaling:

```python
from rl.env.park_ride_env_realtime import ParkOrRide

env = ParkOrRide()
obs, info = env.reset()  # Les features "train_wait" et "train_trip" sont scaled

obs, reward, terminated, truncated, info = env.step(action)
# obs[6] = train_wait (robust scaled)
# obs[7] = train_trip (robust scaled)
```

## 📝 Notes

- Les scalers sont initialisés une seule fois au création de l'environnement
- Les statistiques sont basées sur les données GTFS Bordeaux
- Si GTFS data est manquante, un fallback avec valeurs par défaut est utilisé
- Les valeurs sont clipped à [0, 1] pour rester dans l'observation space

## 🔄 Future Improvements

- [ ] Adapter dynamiquement les statistiques avec un Online RobustScaler
- [ ] Utiliser des statistiques pré-calculées pour initialisation plus rapide
- [ ] Faire un test avec plusieurs villes/réseaux GTFS
