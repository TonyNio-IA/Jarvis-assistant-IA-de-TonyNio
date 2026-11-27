# -*- coding: utf-8 -*-
"""Essai 1.69 : un refus des rapports n'est jamais réactivé ; « Technique » reste le défaut d'une installation neuve.
Tout se passe dans un dossier provisoire (ni les vrais réglages, ni le vrai journal, ni le dépôt)."""
import json
import os
import subprocess
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="jarvis-essai-refus-")
os.environ["JARVIS_JOURNAL_ESSAI"] = os.path.join(TMP, "journal.jsonl")
RACINE = os.environ.get("JARVIS_RACINE", r"C:\Jarvis")
sys.path.insert(0, RACINE)
import jarvis_rapports as jr  # noqa: E402

jr.FICHIER = os.path.join(TMP, "rapports.json")
jr._invite = lambda: False
envois = []
jr._envoyer = lambda d: (envois.append(d), True)[1]
jr._numero_du_pc = lambda: "1" * 32
assert jr.DEPOT.startswith("http://0.0.0.0"), jr.DEPOT

bons = rates = 0


def verifie(nom, ok, detail=""):
    global bons, rates
    if ok:
        bons += 1
        print("  OK   ", nom)
    else:
        rates += 1
        print("  RATÉ ", nom, detail)


def depart(contenu):
    """Simule le premier démarrage d'une version, avec ce rapports.json (None : pas de fichier)."""
    jr._donnees = None
    if os.path.exists(jr.FICHIER):
        os.remove(jr.FICHIER)
    if contenu is not None:
        with open(jr.FICHIER, "w", encoding="utf-8") as f:
            json.dump(contenu, f)
    jr._lire()
    with open(jr.FICHIER, encoding="utf-8") as f:
        return json.load(f)


print("--- 1. Mise à jour : le réglage déjà choisi est gardé")
vieux = time.time() - 30 * 86400
cas = [
    ("PC en 1.64 qui avait refusé (« Rien »)", {"id": "a" * 32, "niveau": "aucun", "refuse_le": vieux}, "aucun"),
    ("PC en 1.47 qui avait refusé, sans date", {"id": "a" * 32, "niveau": "aucun"}, "aucun"),
    ("refus après la 1.65", {"id": "a" * 32, "niveau": "aucun", "bascule_165": True, "refuse_le": vieux}, "aucun"),
    ("refus et rappel déjà fait", {"id": "a" * 32, "niveau": "aucun", "refuse_le": vieux, "rappel_fait": True}, "aucun"),
    ("« Complet » choisi", {"id": "a" * 32, "niveau": "complet"}, "complet"),
    ("« Technique » choisi", {"id": "a" * 32, "niveau": "technique", "choisi_le": vieux}, "technique"),
]
for nom, contenu, attendu in cas:
    d = depart(contenu)
    verifie(f"{nom} -> {attendu}", d.get("niveau") == attendu, str(d))
d = depart({"id": "a" * 32, "niveau": "aucun", "refuse_le": vieux})
verifie("le refus garde sa date (le rappel unique reste possible, jamais un changement)", d.get("refuse_le") == vieux, str(d))
verifie("le refus n'est pas marqué « par défaut »", not d.get("par_defaut"), str(d))

print("--- 2. Installation neuve : « Technique » par défaut, comme avant")
d = depart(None)
verifie("pas de fichier -> Technique par défaut", d.get("niveau") == "technique" and d.get("par_defaut") is True, str(d))
d = depart({"id": "a" * 32, "niveau": None})
verifie("1.64 jamais interrogé -> Technique par défaut", d.get("niveau") == "technique" and d.get("par_defaut") is True, str(d))
verifie("la fenêtre d'accord reste à montrer une fois", jr.a_demander() is True)

