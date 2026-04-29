#!/bin/bash

# =============================================================================
# Script de génération du réseau routier SUMO - Bordeaux Métropole
# Projet : Aide à la décision pour le report modal (SCALE)
# Usage  : ./scripts/generate_network.sh
# =============================================================================

set -e  # Arrêter si une commande échoue

# --- Couleurs pour les messages ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Génération réseau SUMO Bordeaux Métropole${NC}"
echo -e "${GREEN}========================================${NC}"

# --- Répertoire racine du projet ---
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK_DIR="$PROJECT_DIR/network"
OSM_FILE="$PROJECT_DIR/bordeaux_metropole.osm"
PBF_FILE="$PROJECT_DIR/aquitaine-latest.osm.pbf"
NET_FILE="$NETWORK_DIR/network.net.xml"

# --- Vérification des outils ---
echo -e "\n${YELLOW}[1/5] Vérification des outils...${NC}"

if ! command -v sumo &> /dev/null; then
    echo -e "${RED}❌ SUMO n'est pas installé. Lancez : sudo apt install sumo sumo-tools${NC}"
    exit 1
fi

if ! command -v osmium &> /dev/null; then
    echo -e "${RED}❌ osmium n'est pas installé. Lancez : sudo apt install osmium-tool${NC}"
    exit 1
fi

if ! command -v netconvert &> /dev/null; then
    echo -e "${RED}❌ netconvert n'est pas installé. Lancez : sudo apt install sumo sumo-tools${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Tous les outils sont disponibles${NC}"

# --- Créer les dossiers si nécessaire ---
mkdir -p "$NETWORK_DIR"

# --- Étape 1 : Télécharger l'Aquitaine ---
echo -e "\n${YELLOW}[2/5] Téléchargement de l'Aquitaine (Geofabrik)...${NC}"

if [ -f "$PBF_FILE" ]; then
    echo -e "${GREEN}✅ Fichier PBF déjà présent, téléchargement ignoré${NC}"
else
    wget -q --show-progress \
        https://download.geofabrik.de/europe/france/aquitaine-latest.osm.pbf \
        -O "$PBF_FILE"
    echo -e "${GREEN}✅ Téléchargement terminé${NC}"
fi

# --- Étape 2 : Découper Bordeaux Métropole ---
echo -e "\n${YELLOW}[3/5] Découpage de Bordeaux Métropole...${NC}"

# Bounding box officielle Bordeaux Métropole
# min_lon, min_lat, max_lon, max_lat
BBOX="-0.7950,44.7000,-0.3500,45.0500"

if [ -f "$OSM_FILE" ]; then
    echo -e "${GREEN}✅ Fichier OSM déjà présent, découpage ignoré${NC}"
else
    osmium extract \
        --bbox="$BBOX" \
        "$PBF_FILE" \
        -o "$OSM_FILE"
    echo -e "${GREEN}✅ Découpage terminé${NC}"
fi

# --- Étape 3 : Convertir en réseau SUMO ---
echo -e "\n${YELLOW}[4/5] Conversion en réseau SUMO (peut prendre 15-30 min)...${NC}"

netconvert \
    --osm-files "$OSM_FILE" \
    --output-file "$NET_FILE" \
    --geometry.remove \
    --roundabouts.guess \
    --ramps.guess \
    --junctions.join \
    --tls.guess-signals \
    --keep-edges.by-vclass passenger,bus \
    --remove-edges.isolated \
    --no-internal-links \
    2>&1 | grep -v "^Warning"  # Masquer les warnings

echo -e "${GREEN}✅ Réseau généré : $NET_FILE${NC}"

# --- Étape 4 : Vérification ---
echo -e "\n${YELLOW}[5/5] Vérification...${NC}"

if [ -f "$NET_FILE" ]; then
    SIZE=$(ls -lh "$NET_FILE" | awk '{print $5}')
    echo -e "${GREEN}✅ Fichier réseau créé avec succès : $SIZE${NC}"
else
    echo -e "${RED}❌ Erreur : le fichier réseau n'a pas été créé${NC}"
    exit 1
fi

# --- Résumé ---
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ Réseau généré avec succès !${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "📁 Réseau    : $NET_FILE"
echo -e "📦 Taille    : $SIZE"
echo -e "\n${YELLOW}Prochaine étape : générer les routes${NC}"
echo -e "python \$SUMO_HOME/tools/randomTrips.py \\"
echo -e "  -n $NET_FILE \\"
echo -e "  -o $PROJECT_DIR/routes/routes.rou.xml \\"
echo -e "  --begin 0 --end 3600 --period 5 --validate"