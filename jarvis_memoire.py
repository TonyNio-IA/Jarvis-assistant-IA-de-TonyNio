"""
JARVIS - mémoire durable.

Jarvis garde deux choses dans le fichier C:\\Jarvis\\memoire.json, qui reste sur ce PC
(il n'est jamais envoyé sur GitHub) :
  - les faits que tu lui demandes de retenir (« Jarvis, retiens que ma voiture est une Clio ») ;
  - le fil des derniers échanges, pour qu'il sache de quoi vous parliez même après
    dix minutes de silence ou un redémarrage.

À la voix :
  « retiens que ... » / « souviens-toi que ... » / « n'oublie pas que ... »
  « qu'est-ce que tu as retenu ? » / « qu'est-ce que tu sais sur moi ? »
  « oublie que ... »
  « efface toute ta mémoire » (avec confirmation)

Ces informations sont données à Claude au début de chaque conversation.
"""

import datetime
import difflib
import json
import os
import re
import threading

FICHIER = r"C:\Jarvis\memoire.json"
NB_FAITS_MAX = 60          # au-delà, les plus anciens sont retirés
NB_ECHANGES_GARDES = 30    # échanges conservés dans le fichier
NB_ECHANGES_RAPPELES = 6   # échanges récents redonnés à Claude au début d'une conversation
HEURES_RAPPEL = 12         # ... s'ils datent de moins de 12 heures
LONGUEUR_MAX = 220         # un échange rappelé est raccourci à cette longueur

_verrou = threading.Lock()
_donnees = None
_non_transmis = []         # faits retenus depuis le début de la conversation Claude en cours


def _charger():
    global _donnees
    if _donnees is None:
        try:
            with open(FICHIER, encoding="utf-8") as f:
                lu = json.load(f)
        except (OSError, ValueError):
            lu = {}
        _donnees = {"faits": list(lu.get("faits") or []), "echanges": list(lu.get("echanges") or [])}
    return _donnees


def _enregistrer():
    provisoire = FICHIER + ".tmp"
    try:
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(_donnees, f, ensure_ascii=False, indent=1)
        os.replace(provisoire, FICHIER)
    except OSError as erreur:
        print("Mémoire : écriture impossible :", erreur)


def _simple(texte):
    return re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüœ]+", " ", texte.lower()).strip()


def _maintenant():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- Faits retenus ----------

def faits():
    with _verrou:
        return [f["texte"] for f in _charger()["faits"]]


def retenir(texte):
    """Ajoute un fait. Renvoie False s'il était déjà retenu."""
    texte = " ".join(texte.split()).strip(" .,;:!?«»\"")
    if len(texte) < 3:
        return False
    with _verrou:
        donnees = _charger()
        simple = _simple(texte)
        for fait in donnees["faits"]:
            if _simple(fait["texte"]) == simple:
                return False
        donnees["faits"].append({"texte": texte, "date": _maintenant()})
        del donnees["faits"][:-NB_FAITS_MAX]
        _non_transmis.append(texte)
        _enregistrer()
    return True


def oublier(texte):
    """Retire le fait qui ressemble le plus à « texte ». Renvoie le fait retiré, ou None."""
    cible = _simple(texte)
    mots_cible = set(cible.split()) - _MOTS_VIDES
    with _verrou:
        donnees = _charger()
        meilleur, score_max = None, 0.0
        for i, fait in enumerate(donnees["faits"]):
            simple = _simple(fait["texte"])
            mots = set(simple.split()) - _MOTS_VIDES
            commun = len(mots & mots_cible) / max(1, len(mots_cible))
            score = max(difflib.SequenceMatcher(None, simple, cible).ratio(), commun * 0.95)
            if score > score_max:
                meilleur, score_max = i, score
        if meilleur is None or score_max < 0.6:
            return None
        retire = donnees["faits"].pop(meilleur)["texte"]
        if retire in _non_transmis:
            _non_transmis.remove(retire)
        _enregistrer()
    return retire


def tout_effacer():
    with _verrou:
        donnees = _charger()
        donnees["faits"].clear()
        donnees["echanges"].clear()
        _non_transmis.clear()
        _enregistrer()


_MOTS_VIDES = set("le la les l un une des de du d et que qu je j tu il elle on mon ma mes ton ta tes "
                  "est suis es a ai as en au aux ce c se s ne n pas y à".split())


# ---------- Fil des échanges ----------

def noter_echange(demande, reponse):
    if not demande or not reponse:
        return
    with _verrou:
        donnees = _charger()
        donnees["echanges"].append({"date": _maintenant(), "demande": demande[:400], "reponse": reponse[:600]})
        del donnees["echanges"][:-NB_ECHANGES_GARDES]
        _enregistrer()


def _court(texte):
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_MAX else texte[:LONGUEUR_MAX - 1].rstrip() + "…"


# ---------- Ce qui est donné à Claude ----------

