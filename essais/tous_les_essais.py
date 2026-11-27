# -*- coding: utf-8 -*-
"""UN SEUL BOUTON : tous les essais de Jarvis, à lancer avant chaque publication.

    python tests\\tous_les_essais.py            -> lance tout, puis ouvre une fenêtre (tableau + bouton Copier)
    python tests\\tous_les_essais.py --sans-fenetre

Rien ne touche la vraie installation :
  - les essais « isolés » (bac à sable, ou dossier provisoire) sont lancés tels quels ;
  - les anciens essais des mises à jour sont lancés dans une copie provisoire de Jarvis (lancer_isole.py) ;
  - les essais qui tapent au clavier, parlent au vrai Claude ou ne sont pas isolés ne sont PAS lancés.
Le programme Python utilisé est celui de Jarvis (python-env), comme chez les utilisateurs.
"""
import glob, json, os, py_compile, re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
PYTHON = os.path.join(RACINE, "python-env", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable
import tempfile
# Les essais n'écrivent JAMAIS dans le vrai journal des rapports (sinon de fausses demandes partent dans le vrai rapport du PC)
JOURNAL_ESSAI = os.path.join(tempfile.mkdtemp(prefix="jarvis-essais-"), "rapports_journal.jsonl")
# Seul essai qui parle exprès au VRAI dépôt Google : il y envoie un rapport, un message et un questionnaire sous un numéro
# de PC tiré au hasard, puis efface tout (« Effacer mes données »). Il garde son propre journal, dans un dossier provisoire.
VRAI_DEPOT = {"essai_rapports.py"}
ISOLE = re.compile(r"bac_a_sable|mkdtemp|TemporaryDirectory")
COPIE = ("essai_maj_bloquee.py", "essai_maj_forcee.py", "essai_maj_testeurs.py", "essai_maj_manquees.py",
         "essai_maj_bouton.py", "essai_bilan_maj.py")                       # lancés dans une copie provisoire
JAMAIS = {"essai_frappe_harnais.py": "tape au clavier",                     # jamais lancés d'ici
          "essai_tablette_reel.py": "parle au vrai Claude (quota)"}
CONNUS = {"essai_local.py": "attend la date du 24/11 écrite en dur, et 3 réponses qui demandent Claude",
          "essai_discussion.py": "vérifie l'ancienne taille du panneau du bas (changée exprès)"}
try:      # anciens essais (non isolés) qui réussissent dans le bac à sable : liste faite par base_anciens_essais.py
    ANCIENS = set(json.load(open(os.path.join(ICI, "anciens_dans_le_bac.json"), encoding="utf-8"))["bons"])
except Exception:
    ANCIENS = set()
ECHEC = re.compile(r"^\s*(?:NON|ÉCHEC|ECHEC|FAIL|KO)\b")
MAUVAIS_BILAN = re.compile(r"IL Y A UN PROBLEME|RESULTAT : ECHEC|[1-9]\d* ÉCHEC|erreurs? ?: ?[1-9]|ECHECS : [1-9]|échecs : [1-9]")


def lancer(commande, delai=420):
    debut = time.time()
    try:
        p = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=delai,
                           cwd=ICI, creationflags=0x08000000,
                           env=(dict(os.environ, PYTHONIOENCODING="utf-8") if os.path.basename(commande[-1]) in VRAI_DEPOT
                                else dict(os.environ, PYTHONIOENCODING="utf-8", JARVIS_JOURNAL_ESSAI=JOURNAL_ESSAI)))
        sortie, code = (p.stdout + "\n" + p.stderr), p.returncode
    except subprocess.TimeoutExpired:
        sortie, code = "", "délai dépassé"
    lignes = [l for l in sortie.splitlines() if l.strip()]
    echecs = [l.strip()[:170] for l in lignes if ECHEC.match(l)]
    trace = [l.strip()[:170] for l in lignes if re.search(r"Traceback|^\w*Error:|^\w+Exception:", l)]
    bilan = next((l.strip() for l in reversed(lignes) if re.search(r"\d+\s*/\s*\d+|réussi|BON|OK|erreurs?|ÉCHEC|ECHEC|PROBLEME", l)), "")
    bon = code == 0 and not echecs and not trace and not MAUVAIS_BILAN.search(bilan)
    return {"bon": bon, "code": code, "bilan": bilan[:110], "echecs": echecs[:6] + trace[:2], "s": round(time.time() - debut)}


