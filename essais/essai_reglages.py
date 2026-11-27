import sys, os, json, tempfile, shutil, hashlib, zipfile, socket
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
socket.socket.bind = lambda *a, **k: None; socket.socket.listen = lambda *a, **k: None
def h(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:10] if os.path.exists(p) else None
perso = ("memoire.json", "notes.txt", "profils.json", "reglages_voix.json", "apparence.json", "preferences.json", "rappels.json")
avant = {f: h(f) for f in perso}
import jarvis_reacteur, jarvis_affichage as A, jarvis_voix as V, jarvis_vigilance as VG, jarvis_claude as C, jarvis_config as cfg
import jarvis_reglages_ui as R, jarvis_extras as X
essai = tempfile.mkdtemp(prefix="jarvis_reglages_")
R.FICHIER = os.path.join(essai, "preferences.json")
X.FICHIER_APPARENCE = os.path.join(essai, "apparence.json")
V._enregistrer_reglages = lambda: None
R.charger()
print("defauts:", {k: R.DEFAUTS[k] for k in ("vitesse_reflet", "volume_bip", "alertes", "niveau_alertes", "taille")})
R.regler("vitesse_reflet", 250); R.regler("volume_bip", 0.3); R.regler("alertes", False); R.regler("niveau_alertes", 3)
R.regler("micro", "bruyante"); R.regler("reveil", "prudente"); R.regler("nuit_auto", "22 h à 7 h"); R.regler("jauges", ["CPU", "TMP"])
print("en direct:", A.VITESSE_REFLET, V.VOLUME_BIP, VG.ACTIVE, VG.NIVEAU_MIN, C.SEUIL_SON_MIN, C.PAUSE_LONGUE_AVANT_JARVIS, cfg.HEURES_NUIT, A.JAUGES)
print("fichier:", json.load(open(R.FICHIER, encoding="utf-8")))
X.choisir_couleur("océan"); print("theme:", jarvis_reacteur.COULEURS_VEILLE)
R.demarrage_windows = lambda actif: True        # pas de changement du vrai démarrage pendant l'essai
apparence_vraie = cfg.chemin("apparence.json")
R.par_defaut.__globals__["jarvis_config"] = cfg
orig = R.FICHIER
vrai_chemin = cfg.chemin                        # par_defaut() efface apparence.json : jamais le vrai
cfg.chemin = lambda *m: os.path.join(essai, *m) if m == ("apparence.json",) else vrai_chemin(*m)
try:
    R.par_defaut()
finally:
    cfg.chemin = vrai_chemin
print("par defaut:", A.VITESSE_REFLET, V.VOLUME_BIP, VG.ACTIVE, VG.NIVEAU_MIN, C.SEUIL_SON_MIN, C.PAUSE_LONGUE_AVANT_JARVIS, cfg.HEURES_NUIT, A.JAUGES, jarvis_reacteur.COULEURS_VEILLE)
print("preferences effacé:", not os.path.exists(R.FICHIER))
# sauvegarde et restauration dans un dossier d'essai
dossier_vrai = cfg.DOSSIER
faux = os.path.join(essai, "jarvis"); os.makedirs(os.path.join(faux, "profils", "x"))
for f in ("memoire.json", "profils.json"): open(os.path.join(faux, f), "w").write('{"essai": 1}')
open(os.path.join(faux, "profils", "x", "voix.json"), "w").write("[]")
cfg.DOSSIER = faux; R.DOSSIER_SAUVEGARDES = os.path.join(essai, "sauvegardes")
z = R.sauvegarder(); print("sauvegarde:", sorted(zipfile.ZipFile(z).namelist()))
os.remove(os.path.join(faux, "memoire.json"))
mauvais = os.path.join(essai, "mauvais.zip")
with zipfile.ZipFile(mauvais, "w") as m:
    m.writestr("memoire.json", "{}"); m.writestr("jarvis_claude.py", "piege"); m.writestr("../dehors.txt", "piege")
print("restaure:", R.restaurer(z), "| piege:", R.restaurer(mauvais), os.path.exists(os.path.join(faux, "jarvis_claude.py")), os.path.exists(os.path.join(essai, "dehors.txt")))
cfg.DOSSIER = dossier_vrai
print("aide:", len(R.AIDE), "| historique:", len(R.historique()), R.historique(2)[:1])
import jarvis_commandes as K
R.ouvrir = lambda: print("   (fenetre ouverte)")
for q in ["ouvre les réglages", "ouvre tes paramètres", "ouvre les paramètres", "ouvre les réglages de jarvis"]:
    print(repr(q), "->", repr(R.commande(q)))
shutil.rmtree(essai, ignore_errors=True)
print("fichiers personnels intacts:", avant == {f: h(f) for f in perso})
