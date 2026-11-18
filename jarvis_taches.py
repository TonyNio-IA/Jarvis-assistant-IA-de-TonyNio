"""
JARVIS - tâches de fond confiées à Claude Code (comme les agents Hermes de Cornelius).

Une demande longue part en arrière-plan : Jarvis reste disponible pendant que Claude cherche, puis il
annonce le résultat dès qu'il est prêt.
  « Jarvis, en tâche de fond, compare les trois meilleurs aspirateurs robots à moins de 300 euros »
  « Jarvis, fais une recherche approfondie sur les voitures électriques d'occasion, préviens-moi quand c'est prêt »
  « Jarvis, prends ton temps et trouve-moi des idées de sorties en famille ce week-end »
  « où en est ma recherche ? »          « annule la tâche de fond »
Une seule tâche à la fois. Claude n'a droit qu'à la recherche sur Internet (aucune action sur le PC).
Pas en mode enfant. Chaque tâche consomme du quota Claude : elle ne part que sur demande explicite.
"""

import re
import subprocess
import threading
import time
import json

# Une tâche de fond commence toujours par un vrai travail à faire (« mets la vidéo en arrière-plan » n'en est pas une)
_VERBE = (r"(?:cherche|recherche|trouve|compare|regarde|renseigne[- ]toi|fais(?:-moi)? (?:une |des )?(?:recherches?|liste|"
          r"comparatif|r[ée]sum[ée]|synth[èe]se|point|plan|programme|s[ée]lection)|pr[ée]pare|[ée]tudie|analyse|r[ée]sume|"
          r"liste|calcule|r[ée]dige|[ée]cris|v[ée]rifie|organise|planifie|propose|sugg[èe]re|explique|d[ée]niche)")
_LANCER = [
    re.compile(r"^\W*(?:jarvis\W+)?(?:en (?:arri[èe]re[- ]plan|t[âa]che de fond)|prends ton temps(?: et| pour)?|"
               r"sans te presser,?)\W+(?P<tache>" + _VERBE + r"\b.{6,})$"),
    re.compile(r"^\W*(?:jarvis\W+)?(?P<tache>" + _VERBE + r"\b.{6,}?)\W+en (?:arri[èe]re[- ]plan|t[âa]che de fond)\b"
               r"(?P<fin>.*)$"),
    re.compile(r"^\W*(?:jarvis\W+)?(?:fais|lance|fais-moi|lance-moi)(?: une| des)? recherches? approfondies?\s+"
               r"(?P<tache>(?:sur|pour|à propos de|concernant)\s.{4,})$"),
]
_FIN = re.compile(r"[,.]?\s*(?:et\s+)?(?:pr[ée]viens[- ]moi|dis[- ]le[- ]moi|tiens[- ]moi au courant|"
                  r"reviens vers moi)\b.*$")
_ETAT = re.compile(r"\b(?:o[ùu] en est|c'est pr[êe]t|elle est finie|elle avance|tu as fini)\b.{0,30}"
                   r"\b(?:recherche|t[âa]che)\b|\b(?:ma|la) (?:recherche|t[âa]che) (?:de fond |en arri[èe]re[- ]plan )?"
                   r"(?:est[- ]elle|avance|est pr[êe]te|est finie)")
_ANNULER = re.compile(r"\b(?:annule|arr[êe]te|stoppe|laisse tomber)\b.{0,15}\b(?:la |ma )?(?:recherche|t[âa]che)"
                      r"(?: de fond| en arri[èe]re[- ]plan| approfondie)?\b")

CONSIGNES = (
    "Tu es Jarvis, l'assistant vocal d'un foyer français. On t'a confié une tâche de fond : prends le temps de la "
    "faire bien, avec des recherches sur Internet si c'est utile, en vérifiant les informations importantes "
    "sur plusieurs sources. Ta réponse finale sera lue à voix haute : en français, entre quatre et huit phrases "
    "claires, sans markdown, sans liste, sans emoji, sans lien ni adresse web. Commence directement par le résultat, "
    "sans phrase sur tes recherches. Si une information n'a pas pu être vérifiée, dis-le simplement. "
    "N'invente rien.")

