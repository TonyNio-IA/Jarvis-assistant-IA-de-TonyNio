import sys, os, glob, wave, time, tempfile, shutil, json
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
import jarvis_profils as p, jarvis_locuteur as L
from vosk import Model, SetLogLevel
SetLogLevel(-1)
essai = tempfile.mkdtemp(); shutil.copytree("profils", os.path.join(essai, "profils")); shutil.copy("profils.json", os.path.join(essai, "profils.json"))
p.FICHIER, p.DOSSIER = os.path.join(essai, "profils.json"), os.path.join(essai, "profils")
L._empreintes = None; L._auto = None
L.preparer(Model("vosk-model-small-fr-0.22"))
while not L.disponible(): time.sleep(0.2)
for f in sorted(glob.glob("enregistrements/2026-11-17_14h4*.wav"))[:4]:
    with wave.open(f) as w: o = w.readframes(w.getnframes())
    v = L._vecteur(o)
    print(os.path.basename(f), "->", repr(L.identifier(v[0])))
print("fichiers auto:", [os.path.relpath(x, essai) for x in glob.glob(os.path.join(essai, "profils", "*", "voix_auto.json"))])
L._auto_dernier.clear()
print("oubli:", L.oublier_echantillons(""), os.path.exists(os.path.join(essai, "profils", "_principal", "voix_auto.json")))
shutil.rmtree(essai, ignore_errors=True)
print("vrais fichiers auto:", glob.glob("profils/*/voix_auto.json"))
