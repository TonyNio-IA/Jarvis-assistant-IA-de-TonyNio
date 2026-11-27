import sys, os, glob, wave, time, tempfile, shutil, json
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
import jarvis_profils as p, jarvis_locuteur as L, jarvis_commandes as c
from vosk import Model, SetLogLevel
SetLogLevel(-1)
essai = tempfile.mkdtemp(); shutil.copy("profils.json", os.path.join(essai, "profils.json"))
p.FICHIER, p.DOSSIER = os.path.join(essai, "profils.json"), os.path.join(essai, "profils")
L._empreintes = None
L.preparer(Model("vosk-model-small-fr-0.22"))
while not L.disponible(): time.sleep(0.2)
print("commande:", L.commande("apprends ma voix"))
print("guide demande:", L.guide_demande(), "| deuxieme fois:", L.guide_demande())
print("phrases:", L.phrases_guide("Léo")[:2])
fichiers = sorted(glob.glob("enregistrements/2026-11-17_14h4*.wav"))[:6]
for f in fichiers:
    with wave.open(f) as w: o = w.readframes(w.getnframes())
    L.analyser(o, "")
    print(os.path.basename(f), "retenue:", L.apprendre_phrase())
print("fin:", L.terminer_guide("Léo"), "| empreinte enregistree:", os.path.exists(os.path.join(p.DOSSIER, "_principal", "voix.json")))
shutil.rmtree(essai, ignore_errors=True)