_etat = {"tache": None, "debut": 0.0, "proc": None, "annulee": False}
_verrou = threading.Lock()
_reglages = {}


def configurer(executable, modele, outils, permissions, options, dossier, annoncer, delai=900):
    """Appelé une fois au démarrage de Jarvis. annoncer(texte, erreur) fait dire le résultat."""
    _reglages.update(executable=executable, modele=modele, outils=outils, permissions=permissions,
                     options=list(options), dossier=dossier, annoncer=annoncer, delai=delai)


def en_cours():
    return _etat["tache"] is not None


def _executer(tache):
    r = _reglages
    commande = [r["executable"], "-p", tache, "--append-system-prompt", CONSIGNES,
                "--permission-mode", r["permissions"], "--output-format", "json",
                "--model", r["modele"], *r["options"], "--tools", r["outils"]]
    proc = subprocess.Popen(commande, cwd=r["dossier"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    _etat["proc"] = proc
    try:
        sortie, erreurs = proc.communicate(timeout=r["delai"])
    except subprocess.TimeoutExpired:
        proc.kill()
        return "La tâche de fond a pris trop de temps, je l'ai arrêtée.", True
    try:
        donnees = json.loads((sortie or "").strip())
    except ValueError:
        donnees = None
    if not donnees:
        if "limit" in ((erreurs or "") + (sortie or "")).lower():
            return "La limite d'utilisation de Claude est atteinte, je n'ai pas pu finir la tâche de fond.", True
        return "Claude ne m'a pas répondu pour la tâche de fond.", True
    reponse = str(donnees.get("result") or "").strip()
    if donnees.get("is_error") or not reponse:
        return "Claude a rencontré un problème avec la tâche de fond.", True
    return re.sub(r"[*_#`>]", "", reponse), False


def _travailler(tache, resume):
    try:
        texte, erreur = _executer(tache)
    except Exception as e:
        print("Tâche de fond :", e)
        texte, erreur = "Je n'ai pas pu lancer la tâche de fond.", True
    with _verrou:
        annulee = _etat["annulee"]
        _etat.update(tache=None, proc=None, annulee=False)
    if annulee:
        return
    debut = "" if erreur else f"Ta tâche de fond est prête, {resume}. "
    _reglages["annoncer"](debut + texte, erreur)


def _resume(tache):
    mots = tache.split()
    return "à propos de « " + " ".join(mots[:8]) + (" …" if len(mots) > 8 else "") + " »"


def commande(textes, enfant=False):
    """Lance, suit ou annule une tâche de fond. Renvoie la phrase à dire, ou None."""
    for brut in textes:
        if not brut:
            continue
        t = brut.replace("’", "'").strip()
        bas = t.lower()
        if _ANNULER.search(bas) and not _LANCER[0].match(bas):
            with _verrou:
                if _etat["tache"] is None:
                    return "Aucune tâche de fond n'est en cours."
                _etat["annulee"] = True
                proc = _etat["proc"]
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            return "D'accord, j'annule la tâche de fond."
        if _ETAT.search(bas):
            if _etat["tache"] is None:
                return "Aucune tâche de fond n'est en cours."
            minutes = int((time.time() - _etat["debut"]) // 60)
            depuis = f"depuis {minutes} minute{'s' if minutes > 1 else ''}" if minutes else "depuis moins d'une minute"
            return f"J'y travaille encore, {depuis}. Je te préviens dès que c'est prêt."
        for motif in _LANCER:
            m = motif.match(bas)
            if not m:
                continue
            if not _reglages:
                return None
            if enfant:
                return "Les tâches de fond ne sont pas disponibles en mode enfant."
            tache = _FIN.sub("", t[m.start("tache"):m.end("tache")]).strip(" ,.")
            if len(tache) < 8:
                return None
            with _verrou:
                if _etat["tache"] is not None:
                    return "Je travaille déjà sur une tâche de fond. Demande-moi où elle en est, ou annule-la."
                _etat.update(tache=tache, debut=time.time(), annulee=False)
            threading.Thread(target=_travailler, args=(tache, _resume(tache)), daemon=True).start()
            return "C'est parti, je m'en occupe en arrière-plan. Tu peux continuer à me parler, je te préviens dès que c'est prêt."
    return None
