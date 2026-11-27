import sys, os, glob, hashlib, py_compile, tempfile, shutil
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
def h(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:10] if os.path.exists(p) else None
perso = ("memoire.json", "notes.txt", "enfant.json", "liste.json", "rappels.json", "profils.json", "reglages_voix.json", "ville.txt")
avant = {f: h(f) for f in perso}
erreurs = 0
for f in sorted(glob.glob("jarvis_*.py")):
    try: py_compile.compile(f, doraise=True)
    except Exception as e: erreurs += 1; print("COMPILE", f, e)
print("compilation:", len(glob.glob("jarvis_*.py")), "fichiers,", erreurs, "erreur(s)")
import jarvis_commandes as c, jarvis_voix as v
essai = tempfile.mkdtemp(); c.FICHIER_RAPPELS = os.path.join(essai, "r.json")
v.forcer_nuit = lambda val: None
attendus = [
 ("quelle heure est-il", "Il est"), ("quel temps fait-il", "il fait"), ("combien font 15 % de 80", "12"),
 ("3 miles en kilomètres", "kilomètre"), ("quelle heure est-il à Tokyo", "Tokyo"), ("y a-t-il une alerte météo", "vigilance"),
 ("minuteur pâtes 10 minutes", "pâtes"), ("lance un chrono", "chrono"), ("arrête le chrono", ""),
 ("quels sont les profils", "TonyNio"), ("qui suis-je", "TonyNio"), ("qu'est-ce que tu sais faire", "minuteur"),
 ("est-ce que le mode nuit est activé", "mode nuit"), ("quelle est ta version", "version 1."),
]
for q, att in attendus:
    try: r = c.commande_instantanee([q]) or ""
    except Exception as e: r = "ERREUR " + repr(e)
    ok = att.lower() in r.lower() if att else bool(r)
    erreurs += not ok
    print("OK " if ok else "KO ", repr(q), "->", r[:110])
shutil.rmtree(essai, ignore_errors=True)
intacts = avant == {f: h(f) for f in perso}
print("fichiers personnels intacts:", intacts, "| erreurs:", erreurs)
