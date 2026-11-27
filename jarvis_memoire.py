"""
JARVIS - mémoire durable.

Jarvis garde deux choses dans le fichier memoire.json, qui reste sur ce PC
(il n'est jamais envoyé sur GitHub) :
  - les faits que tu lui demandes de retenir (« Jarvis, retiens que ma voiture est une Clio ») ;
  - le fil des derniers échanges, pour qu'il sache de quoi vous parliez même après
    dix minutes de silence ou un redémarrage.

À la voix :
  « retiens que ... » / « souviens-toi que ... » / « n'oublie pas que ... »
  « qu'est-ce que tu as retenu ? » / « qu'est-ce que tu sais sur moi ? »
  « qu'est-ce que tu as retenu sur ma voiture ? » / « rappelle-moi ce qu'on avait décidé pour le jardin »
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

import jarvis_config

FICHIER = jarvis_config.chemin("memoire.json")
NB_FAITS_MAX = 500         # au-delà, les plus anciens sont retirés (60 jusqu'à la 1.66 : on en perdait)
NB_FAITS_CONTEXTE = 40     # faits donnés à Claude au début d'une conversation ; les autres reviennent avec leur sujet
JOURS_PASSAGER = 30        # un fait passager (« demain », « ce soir »…) n'est plus rappelé après ce délai
NB_ECHANGES_GARDES = 30    # échanges conservés dans le fichier
NB_ECHANGES_RAPPELES = 6   # échanges récents redonnés à Claude au début d'une conversation
HEURES_RAPPEL = 12         # ... s'ils datent de moins de 12 heures
LONGUEUR_MAX = 220         # un échange rappelé est raccourci à cette longueur

_verrou = threading.Lock()
_donnees = None
_non_transmis = []         # faits retenus depuis le début de la conversation Claude en cours
_transmis = set()          # faits déjà donnés à Claude dans la conversation en cours

CATEGORIES = (             # (nom, mots qui la désignent) : la première qui convient ; sinon « Autre »
    ("Projets et décisions", r"projets?|d[ée]cid\w*|d[ée]cisions?|on a choisi|objectifs?|pr[ée]vu\w*|plans?|budget"),
    ("Santé", r"m[ée]decins?|docteur|dentiste|m[ée]dicaments?|allergi\w*|ordonnance|pharmacie|h[ôo]pital|kin[ée]|lunettes"),
    ("Véhicules", r"voitures?|motos?|v[ée]los?|camions?|scooter|plaque|contr[ôo]le technique|pneus?|essence|diesel|garagiste"),
    ("Travail et études", r"travail\w*|boulot|bureau|patron|coll[èe]gues?|r[ée]unions?|clients?|[ée]cole|classe|devoirs|[ée]tudes|"
                          r"m[ée]tier|entreprise|chantier|coll[èe]ge|lyc[ée]e|ma[îi]tresse|professeur"),
    ("Famille et proches", r"femme|mari|fils|filles?|enfants?|p[èe]re|m[èe]re|papa|maman|fr[èe]res?|s[œo]e?urs?|amie?s?|copains?|"
                           r"copines?|anniversaires?|mamie|papi|cousine?s?|oncle|tante|voisine?s?|chien|chat|b[ée]b[ée]"),
    ("Maison", r"maison|appartement|jardin|cuisine|garage|cl[ée]s?|code|wi-?fi|box|poubelles?|loyer|chauffage|salon|chambre"),
    ("Goûts et loisirs", r"aimes?|adores?|pr[ée]f[èe]re\w*|d[ée]testes?|favori\w*|pr[ée]f[ée]r[ée]\w*|jeux?|films?|s[ée]ries?|musique|"
                         r"sport|foot|[ée]quipe|console|ps5|xbox|switch|couleur|plat|dessert"),
    ("Rendez-vous et dates", r"rendez-vous|rdv|dates?|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|"
                             r"novembre|d[ée]cembre|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|\d+ ?h\b"),
)
_PASSAGER = re.compile(r"\b(?:aujourd'hui|ce soir|ce matin|cet apr[èe]s-midi|cette nuit|demain|apr[èe]s-demain|tout [àa] l'heure|"
                       r"cette semaine|ce week-end|ce mois-ci|la semaine prochaine|le mois prochain|"
                       r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) prochain)\b", re.I)


_NOMS_CATEGORIE = (("Projets et décisions", r"projets?|d[ée]cisions?"), ("Santé", r"sant[ée]"),
                   ("Véhicules", r"v[ée]hicules?"), ("Travail et études", r"travail|boulot|[ée]tudes"),
                   ("Famille et proches", r"famille|proches"), ("Maison", r"maison"),
                   ("Goûts et loisirs", r"go[ûu]ts?|loisirs?"), ("Rendez-vous et dates", r"rendez-vous|dates"))


def categorie(texte):
    """La catégorie d'un fait, d'après ses mots (rangement dans les réglages et recherche par sujet)."""
    for nom, mots in CATEGORIES:
        if re.search(r"\b(?:" + mots + r")\b", texte, re.I):
            return nom
    return "Autre"


def _perime(fait, maintenant=None):
    """Un fait passager (« demain j'ai… ») retenu il y a plus de JOURS_PASSAGER jours : gardé, mais plus rappelé."""
    if not _PASSAGER.search(fait.get("texte", "")):
        return False
    try:
        quand = datetime.datetime.strptime(fait.get("date", ""), "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return (maintenant or datetime.datetime.now()) - quand > datetime.timedelta(days=JOURS_PASSAGER)


def _racines(texte):
    """Les mots utiles d'un texte, réduits à leur début (« voitures » et « voiture » se retrouvent)."""
    return {m[:5] if len(m) > 5 else m.rstrip("sx") if len(m) > 3 else m
            for m in _simple(texte).split() if m not in _MOTS_VIDES and len(m) >= 3}


def tous():
    """Tous les faits, pour les réglages : [{texte, date, categorie, source, perime}], du plus récent au plus ancien."""
    with _verrou:
        liste = [{"texte": f["texte"], "date": f.get("date", ""), "categorie": categorie(f["texte"]),
                  "source": f.get("source", "toi"), "perime": _perime(f)} for f in _charger()["faits"]]
    return liste[::-1]


def sur(sujet):
    """Les faits retenus qui parlent de ce sujet (ou de sa catégorie : « ma famille », « mon travail »)."""
    cherche = _racines(sujet)
    if not cherche:
        return []
    # une catégorie entière seulement si le sujet la nomme (« ma famille », « mon travail », « mes projets »)
    rangs = [nom for nom, mots in _NOMS_CATEGORIE if re.search(r"\b(?:" + mots + r")\b", sujet, re.I)]
    trouves = []
    with _verrou:
        for f in _charger()["faits"]:
            if _perime(f):
                continue
            if cherche & _racines(f["texte"]) or categorie(f["texte"]) in rangs:
                trouves.append(f["texte"])
    return trouves


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
        return [f["texte"] for f in _charger()["faits"] if not _perime(f)]


def retenir(texte, source="toi"):
    """Ajoute un fait. Renvoie False s'il était déjà retenu. source : « toi » (tu l'as demandé) ou « jarvis »
    (Jarvis l'a retenu de lui-même pendant une conversation)."""
    texte = " ".join(texte.split()).strip(" .,;:!?«»\"")
    if len(texte) < 3:
        return False
    with _verrou:
        donnees = _charger()
        simple = _simple(texte)
        for fait in donnees["faits"]:
            if _simple(fait["texte"]) == simple:
                return False
        donnees["faits"].append({"texte": texte, "date": _maintenant(), "source": source})
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


def oublier_exact(texte):
    """Retire exactement ce fait (bouton des réglages). Renvoie True s'il y était."""
    with _verrou:
        donnees = _charger()
        avant = len(donnees["faits"])
        donnees["faits"] = [f for f in donnees["faits"] if f["texte"] != texte]
        if len(donnees["faits"]) == avant:
            return False
        if texte in _non_transmis:
            _non_transmis.remove(texte)
        _enregistrer()
    return True


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

def _invite():
    try:
        import jarvis_extras
        return jarvis_extras.invite()
    except Exception:
        return False


def noter_echange(demande, reponse, par="", autre=""):
    if not demande or not reponse or _invite():         # mode invité : rien n'est enregistré
        return
    with _verrou:
        donnees = _charger()
        donnees["echanges"].append({"date": _maintenant(), "demande": demande[:400], "reponse": reponse[:600]})
        del donnees["echanges"][:-NB_ECHANGES_GARDES]
        _enregistrer()
    try:                              # rapport complet (seulement si l'utilisateur l'a choisi) : texte nettoyé, jamais en profil enfant
        import jarvis_enfant
        if jarvis_enfant.actif():
            return
    except Exception:
        pass
    try:
        import jarvis_rapports
        jarvis_rapports.conversation(demande, reponse, par, autre)
    except Exception:
        pass


def _court(texte):
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_MAX else texte[:LONGUEUR_MAX - 1].rstrip() + "…"


# ---------- Ce qui est donné à Claude ----------

def contexte():
    """Texte ajouté aux consignes de Claude au début d'une conversation."""
    if _invite():                    # mode invité : Claude ne reçoit pas la mémoire
        return ""
    with _verrou:
        donnees = _charger()
        _non_transmis.clear()
        lignes = []
        valables = [f for f in donnees["faits"] if not _perime(f)]
        donnes = valables[-NB_FAITS_CONTEXTE:]
        _transmis.clear()
        _transmis.update(f["texte"] for f in donnes)
        if donnes:
            lignes.append("Ce que " + jarvis_config.NOM + " t'a demandé de retenir (ses propres mots) :")
            lignes += ["- " + f["texte"] for f in donnes]
            if len(valables) > len(donnes):
                lignes.append(f"({len(valables) - len(donnes)} faits plus anciens sont aussi en mémoire : ils te seront "
                              "rappelés quand la demande en parlera.)")
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
                lignes.append(f"- [{e['date'][11:]}] {jarvis_config.NOM} : {_court(e['demande'])} | Toi : {_court(e['reponse'])}")
    return "\n".join(lignes)


def _rappels_pour(demande):
    """Faits anciens (pas donnés au début de la conversation) dont la demande parle : 3 au plus."""
    cherche = _racines(demande)
    if not cherche:
        return []
    with _verrou:
        candidats = [f for f in _charger()["faits"] if f["texte"] not in _transmis and not _perime(f)]
        if not candidats:
            return []
        cherche = {r for r in cherche if len(r) >= 4}      # (un petit mot en commun ne suffit pas)
        notes = sorted(((len(cherche & _racines(f["texte"])), i, f["texte"]) for i, f in enumerate(candidats)), reverse=True)
        choisis = [texte for commun, _, texte in notes if commun >= 1][:3]
        _transmis.update(choisis)
    return choisis


def nouveautes(demande=""):
    """Faits retenus depuis le début de la conversation en cours (Claude ne les connaît pas encore), et faits
    anciens dont la demande parle."""
    if _invite():
        return ""
    with _verrou:
        nouveaux = list(_non_transmis)
        _non_transmis.clear()
        _transmis.update(nouveaux)
    anciens = _rappels_pour(demande) if demande else []
    rappel = ("(Dans ta mémoire, en lien avec cette demande : " + " ; ".join(anciens) + ".) ") if anciens else ""
    if not nouveaux:
        return rappel
    return rappel + ("(Information que " + jarvis_config.NOM + " vient de te demander de retenir, déjà enregistrée dans ta mémoire : "
            + " ; ".join(nouveaux) + ". N'écris pas de ligne RETENIR pour elle.) ")


# ---------- Balises écrites par Claude ----------

_BALISE = re.compile(r"^\s*(RETENIR|OUBLIER)\s*:\s*(.+?)\s*$", re.I | re.M)


def appliquer_balises(reponse):
    """Claude peut finir sa réponse par « RETENIR: ... » ou « OUBLIER: ... » :
    la mémoire est mise à jour et ces lignes sont retirées de ce que Jarvis dit."""
    for action, texte in _BALISE.findall(reponse):
        if action.upper() == "RETENIR":
            if retenir(texte, source="jarvis"):
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
    r"(?:retiens|retient|retenez|retenir|souviens-toi|te souvenir|rappelle-toi|te rappeler|n'oublie (?:pas|jamais)|"
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


_SUR_MEMOIRE = re.compile(      # question qui parle clairement de la mémoire : on répond toujours
    r"qu'est-ce que tu (?:as retenu|retiens|te rappelles|as en m[ée]moire|as not[ée]|as dans ta m[ée]moire)\s+"
    r"(?:sur|[àa] propos (?:de |d')|au sujet (?:de |d')|concernant|pour|de |d')\s*(.+)$|"
    r"qu'as-tu retenu\s+(?:sur|[àa] propos (?:de |d')|au sujet (?:de |d')|concernant|pour)\s*(.+)$|"
    r"(?:rappelle-moi|redis-moi|dis-moi) ce (?:qu'on avait|qu'on a|que nous avions|que j'avais|que j'ai|que tu avais|que tu as) "
    r"(?:d[ée]cid[ée]|dit|pr[ée]vu|retenu|not[ée]|choisi)\s+(?:pour|sur|[àa] propos (?:de |d')|au sujet (?:de |d')|concernant)\s*(.+)$|"
    r"qu'est-ce qu'on avait (?:d[ée]cid[ée]|dit|pr[ée]vu|retenu|choisi)\s+(?:pour|sur|[àa] propos (?:de |d')|au sujet (?:de |d')|concernant)\s*(.+)$|"
    r"(?:cherche|regarde|fouille) dans ta m[ée]moire\s+(?:ce que tu as\s+)?(?:sur|pour|[àa] propos (?:de |d')|au sujet (?:de |d'))?\s*(.+)$", re.I)
_SUR_MOI = re.compile(          # « ce que tu sais sur ma voiture » : la mémoire seulement si elle a quelque chose
    r"(?:qu'est-ce que tu (?:sais|connais)|que sais-tu|que connais-tu)\s+(?:sur|de|[àa] propos de|au sujet de)\s+"
    r"((?:mon|ma|mes|notre|nos)\s+.+)$", re.I)


def _par_sujet(texte):
    m = _SUR_MEMOIRE.search(texte)
    sujet = next((g for g in m.groups() if g), "") if m else ""
    sur_moi = _SUR_MOI.search(texte) if not m else None
    if sur_moi:
        sujet = sur_moi.group(1)
    sujet = sujet.strip(" .!?")
    if not sujet or _simple(sujet) in ("moi", "nous", "toi"):
        return None
    trouves = sur(sujet)
    if not trouves:
        return None if sur_moi else ("dire", f"Je n'ai rien retenu sur {sujet}.")
    debut = "Voici ce que j'ai retenu : " if len(trouves) == 1 else f"J'ai retenu {len(trouves)} choses là-dessus : "
    return "dire", debut + " ; ".join(trouves[-8:]) + "."


def commande(brut):
    """Renvoie ("dire", texte), ("confirmer_effacement", question) ou None si ce n'est pas pour la mémoire."""
    texte = brut.replace("’", "'").strip()
    if _TOUT_EFFACER.search(texte):
        return "confirmer_effacement", "Tu veux vraiment que j'efface toute ma mémoire ? Dis oui pour confirmer."
    m = _OUBLIER.match(texte)
    if m:
        retire = oublier(m.group(1))
        return "dire", (f"C'est oublié : {retire}." if retire else "Je n'avais rien retenu qui ressemble à ça.")
    par_sujet = _par_sujet(texte)
    if par_sujet:
        return par_sujet
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
