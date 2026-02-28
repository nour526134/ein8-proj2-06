"""
Renomme tous les .txt en .csv dans data/gtfs/
"""
from pathlib import Path

gtfs_dir = Path("data/gtfs")

print("=" * 60)
print(" RENOMMAGE .txt → .csv")
print("=" * 60)

txt_files = list(gtfs_dir.glob("*.txt"))

if len(txt_files) == 0:
    print("\n Aucun fichier .txt trouvé")
else:
    print(f"\n {len(txt_files)} fichiers trouvés\n")
    
    for txt_file in sorted(txt_files):
        csv_file = txt_file.with_suffix('.csv')
        txt_file.rename(csv_file)
        print(f"   ✅ {txt_file.name} → {csv_file.name}")
    
    print(f"\n Renommage terminé !")
    
    # Vérification
    print(f"\n Fichiers CSV disponibles:")
    for csv_file in sorted(gtfs_dir.glob("*.csv")):
        print(f"    {csv_file.name}")
