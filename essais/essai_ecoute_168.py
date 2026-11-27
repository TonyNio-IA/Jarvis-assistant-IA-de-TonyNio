# -*- coding: utf-8 -*-
"""Essai 1.68 : le bloc « ecoute » des rapports (le micro capte-t-il ? « Jarvis » est-il reconnu ?).
Tout se passe dans un dossier provisoire : ni le vrai journal, ni les vrais réglages, ni le dépôt Google."""
import json
import os
import re
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="jarvis-essai-ecoute-")
os.environ["JARVIS_JOURNAL_ESSAI"] = os.path.join(TMP, "journal.jsonl")
sys.path.insert(0, r"C:\Jarvis")
import jarvis_rapports as jr  # noqa: E402

jr.JOURNAL = os.path.join(TMP, "journal.jsonl")
jr.FICHIER = os.path.join(TMP, "rapports.json")
jr._donnees = {"id": "0" * 32, "niveau": "technique", "bascule_165": True, "compteur": True, "testeur": False,
               "premier_lancement": time.time()}
jr._invite = lambda: False
envois = []
jr._envoyer = lambda d: (envois.append(d), True)[1]
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


def remise_a_zero(niveau="technique"):
    for f in (jr.JOURNAL,):
        if os.path.exists(f):
            os.remove(f)
    jr._ecoute.clear()
    jr._ecoute.update(niveau_max=0.0, depuis=time.time())
    jr._donnees["niveau"] = niveau
    jr._donnees.pop("dernier_rapport", None)
    jr._donnees.pop("dernier_rapport_envoye", None)
    envois.clear()


def heure(secondes=3600, niveau=0.0, son=0, coupe=0, **compteurs):
    """Simule une heure de veille puis le passage des compteurs dans le journal."""
    jr.ecoute_bloc(secondes - son, niveau if niveau < jr.SEUIL_SON_ECOUTE else 0.005)
    if son:
        jr.ecoute_bloc(son, niveau)
    if coupe:
        jr.ecoute_bloc(coupe, 0.3, True)
    for k, n in compteurs.items():
        jr.ecoute(k, n)
    return jr._vider_ecoute(force=True)


def bilan():
    return jr.construire_rapport()[0]["ecoute"]


print("--- 1. Les verdicts")
cas = [
    ("micro muet", dict(niveau=0.0005), "micro muet : aucun son reçu"),
    ("micro en marche, pièce silencieuse", dict(niveau=0.006), "micro en marche, personne n'a parlé"),
    ("du bruit mais aucune parole", dict(niveau=0.2, son=120), "du son, mais aucune parole reconnue"),
    ("des paroles, jamais Jarvis", dict(niveau=0.3, son=300, phrase=12), "des paroles, mais jamais « Jarvis »"),
    ("Jarvis presque entendu", dict(niveau=0.3, son=300, phrase=12, presque_jarvis=3),
     "des paroles, « Jarvis » presque entendu mais jamais confirmé"),
    ("Jarvis détecté", dict(niveau=0.4, son=300, phrase=20, jarvis=4, presque_jarvis=1), "« Jarvis » détecté"),
    ("aucun micro", dict(secondes=0, sans_micro=1), "aucun micro trouvé"),
    ("micro coupé dans Jarvis", dict(secondes=0, coupe=3600), "micro coupé dans Jarvis"),
    ("presque pas d'écoute", dict(secondes=20, niveau=0.3, son=10), "presque pas d'écoute"),
]
for nom, reglages, attendu in cas:
    remise_a_zero()
    heure(**reglages)
    b = bilan()
    verifie(f"{nom} -> « {attendu} »", b.get("etat") == attendu, f"(reçu : {b})")

print("--- 2. Les compteurs")
remise_a_zero()
heure(niveau=0.25, son=600, phrase=7, jarvis=2)
heure(niveau=0.41, son=60, phrase=3, presque_jarvis=1, coupe=1800)
b = bilan()
verifie("deux heures additionnées : 2 périodes", b.get("periodes") == 2, str(b))
verifie("durée d'écoute : 2 h", b.get("ecoute_h") == 2.0, str(b))
verifie("micro coupé : 0,5 h", b.get("micro_coupe_h") == 0.5, str(b))
verifie("minutes avec du son : 11", b.get("avec_son_min") == 11.0, str(b))
verifie("niveau maximum : le plus fort des deux heures", b.get("niveau_max") == 0.41, str(b))
verifie("phrases entendues : 10", b.get("phrases_entendues") == 10, str(b))
verifie("« Jarvis » détecté : 2", b.get("jarvis_detecte") == 2, str(b))
verifie("« Jarvis » presque : 1", b.get("jarvis_presque") == 1, str(b))
verifie("après le passage au journal, les compteurs repartent de zéro",
        not any(jr._ecoute.get(k) for k in jr._CLES_ECOUTE) and jr._ecoute["niveau_max"] == 0.0)
remise_a_zero()
verifie("rien d'écouté : aucun événement écrit", jr._vider_ecoute(force=True) is False and not os.path.exists(jr.JOURNAL))
verifie("rien d'écouté : bloc « ecoute » vide dans le rapport", bilan() == {})
jr.ecoute_bloc(10, 0.1)
verifie("moins d'une heure : les compteurs attendent", jr._vider_ecoute() is False and not os.path.exists(jr.JOURNAL))
jr._ecoute["depuis"] = time.time() - 3601
verifie("une heure passée : les compteurs partent au journal", jr._vider_ecoute() is True)
jr.ecoute("n_importe_quoi")
verifie("un compteur inconnu est ignoré", "n_importe_quoi" not in jr._ecoute)

