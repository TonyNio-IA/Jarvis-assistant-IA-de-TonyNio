# -*- coding: utf-8 -*-
"""Jarvis prévient quand le disque est presque plein, mais RAREMENT, pour ne jamais devenir lourd :
- une première fois quand la place libre passe sous le seuil ;
- ensuite plus rien pendant 30 jours, sauf si la situation EMPIRE nettement (place libre divisée par deux,
  ou moins de 2 Go : là Windows et Jarvis risquent de mal marcher), et jamais deux fois en 3 jours ;
- « Jarvis, ne me préviens plus pour le disque » coupe ces avertissements (« préviens-moi pour le disque » les remet).
Seuil : moins de 10 % du disque ET moins de 15 Go libres, ou moins de 5 Go libres quelle que soit la taille."""
import json
import os
import re
import shutil
import threading
import time

import jarvis_config

FICHIER = jarvis_config.chemin("disque.json")
INTERVALLE = 6 * 3600            # une vérification toutes les 6 heures
PREMIER_CONTROLE = 15 * 60       # la première, un quart d'heure après le démarrage (jamais au milieu de l'accueil)
JOURS_SILENCE = 30
JOURS_MINI = 3
JOUR = 86400
_verrou = threading.Lock()


def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _ecrire(d):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def place():
    """(libre en Go, total en Go) du disque de Windows."""
    racine = os.environ.get("SystemDrive", "C:") + os.sep
    u = shutil.disk_usage(racine)
    return u.free / 2 ** 30, u.total / 2 ** 30


def trop_plein(libre, total):
    return libre < 5 or (libre < 15 and libre < 0.10 * total)


def faut_il_prevenir(libre, total, donnees, maintenant):
    """True s'il faut prévenir maintenant. Fonction sans effet de bord (essayée dans tests\\essai_disque_166.py)."""
    if donnees.get("coupe") or not trop_plein(libre, total):
        return False
    dernier = donnees.get("dernier")
    if not dernier:
        return True
    depuis = maintenant - dernier
    if depuis < JOURS_MINI * JOUR:
        return False
    if depuis >= JOURS_SILENCE * JOUR:
        return True
    avant = donnees.get("libre_go", libre)
    return libre <= avant / 2 or (libre < 2 <= avant)


def phrase(libre):
    if libre < 2:
        return (f"Attention, il ne reste plus que {libre:.1f} gigaoctet libre sur ton disque. Windows et moi risquons "
                "de mal fonctionner. Vide la corbeille et supprime les gros fichiers dont tu n'as plus besoin, par exemple "
                "dans Téléchargements.").replace(".", ",", 1)
    return (f"Petite info : ton disque est presque plein, il reste {round(libre)} gigaoctets libres. Quand tu auras un "
            "moment, vide la corbeille ou supprime de vieux fichiers. Je ne te le redirai pas avant longtemps. "
            "Si tu ne veux plus que je te prévienne, dis : Jarvis, ne me préviens plus pour le disque.")


def verifier(annoncer, maintenant=None):
    maintenant = maintenant or time.time()
    libre, total = place()
    with _verrou:
        d = _lire()
        if not faut_il_prevenir(libre, total, d, maintenant):
            if not trop_plein(libre, total) and d.get("dernier"):
                d.pop("dernier", None)       # la place est revenue : un prochain manque sera de nouveau signalé
                d.pop("libre_go", None)
                _ecrire(d)
            return False
        d["dernier"], d["libre_go"] = maintenant, round(libre, 1)
        _ecrire(d)
    annoncer(phrase(libre))
    return True


def surveiller(annoncer):
    def boucle():
        time.sleep(PREMIER_CONTROLE)
        while True:
            try:
                verifier(annoncer)
            except Exception as erreur:
                print("Disque :", type(erreur).__name__, erreur)
            time.sleep(INTERVALLE)
    threading.Thread(target=boucle, daemon=True).start()


_COUPER = re.compile(r"\b(?:ne me previens plus|arrete de me prevenir|ne me dis plus rien|ne me parle plus)\b.*\bdisque\b")
_REMETTRE = re.compile(r"\b(?:previens[- ]moi|recommence a me prevenir|remets les avertissements)\b.*\bdisque\b")


def commande(t):
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    if not re.search(r"\bdisque\b", s):
        return None
    if _COUPER.search(s):
        with _verrou:
            d = _lire()
            d["coupe"] = True
            _ecrire(d)
        return "D'accord, je ne te préviendrai plus quand le disque est presque plein."
    if _REMETTRE.search(s) and not re.search(r"\bne\b", s):
        with _verrou:
            d = _lire()
            d["coupe"] = False
            _ecrire(d)
        return "D'accord, je te préviendrai de nouveau si le disque est presque plein, mais rarement."
    return None