def contexte():
    """Texte ajouté aux consignes de Claude au début d'une conversation."""
    with _verrou:
        donnees = _charger()
        _non_transmis.clear()
        lignes = []
        if donnees["faits"]:
            lignes.append("Ce que TonyNio t'a demandé de retenir (ses propres mots) :")
            lignes += ["- " + f["texte"] for f in donnees["faits"]]
        limite = datetime.datetime.now() - datetime.timedelta(hours=HEURES_RAPPEL)
        recents = []
        for e in donnees["echanges"][-NB_ECHANGES_RAPPELES:]:
            try:
                if datetime.datetime.strptime(e["date"], "%Y-%m-%d %H:%M") >= limite:
                    recents.append(e)
            except (KeyError, ValueError):
                pass
        if recents:
            lignes.append("Vos derniers échanges (pour le contexte, n'y reviens pas sans raison) :")
            for e in recents:
                lignes.append(f"- [{e['date'][11:]}] TonyNio : {_court(e['demande'])} | Toi : {_court(e['reponse'])}")
    return "\n".join(lignes)


def nouveautes():
    """Faits retenus depuis le début de la conversation en cours (Claude ne les connaît pas encore)."""
    with _verrou:
        nouveaux = list(_non_transmis)
        _non_transmis.clear()
    if not nouveaux:
        return ""
    return "(Information que TonyNio vient de te demander de retenir : " + " ; ".join(nouveaux) + ".) "


# ---------- Balises écrites par Claude ----------

_BALISE = re.compile(r"^\s*(RETENIR|OUBLIER)\s*:\s*(.+?)\s*$", re.I | re.M)


def appliquer_balises(reponse):
    """Claude peut finir sa réponse par « RETENIR: ... » ou « OUBLIER: ... » :
    la mémoire est mise à jour et ces lignes sont retirées de ce que Jarvis dit."""
    for action, texte in _BALISE.findall(reponse):
        if action.upper() == "RETENIR":
            if retenir(texte):
                print("Mémoire : retenu :", texte)
        else:
            retire = oublier(texte)
            print("Mémoire : oublié :", retire or "(rien ne correspondait)")
    with _verrou:
        _non_transmis.clear()          # Claude vient de les écrire lui-même : il les connaît
    return _BALISE.sub("", reponse).strip()


# ---------- Commandes à la voix ----------

_RETENIR = re.compile(
    r"^\W*(?:est-ce que tu peux |tu peux |peux-tu |tu pourrais |pourrais-tu |s'il te pla[îi]t )?"
    r"(?:retiens|retenir|souviens-toi|te souvenir|rappelle-toi|te rappeler|n'oublie (?:pas|jamais)|"
    r"m[ée]morise|m[ée]moriser|garde en m[ée]moire|garder en m[ée]moire|"
    r"(?:note|enregistre|ajoute|mets)(?: [çc]a)? (?:dans|[àa]|en) (?:ta )?m[ée]moire)"
    r"\s*(?:bien\s+)?(?:que\s+|qu'|:|,)?\s*(.+)$", re.I | re.S)
_LIRE = re.compile(
    r"qu'est-ce que tu (?:sais|connais) (?:sur|de) moi|que sais-tu (?:sur|de) moi|"
    r"qu'est-ce que tu (?:as retenu|retiens|te rappelles|as en m[ée]moire|as dans ta m[ée]moire)|"
    r"qu'as-tu retenu|de quoi (?:est-ce que )?tu te souviens|"
    r"\b(?:lis|relis|dis-moi|montre|montre-moi)\b.*\bta m[ée]moire\b|"
    r"qu'y a-t-il dans ta m[ée]moire|qu'est-ce qu'il y a dans ta m[ée]moire", re.I)
_TOUT_EFFACER = re.compile(
    r"\b(?:efface|vide|supprime|r[ée]initialise)\b.*\b(?:toute )?ta m[ée]moire\b|"
    r"\boublie tout ce que (?:tu sais|je t'ai dit)\b", re.I)
_OUBLIER = re.compile(
    r"^\W*(?:est-ce que tu peux |tu peux |peux-tu )?(?:oublie|oublier|efface|effacer|supprime|retire)\s+"
    r"(?:de ta m[ée]moire\s+)?(?:le fait que\s+|que\s+|qu'|ce que je t'ai dit (?:sur|à propos de)\s+)(.+)$", re.I | re.S)


def commande(brut):
    """Renvoie ("dire", texte), ("confirmer_effacement", question) ou None si ce n'est pas pour la mémoire."""
    texte = brut.replace("’", "'").strip()
    if _TOUT_EFFACER.search(texte):
        return "confirmer_effacement", "Tu veux vraiment que j'efface toute ma mémoire ? Dis oui pour confirmer."
    m = _OUBLIER.match(texte)
    if m:
        retire = oublier(m.group(1))
        return "dire", (f"C'est oublié : {retire}." if retire else "Je n'avais rien retenu qui ressemble à ça.")
    if _LIRE.search(texte):
        liste = faits()
        if not liste:
            return "dire", "Je n'ai encore rien retenu. Dis-moi : retiens que, suivi de l'information."
        debut = "J'ai retenu une chose : " if len(liste) == 1 else f"J'ai retenu {len(liste)} choses : "
        return "dire", debut + " ; ".join(liste[-12:]) + "."
    m = _RETENIR.match(texte)
    if m:
        fait = m.group(1).strip(" .!?")
        if len(fait.split()) < 2:
            return None
        return "dire", ("C'est retenu." if retenir(fait) else "Je l'avais déjà retenu.")
    return None