print("--- 3. Rien de personnel")
remise_a_zero()
heure(niveau=0.3, son=200, phrase=5, jarvis=1)
lignes = [json.loads(x) for x in open(jr.JOURNAL, encoding="utf-8")]
permis = set(jr._CLES_ECOUTE) | {"niveau_max", "genre", "t", "version"}
verifie("l'événement ne contient que des compteurs", len(lignes) == 1 and set(lignes[0]) <= permis, str(lignes))
verifie("aucun texte dans les valeurs (hors genre et version)",
        all(isinstance(v, (int, float)) for k, v in lignes[0].items() if k not in ("genre", "version")), str(lignes))
remise_a_zero("aucun")
heure(niveau=0.3, son=200, phrase=5)
verifie("rapports refusés (« Rien ») : rien n'est écrit", not os.path.exists(jr.JOURNAL))

print("--- 4. L'envoi : un PC où personne ne parle envoie quand même son bilan, une fois par jour")
remise_a_zero()
heure(niveau=0.0005)
verifie("premier bilan d'écoute seul : envoyé", jr.envoyer_rapport() is True and len(envois) == 1)
verifie("le rapport envoyé contient le verdict", envois and envois[-1]["ecoute"].get("etat") == "micro muet : aucun son reçu")
verifie("le journal est vidé après l'envoi", not os.path.exists(jr.JOURNAL) or os.path.getsize(jr.JOURNAL) == 0)
jr._donnees["dernier_rapport"] = time.time() - 3700                 # une heure plus tard
heure(niveau=0.0005)
verifie("une heure après, encore rien d'autre : pas de nouvel envoi", jr.envoyer_rapport() is False and len(envois) == 1)
verifie("... et les compteurs restent en attente dans le journal", os.path.getsize(jr.JOURNAL) > 0)
jr.noter("incompris", texte="essai", raison="trop court")
verifie("dès qu'il y a autre chose : envoyé, avec l'écoute", jr.envoyer_rapport() is True and len(envois) == 2
        and envois[-1]["ecoute"].get("periodes") == 1)
jr._donnees["dernier_rapport"] = time.time() - 3700
jr._donnees["dernier_rapport_envoye"] = time.time() - 25 * 3600     # un jour plus tard
heure(niveau=0.0005)
verifie("un jour après : le bilan d'écoute seul repart", jr.envoyer_rapport() is True and len(envois) == 3)
remise_a_zero()
jr._envoyer = lambda d: False
heure(niveau=0.0005)
verifie("envoi raté : pas compté comme envoyé", jr.envoyer_rapport() is False and "dernier_rapport_envoye" not in jr._donnees)
verifie("envoi raté : les compteurs sont gardés", os.path.getsize(jr.JOURNAL) > 0)
jr._envoyer = lambda d: (envois.append(d), True)[1]
remise_a_zero()
jr.noter("incompris", texte="essai", raison="trop court")
verifie("un rapport sans écoute part comme avant", jr.envoyer_rapport() is True and envois[-1]["ecoute"] == {})

print("--- 5. Les branchements dans jarvis_claude.py")
source = open(r"C:\Jarvis\jarvis_claude.py", encoding="utf-8").read()
for nom, motif in [
    ("chaque morceau de son de la veille est compté", r'rapport\("ecoute_bloc", BLOC_AUDIO / SAMPLE_RATE, niveau_micro, micro_coupe\)'),
    ("chaque phrase entendue est comptée, sans ses mots", r'print\("Entendu :", phrase\)\s+rapport\("ecoute", "phrase"\)'),
    ("chaque réveil est compté", r'if demande is None:\s+continue\s+rapport\("ecoute", "jarvis"\)'),
    ("le réveil pendant un son du PC est compté", r'entendu pendant que le PC joue du son\.\)"\)\s+rapport\("ecoute", "jarvis"\)'),
    ("un « presque Jarvis » non confirmé est compté", r'if presque:\s+rapport\("ecoute", "presque_jarvis"\)'),
    ("l'absence de micro est comptée", r'rapport\("ecoute", "sans_micro"\)'),
]:
    verifie(nom, re.search(motif, source) is not None)
verifie("aucun compteur ne reçoit le texte entendu",
        not re.search(r'rapport\("ecoute(_bloc)?",[^)\n]*(phrase\b(?!")|demande|texte|precise)', source))
ui = open(r"C:\Jarvis\jarvis_rapports_ui.py", encoding="utf-8").read()
verifie("la fenêtre des rapports dit que ces compteurs sont envoyés", "des compteurs, jamais vos paroles" in ui)

# vitesse : appelé dix fois par seconde dans la boucle d'écoute
debut = time.perf_counter()
for _ in range(100000):
    jr.ecoute_bloc(0.1, 0.05)
micro = (time.perf_counter() - debut) / 100000 * 1e6
verifie(f"ecoute_bloc est léger ({micro:.2f} µs par appel, moins de 20)", micro < 20)

print()
print(f"RÉSULTAT : {bons} bons, {rates} ratés")
sys.exit(1 if rates else 0)