def tout():
    resultats = []

    def noter(nom, r, sorte):
        r.update(nom=nom, sorte=sorte)
        if not r["bon"] and nom in CONNUS:
            r["connu"] = CONNUS[nom]
        resultats.append(r)
        print(("OK   " if r["bon"] else "connu" if r.get("connu") else "NON  "), nom, "|", r["bilan"], flush=True)

    # 1. tous les programmes se compilent
    mauvais = []
    for f in sorted(glob.glob(os.path.join(RACINE, "jarvis_*.py"))):
        try:
            py_compile.compile(f, doraise=True, cfile=os.devnull if os.name != "nt" else os.path.join(os.environ["TEMP"], "essai.pyc"))
        except py_compile.PyCompileError as erreur:
            mauvais.append(os.path.basename(f) + " : " + str(erreur)[:120])
    nb = len(glob.glob(os.path.join(RACINE, "jarvis_*.py")))
    noter("compilation", {"bon": not mauvais, "code": 0, "bilan": f"{nb - len(mauvais)} / {nb} programmes se compilent",
                          "echecs": mauvais[:6], "s": 0}, "contrôle")
    # 2. essais
    for f in sorted(glob.glob(os.path.join(ICI, "essai_*.py"))):
        nom = os.path.basename(f)
        if nom in JAMAIS:
            resultats.append({"nom": nom, "sorte": "pas lancé", "bon": None, "bilan": JAMAIS[nom], "echecs": [], "s": 0})
            continue
        source = open(f, encoding="utf-8", errors="ignore").read()
        if nom in ANCIENS and not ISOLE.search(source) and nom not in COPIE:
            noter(nom, lancer([PYTHON, os.path.join(ICI, "lancer_dans_bac.py"), nom]), "ancien, dans le bac à sable")
        elif nom in COPIE:
            noter(nom, lancer([PYTHON, os.path.join(ICI, "lancer_isole.py"), nom]), "copie provisoire")
        elif ISOLE.search(source):
            noter(nom, lancer([PYTHON, f]), "isolé")
        else:
            resultats.append({"nom": nom, "sorte": "pas lancé", "bon": None, "bilan": "pas isolé (ancien essai)", "echecs": [], "s": 0})
    json.dump(resultats, open(os.path.join(ICI, "tous_les_essais.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return resultats


def resume(resultats):
    lances = [r for r in resultats if r["bon"] is not None]
    bons = [r for r in lances if r["bon"]]
    connus = [r for r in lances if not r["bon"] and r.get("connu")]
    mauvais = [r for r in lances if not r["bon"] and not r.get("connu")]
    version = ""
    try:
        version = re.search(r'(?m)^VERSION\s*=\s*"([^"]+)"', open(os.path.join(RACINE, "jarvis_claude.py"), encoding="utf-8").read()).group(1)
    except Exception:
        pass
    lignes = [f"TOUS LES ESSAIS DE JARVIS {version} - {time.strftime('%d/%m/%Y %H:%M')}",
              f"{len(bons)} séries bonnes sur {len(lances)} lancées ; {len(mauvais)} à regarder ; {len(connus)} échec(s) connu(s) et expliqué(s) ; "
              f"{len(resultats) - len(lances)} non lancées (pas isolées).",
              "VERDICT : " + ("RIEN DE CASSÉ, on peut publier." if not mauvais else "NE PAS PUBLIER avant d'avoir regardé les séries ci-dessous."), ""]
    if mauvais:
        lignes.append("À REGARDER")
        for r in mauvais:
            lignes.append(f"- {r['nom']} : {r['bilan']}")
            lignes += ["    " + e for e in r["echecs"]]
        lignes.append("")
    if connus:
        lignes.append("ÉCHECS CONNUS (pas des défauts de Jarvis)")
        lignes += [f"- {r['nom']} : {r['connu']}" for r in connus] + [""]
    lignes.append("SÉRIES BONNES")
    lignes += [f"- {r['nom']} : {r['bilan']}" for r in bons]
    return "\n".join(lignes), mauvais, connus


def fenetre(resultats):
    import tkinter as tk
    texte, mauvais, connus = resume(resultats)
    f = tk.Tk()
    f.title("Jarvis - tous les essais")
    f.geometry(f"{min(1050, f.winfo_screenwidth() - 80)}x{min(760, f.winfo_screenheight() - 120)}+40+40")
    f.minsize(480, 320)
    haut = tk.Frame(f)
    haut.pack(fill="x", padx=8, pady=6)
    couleur = "#2e7d32" if not mauvais else "#c62828"
    tk.Label(haut, text=texte.splitlines()[2], font=("Segoe UI", 12, "bold"), fg=couleur).pack(side="left")

    def copier():
        f.clipboard_clear()
        f.clipboard_append(texte)
        b.config(text="Copié ✓")

    b = tk.Button(haut, text="Copier", font=("Segoe UI", 11, "bold"), bg="#2e7d32", fg="white", command=copier)
    b.pack(side="right")
    zone = tk.Text(f, wrap="word", font=("Consolas", 10), padx=8, pady=6)
    barre = tk.Scrollbar(f, command=zone.yview)
    zone.configure(yscrollcommand=barre.set)
    barre.pack(side="right", fill="y")
    zone.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))
    zone.tag_configure("vert", background="#e3f4e5")
    zone.tag_configure("rouge", background="#fbdcdc")
    zone.tag_configure("orange", background="#fff0d0")
    zone.tag_configure("gris", foreground="#777777")
    zone.insert("end", "\n".join(texte.splitlines()[:3]) + "\n\n")
    for r in sorted(resultats, key=lambda r: (r["bon"] is None, r["bon"] is True, r["nom"])):
        etat, marque = (("BON ", "vert") if r["bon"] else ("non lancé", "gris") if r["bon"] is None
                        else ("connu", "orange") if r.get("connu") else ("À VOIR", "rouge"))
        zone.insert("end", f"{etat:<10}{r['nom']:<38}{r['bilan']}\n", marque)
        for e in ([r.get("connu")] if r.get("connu") else r["echecs"] if r["bon"] is False else []):
            zone.insert("end", f"{'':<10}  {e}\n", marque)
    zone.configure(state="disabled")
    f.mainloop()


if __name__ == "__main__":
    if "--montrer" in sys.argv:                    # rouvre la fenêtre sur les derniers résultats, sans rien relancer
        fenetre(json.load(open(os.path.join(ICI, "tous_les_essais.json"), encoding="utf-8")))
        sys.exit(0)
    res = tout()
    texte, mauvais, connus = resume(res)
    print("\n" + "\n".join(texte.splitlines()[:3]))
    if "--sans-fenetre" not in sys.argv:
        subprocess.Popen([PYTHON.replace("python.exe", "pythonw.exe"), os.path.abspath(__file__), "--montrer"], creationflags=0x08000000)
    sys.exit(1 if mauvais else 0)
