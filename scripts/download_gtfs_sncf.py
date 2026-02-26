"""
Ces données contiennent bordeaux
"""
import requests
import zipfile
import os
from pathlib import Path
import pandas as pd
def download_gtfs_sncf():
    print("="*60)
    print("téléchargement gtfs sncf france")
    print("="*60)
    url="https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
    Path("data/gtfs").mkdir(parents=True, exist_ok=True)
    print(f"\n Source: SNCF Open Data")
    print(f"URL: {url}")
    print("Téléchargement ...\n")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    zip_path="data/gtfs_sncf.zip"
    download = 0
    with open(zip_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            download += len(chunk)
            if total_size > 0:
                percent = (download / total_size) * 100
                mb_download = download / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r {percent:.1f}% ({mb_download:.1f}/{mb_total:.1f} MB)", end="")
        print("\n Téléchargement terminé")
    print("\n Décompression..")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall("data/gtfs/")
    os.remove(zip_path)
    print("Fichiers extraits dans data/gtfs/\n")
    required_files = [
    'stops.txt',
    'routes.txt',
    'trips.txt',
    'stop_times.txt',
    'calendar_dates.txt'
    ]
    print("Verification ces fichiers")
    all_ok = True
    for file in required_files:
        path = f"data/gtfs/{file}"
        if os.path.exists(path):
            size = os.path.getsize(path) / (1024*1024)
            print(f"ok file {file:<20} ({size:.1f} MB)")
        else:
            print(f"ko{file:<20} Manquant")
            all_ok = False
    if all_ok:
        print("\n"+"="*60)
        print(" VÉRIFICATION BORDEAUX")
        print("=" * 60)
        stops = pd.read_csv("data/gtfs/stops.txt")
        bordeaux = stops[stops['stop_name'].str.contains('Bordeaux', na=False, case=False)]
        print(f"\n {len(bordeaux)} gares trouvees contenant 'Bordeaux':")
        print(bordeaux[['stop_id', 'stop_name']].head(10).to_string(index=False))
        st_jean = stops[stops['stop_name'].str.contains('Bordeaux-Saint-Jean', na=False, case=False)]
        if len(st_jean) > 0:
            print(f"\n Bordeaux Saint-Jean trouvee:")
            print(f" ID: {st_jean.iloc[0]['stop_id']}")
            print(f" Nom: {st_jean.iloc[0]['stop_name']}")
        print("\n"+"validation" * 30)
        print("GTFS SNCF installe avec succes")
        print("Bordeaux est bien present ")
    return all_ok
if __name__ == "__main__":
   success = download_gtfs_sncf()
   if not success:
       print("\n erreur lors de l'installation")
   else:
       print("\n next step")
       print("   python scripts/download_osm_bordeaux.py")