print("--- 3. Avec un refus, rien ne part")
depart({"id": "a" * 32, "niveau": "aucun", "refuse_le": vieux, "rappel_fait": True})
jr.noter("incompris", texte="essai", raison="trop court")
jr.ecoute_bloc(4000, 0.3)
jr._ecoute["depuis"] = time.time() - 4000
jr._vider_ecoute()
verifie("aucun événement écrit dans le journal", not os.path.exists(jr.JOURNAL) or os.path.getsize(jr.JOURNAL) == 0)
verifie("aucun rapport envoyé, même forcé", jr.envoyer_rapport(force=True) is False and not envois)
d = depart({"id": "a" * 32, "niveau": "aucun", "compteur": False})
verifie("compteur coupé : reste coupé après la mise à jour", d.get("compteur") is False, str(d))
jr._signal()
verifie("compteur coupé : aucun signal envoyé", not envois, str(envois))

print("--- 4. Réinstallation avec reprise des fichiers (case « rapport technique » cochée d'office)")
# la partie PowerShell de l'installateur publié (tout ce qui suit la marque dans Installer-Jarvis.bat)
with open(os.path.join(RACINE, "installateur", "Installer-Jarvis.bat"), "rb") as f:
    _lot = f.read()
corps = os.path.join(TMP, "corps.ps1")
with open(corps, "wb") as f:
    f.write(_lot[_lot.index(b"#==JARVIS-POWERSHELL==#"):])
script = r'''
$ErrorActionPreference = 'Stop'
$texte = [IO.File]::ReadAllText('%s', [Text.Encoding]::UTF8)
$f = $null; $j = $null
$arbre = [Management.Automation.Language.Parser]::ParseInput($texte, [ref]$j, [ref]$f)
foreach ($fn in $arbre.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    if ($fn.Name -eq 'Ecrire-Rapport') { Invoke-Expression $fn.Extent.Text }
}
function Bon($t) { } ; function Attention($t) { }
$UTF8 = New-Object Text.UTF8Encoding $false
Ecrire-Rapport $args[0] $args[1]
''' % corps.replace("'", "''")
fichier_ps = os.path.join(TMP, "ecrire_rapport.ps1")
with open(fichier_ps, "w", encoding="utf-8-sig") as f:
    f.write(script)


def installe(contenu, choix):
    dossier = tempfile.mkdtemp(dir=TMP)
    if contenu is not None:
        with open(os.path.join(dossier, "rapports.json"), "w", encoding="utf-8") as f:
            json.dump(contenu, f)
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", fichier_ps, dossier, choix],
                       capture_output=True, text=True, timeout=60)
    if p.returncode:
        return {"erreur": p.stderr[-300:]}
    with open(os.path.join(dossier, "rapports.json"), encoding="utf-8-sig") as f:
        return json.load(f)


cas = [
    ("refus repris + case cochée -> reste « Rien »", {"niveau": "aucun", "refuse_le": vieux}, "technique", "aucun"),
    ("refus repris + case décochée -> « Rien »", {"niveau": "aucun", "refuse_le": vieux}, "aucun", "aucun"),
    ("« Complet » repris + case cochée -> « Complet »", {"niveau": "complet"}, "technique", "complet"),
    ("« Technique » repris + case décochée -> « Rien »", {"niveau": "technique"}, "aucun", "aucun"),
    ("installation neuve + case cochée -> « Technique »", None, "technique", "technique"),
    ("installation neuve + case décochée -> « Rien »", None, "aucun", "aucun"),
]
for nom, contenu, choix, attendu in cas:
    d = installe(contenu, choix)
    verifie(nom, d.get("niveau") == attendu, str(d))
d = installe({"niveau": "aucun", "refuse_le": vieux, "id": "b" * 32}, "technique")
verifie("refus repris : le fichier n'est pas modifié du tout", d == {"niveau": "aucun", "refuse_le": vieux, "id": "b" * 32}, str(d))

print("--- 5. Le code ne contient plus de bascule vers « Technique »")
source = open(os.path.join(RACINE, "jarvis_rapports.py"), encoding="utf-8").read()
verifie("plus de passage de « Rien » à « Technique » au démarrage",
        'passé de « Rien » à « Technique »' not in source and source.count('_donnees["niveau"] = "technique"') == 1)

print()
print(f"RÉSULTAT : {bons} bons, {rates} ratés")
sys.exit(1 if rates else 0)
