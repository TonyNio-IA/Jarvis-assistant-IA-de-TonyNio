"""
JARVIS - informations du quotidien (sans Claude, donc instantanées et sans quota).

  « combien coûte le gazole ? », « le prix du sans-plomb 98 »   le carburant le moins cher près de ta ville
  « mon carburant, c'est le gazole »                            retenu pour « le prix du carburant »
  « c'est quand les prochaines vacances ? », « on est en vacances ? », « c'est quand la rentrée ? »
  « c'est quand le prochain jour férié ? », « est-ce que demain est férié ? »
  « l'éphéméride », « qu'est-ce qui s'est passé un jour comme aujourd'hui ? », « ... un 20 octobre ? »
  « la poubelle jaune passe le mercredi des semaines paires »   Jarvis retient les jours de ramassage
  « quelle poubelle je sors ce soir ? », « c'est quand le verre ? », « quels sont les jours de ramassage ? »
  « oublie la poubelle jaune », « arrête les rappels de poubelles » / « remets les rappels de poubelles »

Sources publiques, sans clé ni compte : prix des carburants (data.economie.gouv.fr), calendrier scolaire
(data.education.gouv.fr), jours fériés (calendrier.api.gouv.fr), éphéméride (Wikipédia en français, CC BY-SA 4.0).
Les jours de ramassage sont calculés sur ce PC, sans réseau.
Idées reprises des modules du projet Cornelius des Frères Poulain (github.com/lfpoulain/cornelius-modules,
licence MIT), réécrites pour Jarvis.
Chaque fonction « commande_... » renvoie la phrase à dire, ou None si la demande ne la concerne pas.
Les réglages (carburant préféré, jours de ramassage) restent sur ce PC, dans infos.json (jamais publié).
"""

import calendar
import datetime
import json
import re
import threading
import time
import urllib.parse
import urllib.request

import jarvis_config

FICHIER = jarvis_config.chemin("infos.json")
DELAI = 8                      # secondes maximum pour une source en ligne
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
_MOIS_RE = r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
_verrou = threading.Lock()


# ---------- Outils communs ----------

def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t


def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    except OSError as erreur:
        print("infos.json :", erreur)


def _regler(cle, valeur):
    with _verrou:
        donnees = _lire()
        donnees[cle] = valeur
        _ecrire(donnees)


def _json(url):
    requete = urllib.request.Request(url, headers={"User-Agent": "Jarvis (assistant vocal personnel)"})
    with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def _en_cache(nom, cle, duree, lire):
    """Résultat de lire(), gardé `duree` secondes ; si la source ne répond pas, le dernier résultat connu."""
    with _verrou:
        cache = (_lire().get("cache") or {}).get(nom) or {}
    if cache.get("cle") == cle and time.time() - float(cache.get("quand") or 0) < duree:
        return cache.get("valeur"), True
    try:
        valeur = lire()
    except Exception as erreur:
        print("Infos,", nom, ":", erreur)
        if cache.get("cle") == cle and cache.get("valeur"):
            return cache["valeur"], False          # dernier résultat connu, à vérifier
        return None, False
    with _verrou:
        donnees = _lire()
        donnees.setdefault("cache", {})[nom] = {"cle": cle, "quand": time.time(), "valeur": valeur}
        _ecrire(donnees)
    return valeur, True


def _jour_dit(jour, avec_mois=True):
    """« mercredi 25 novembre », « dimanche 1er novembre »."""
    numero = "1er" if jour.day == 1 else str(jour.day)
    return f"{JOURS[jour.weekday()]} {numero}" + (f" {MOIS[jour.month - 1]}" if avec_mois else "")


def _dans(jours):
    return "aujourd'hui" if jours == 0 else "demain" if jours == 1 else f"dans {jours} jours"


def _ville():
    import jarvis_commandes                      # à la demande : jarvis_commandes charge ce module
    return jarvis_commandes.VILLE_DEFAUT


def _departement():
    try:
        import jarvis_vigilance
        return str(jarvis_vigilance.departement() or "")
    except Exception as erreur:
        print("Infos, département :", erreur)
        return ""


def _debut(t):
    return re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")


# ---------- Prix des carburants (flux officiel du ministère de l'Économie) ----------

URL_CARBURANTS = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
                  "prix-des-carburants-en-france-flux-instantane-v2/records?")
# (champ du flux, façon de le dire, mots qui le désignent) : du plus précis au plus général
_CARBURANTS = [
    ("e10", "le sans-plomb 95 E10", r"sp ?95[- ]?e ?10|sans[- ]plomb 95 e ?10|\be ?10\b|\beu? dix\b"),
    ("sp98", "le sans-plomb 98", r"sp ?98|sans[- ]plomb 98|\b98\b|quatre[- ]vingt[- ]dix[- ]huit"),
    ("e85", "le E85", r"\be ?85\b|bio[ée]thanol|super[ée]thanol|[ée]thanol"),
    ("gplc", "le GPL", r"\bgpl\b|\bg p l\b"),
    ("gazole", "le gazole", r"gazole|gasoil|gas[- ]oil|gazoil|diesel|di[ée]sel"),
    ("sp95", "le sans-plomb 95", r"sp ?95|sans[- ]plomb 95|\b95\b|quatre[- ]vingt[- ]quinze"),
]
_ESSENCE = r"\bessence\b|sans[- ]plomb"            # sans précision : E10 d'abord, sinon sans-plomb 95
_NOMS_CARBURANTS = {champ: nom for champ, nom, _ in _CARBURANTS}
_QUESTION_PRIX = re.compile(r"\b(prix|tarifs?|combien|moins ch[eè]re?s?|co[uû]te|vaut)\b")
_MOT_CARBURANT = re.compile(r"\b(carburants?|station[- ]service|stations?[- ]essence|plein d'essence|faire le plein)\b|"
                            + _ESSENCE + "|" + "|".join(motif for _, _, motif in _CARBURANTS))
_MON_CARBURANT = re.compile(r"\b(?:mon carburant|ma voiture roule|je roule|je mets)\b")
AGE_MAX = 10                   # jours : un prix plus ancien n'est plus annoncé


def _carburant_demande(t):
    """Le ou les champs du flux qui correspondent à la demande, du plus probable au moins probable."""
    for champ, _, motif in _CARBURANTS:
        if re.search(motif, t):
            return [champ]
    if re.search(_ESSENCE, t):
        return ["e10", "sp95"]
    return []


def _prix_dit(prix):
    centimes = int(round(prix * 100))
    euros, reste = divmod(centimes, 100)
    if not euros:
        return f"{reste} centimes"
    return f"{euros} euro{'s' if euros > 1 else ''}" + (f" {reste:02d}" if reste else "")


def _stations(rayon):
    _, latitude, longitude = _ville()
    point = "geom'POINT({} {})'".format(longitude, latitude)
    requete = urllib.parse.urlencode({"where": "within_distance(geom, {}, {}km)".format(point, rayon),
                                      "order_by": "distance(geom, {})".format(point), "limit": 40})
    return _json(URL_CARBURANTS + requete).get("results") or []


def _age(releve):
    """Nombre de jours depuis le relevé du prix (le flux ne garantit que la date, pas l'heure)."""
    try:
        jour = datetime.date.fromisoformat(str(releve)[:10])
    except ValueError:
        return None
    return (datetime.date.today() - jour).days


def _moins_cheres(stations, champ):
    trouvees = []
    for station in stations:
        prix, age = station.get(champ + "_prix"), _age(station.get(champ + "_maj"))
        if isinstance(prix, (int, float)) and prix > 0 and age is not None and age <= AGE_MAX:
            trouvees.append((float(prix), age, station))
    return sorted(trouvees, key=lambda x: x[0])


def _lieu_station(station):
    ville = str(station.get("ville") or "").strip().title()
    adresse = re.sub(r"\s+", " ", str(station.get("adresse") or "")).strip().lower()
    return ville + (f", {adresse}" if adresse else "")


def _phrase_carburant(stations, champ):
    classees = _moins_cheres(stations, champ)
    if not classees:
        return None
    prix, age, station = classees[0]
    phrase = f"{_NOMS_CARBURANTS[champ]} le moins cher est à {_prix_dit(prix)}, à {_lieu_station(station)}"
    if age >= 2:
        phrase += f", prix relevé il y a {age} jours"
    suivante = next((s for s in classees[1:] if _lieu_station(s[2]) != _lieu_station(station)), None)
    if suivante:
        ville = str(station.get("ville") or "").strip().title()
        ville_suivante = str(suivante[2].get("ville") or "").strip().title()
        # même ville : on précise l'adresse, sinon les deux stations ont l'air d'être la même
        lieu = _lieu_station(suivante[2]) if ville_suivante == ville else ville_suivante
        if abs(suivante[0] - prix) < 0.005:
            phrase += f". Même prix à {lieu}"
        else:
            phrase += f". Ensuite, {_prix_dit(suivante[0])} à {lieu}"
    return phrase[0].upper() + phrase[1:] + "."


def commande_carburant(t):
    t = _debut(t)
    if _MON_CARBURANT.search(t):
        champs = _carburant_demande(t)
        if not champs:
            return None
        _regler("carburant", champs[0])
        return f"C'est noté : ton carburant, c'est {_NOMS_CARBURANTS[champs[0]]}."
    if not (_QUESTION_PRIX.search(t) and _MOT_CARBURANT.search(t)):
        return None
    champs = _carburant_demande(t)
    prefere = False
    if not champs:
        choisi = _lire().get("carburant")
        champs, prefere = ([choisi], True) if choisi in _NOMS_CARBURANTS else (["gazole", "e10"], False)
    try:
        stations = _stations(15) or _stations(30)
    except Exception as erreur:
        print("Carburants :", erreur)
        return "Je n'arrive pas à obtenir les prix des carburants pour le moment."
    ville = _ville()[0]
    if not stations:
        return f"Je ne trouve aucune station-service à moins de 30 kilomètres de {ville}."
    if prefere or len(champs) == 1 or re.search(_ESSENCE, t):
        for champ in champs:                       # « essence » : E10, sinon sans-plomb 95
            phrase = _phrase_carburant(stations, champ)
            if phrase:
                return f"Près de {ville} : {phrase[0].lower() + phrase[1:]}"
        return f"Aucune station près de {ville} n'affiche de prix récent pour {_NOMS_CARBURANTS[champs[0]]}."
    phrases = [p for p in (_phrase_carburant(stations, champ) for champ in champs) if p]
    if not phrases:
        return f"Aucune station près de {ville} n'affiche de prix récent."
    return f"Près de {ville}. " + " ".join(phrases)


# ---------- Vacances scolaires et jours fériés ----------

URL_VACANCES = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/records?"
URL_FERIES = "https://calendrier.api.gouv.fr/jours-feries/{}.json"
# Zone scolaire de chaque département (France métropolitaine) ; la Corse a son propre calendrier
_ZONES = {
    "Zone A": "25 39 70 90 24 33 40 47 64 03 15 43 63 21 58 71 89 07 26 38 73 74 19 23 87 01 42 69 16 17 79 86",
    "Zone B": ("04 05 13 84 02 60 80 59 62 54 55 57 88 44 49 53 72 85 06 83 14 27 50 61 76 18 28 36 37 41 45 "
               "08 10 51 52 22 29 35 56 67 68"),
    "Zone C": "77 93 94 11 30 34 48 66 75 09 12 31 32 46 65 81 82 78 91 92 95",
    "Corse": "2A 2B",
}
_VACANCES = re.compile(
    r"\bprochaines? vacances\b|\bvacances scolaires\b|\b(?:quand|combien)\b.{0,45}\bvacances\b|"
    r"\bvacances\b.{0,30}\b(?:quand|quelle date|dans combien)\b|"
    r"\b(?:on est|est-ce qu'on est|sommes[- ]nous|c'est|est-ce que c'est)(?: bient[oô]t| d[ée]j[aà])? (?:en|les) vacances\b|"
    r"\b(?:quand|quelle date|dans combien)\b.{0,35}\brentr[ée]e\b|\brentr[ée]e\b.{0,25}\b(?:quand|quelle date)\b")
_FERIE = re.compile(r"\bf[ée]ri[ée]s?\b")
_QUESTION_FERIE = re.compile(r"\b(prochains?|demain|aujourd'hui|quand|combien|est-ce que|est-ce qu'|reste-t-il|"
                             r"il reste|quels? sont|liste)\b")
# noms du calendrier officiel, dits naturellement (« c'est Noël », « c'est le lundi de Pâques »)
_NOMS_FERIES = {"Jour de Noël": "Noël", "Lundi de Pâques": "le lundi de Pâques", "Lundi de Pentecôte": "le lundi de Pentecôte",
                "Ascension": "l'Ascension", "Assomption": "l'Assomption", "Toussaint": "la Toussaint",
                "Vendredi saint": "le Vendredi saint", "14 juillet": "le 14 juillet, la fête nationale",
                "1er mai": "le 1er mai, la fête du Travail", "8 mai": "le 8 mai", "11 novembre": "le 11 novembre",
                "1er janvier": "le 1er janvier", "Lendemain de Noël": "le lendemain de Noël"}


def _nom_ferie(nom):
    return _NOMS_FERIES.get(str(nom).strip(), str(nom).strip())


def _zone():
    forcee = str(jarvis_config._lu.get("zone_scolaire") or "").strip().upper()
    if forcee in ("A", "B", "C"):
        return "Zone " + forcee
    if forcee == "CORSE":
        return "Corse"
    departement = _departement().upper().zfill(2)
    return next((zone for zone, liste in _ZONES.items() if departement in liste.split()), None)


def _lire_vacances(zone):
    aujourd_hui = datetime.date.today().isoformat()
    requete = urllib.parse.urlencode({"where": 'end_date >= "{}" and zones = "{}"'.format(aujourd_hui, zone),
                                      "order_by": "start_date", "limit": 100})
    periodes, vues = [], set()
    for ligne in _json(URL_VACANCES + requete).get("results") or []:
        nom = str(ligne.get("description") or "").strip()
        if not nom or nom.lower().startswith("pont") or str(ligne.get("population") or "-") not in ("-", "Élèves"):
            continue
        try:                                       # dates du flux en UTC : ramenées au jour d'ici
            debut = datetime.datetime.fromisoformat(ligne["start_date"]).astimezone().date()
            fin = datetime.datetime.fromisoformat(ligne["end_date"]).astimezone().date()
        except (KeyError, TypeError, ValueError):
            continue
        if (nom, debut) not in vues and fin > debut:
            vues.add((nom, debut))
            periodes.append([nom, debut.isoformat(), fin.isoformat()])     # fin = jour de la rentrée
    if not periodes:
        raise ValueError("aucune période publiée")
    return periodes


def _nom_vacances(nom):
    nom = nom[0].lower() + nom[1:]
    return re.sub(r"\b(no[eë]l|toussaint|p[aâ]ques)\b", lambda m: m.group(1).capitalize(), nom)


def commande_vacances(t):
    t = _debut(t)
    if _FERIE.search(t):
        return _commande_ferie(t) if _QUESTION_FERIE.search(t) else None
    if not _VACANCES.search(t):
        return None
    zone = _zone()
    if not zone:
        return ("Je ne connais pas ta zone scolaire. Dis-moi d'abord ta ville, par exemple : "
                "« ma ville est Toulouse ».")
    periodes, a_jour = _en_cache("vacances", zone, 12 * 3600, lambda: _lire_vacances(zone))
    if not periodes:
        return "Je n'arrive pas à consulter le calendrier scolaire pour le moment."
    aujourd_hui = datetime.date.today()
    periodes = [(nom, datetime.date.fromisoformat(d), datetime.date.fromisoformat(f)) for nom, d, f in periodes]
    periodes = sorted((p for p in periodes if p[2] > aujourd_hui), key=lambda p: p[1])
    if not periodes:
        return "Aucune période de vacances n'est encore publiée pour la suite."
    nom, debut, rentree = periodes[0]
    nom = _nom_vacances(nom)
    reserve = "" if a_jour else " C'est le dernier calendrier que je connais, à vérifier."
    la_zone = "en Corse" if zone == "Corse" else "en zone " + zone[-1]
    if debut <= aujourd_hui:
        return (f"Oui, ce sont les {nom}, {la_zone}. La rentrée, c'est {_jour_dit(rentree)}, "
                f"{_dans((rentree - aujourd_hui).days)}.{reserve}")
    dernier = rentree - datetime.timedelta(days=1)
    if re.search(r"\brentr[ée]e\b", t):
        return (f"La prochaine rentrée, c'est {_jour_dit(rentree)}, après les {nom}, "
                f"qui commencent {_jour_dit(debut)}.{reserve}")
    debut_phrase = "Non, pas encore. " if re.search(r"\b(?:on est|sommes[- ]nous|c'est)\b.{0,12}\bvacances\b", t) else ""
    return (f"{debut_phrase}Les prochaines vacances, {la_zone}, ce sont les {nom} : du {_jour_dit(debut)} au "
            f"{_jour_dit(dernier)}, {_dans((debut - aujourd_hui).days)}. Rentrée le {_jour_dit(rentree)}.{reserve}")


def _commande_ferie(t):
    region = "alsace-moselle" if _departement() in ("57", "67", "68") else "metropole"
    jours, a_jour = _en_cache("feries", region, 7 * 24 * 3600, lambda: _json(URL_FERIES.format(region)))
    if not jours:
        return "Je n'arrive pas à consulter les jours fériés pour le moment."
    aujourd_hui = datetime.date.today()
    reserve = "" if a_jour else " C'est la dernière liste que je connais, à vérifier."
    demande = (aujourd_hui + datetime.timedelta(days=1) if re.search(r"\bdemain\b", t)
               else aujourd_hui if re.search(r"\b(aujourd'hui|ce jour)\b", t) else None)
    if demande:
        quand = "Demain" if demande != aujourd_hui else "Aujourd'hui"
        nom = jours.get(demande.isoformat())
        if nom:
            return f"Oui. {quand}, {_jour_dit(demande)}, c'est férié : {_nom_ferie(nom)}.{reserve}"
        debut = f"Non, {quand.lower()} n'est pas férié. "
    else:
        debut = ""
    for date, nom in sorted(jours.items()):
        try:
            jour = datetime.date.fromisoformat(date)
        except ValueError:
            continue
        if jour > aujourd_hui or (jour == aujourd_hui and not demande):
            return (f"{debut}Le prochain jour férié, c'est {_nom_ferie(nom)}, {_jour_dit(jour)}, "
                    f"{_dans((jour - aujourd_hui).days)}.{reserve}")
    return debut + "Je ne connais pas encore les prochains jours fériés."


# ---------- Éphéméride (sélection de Wikipédia en français) ----------

URL_EPHEMERIDE = "https://fr.wikipedia.org/api/rest_v1/feed/onthisday/selected/{:02d}/{:02d}"
_EPHEMERIDE = re.compile(
    r"\b[ée]ph[ée]m[ée]rides?\b|\bun jour comme aujourd'hui\b|"
    r"\b(?:qu'est-ce qui s'est|qu'est-ce qu'il s'est|que s'est-il|ce qui s'est) pass[ée]\b.{0,20}"
    r"(?:\baujourd'hui\b|\b(?:un|le) \d{1,2}(?:er)? " + _MOIS_RE + r")")
_DATE_DITE = re.compile(r"\b(?:un|le) (?P<jour>\d{1,2})(?:er)? (?P<mois>" + _MOIS_RE[1:-1] + r")\b")
# en mode enfant, les événements violents ne sont pas racontés
_SOMBRE = re.compile(r"mort|tu[ée]|suicid|attentat|guerre|bataill|massacr|assassin|ex[ée]cut|bombard|g[ée]nocid|"
                     r"meurtr|viol|crash|accident|catastroph|s[ée]isme|tremblement|incendi|[ée]pid[ée]mi|terroris|"
                     r"otage|coup d'[ée]tat|d[ée]c[èe]s|d[ée]c[ée]d|victime|naufrag|explos|fusill|condamn|prison")


def _ordre_ephemeride(evenement, annee):
    """Les anniversaires les plus ronds d'abord (100 ans, 50, 25, 10, 5), puis les plus récents."""
    age = annee - evenement[0]
    rang = next((i for i, pas in enumerate((100, 50, 25, 10, 5)) if age > 0 and age % pas == 0), 5)
    return rang, age


def commande_ephemeride(t, enfant=False):
    t = _debut(t)
    if not _EPHEMERIDE.search(t):
        return None
    aujourd_hui = datetime.date.today()
    mois, jour, autre = aujourd_hui.month, aujourd_hui.day, False
    m = _DATE_DITE.search(t)
    if m:
        mois = next(i + 1 for i, nom in enumerate(MOIS) if _sans_accents(nom) == _sans_accents(m.group("mois")))
        jour = int(m.group("jour"))
        if jour > calendar.monthrange(2024, mois)[1]:
            return f"Il n'y a pas de {jour} {MOIS[mois - 1]}."
        autre = (mois, jour) != (aujourd_hui.month, aujourd_hui.day)

    def lire():
        choisis = _json(URL_EPHEMERIDE.format(mois, jour)).get("selected") or []
        return [[int(e["year"]), re.sub(r"\s*\((?:photo|image|illustration|ci-contre|portrait)[^)]*\)", "", str(e["text"])).strip()] for e in choisis
                if isinstance(e.get("year"), int) and e.get("text")]

    evenements, _ = _en_cache("ephemeride", f"{mois:02d}-{jour:02d}", 24 * 3600, lire)
    if evenements is None:
        return "Je n'arrive pas à consulter l'éphéméride pour le moment."
    if enfant:
        evenements = [e for e in evenements if not _SOMBRE.search(e[1].lower())]
    if not evenements:
        return "Je n'ai pas d'histoire à raconter pour ce jour-là."
    evenements.sort(key=lambda e: _ordre_ephemeride(e, aujourd_hui.year))
    annee, texte = evenements[0]
    texte = texte.rstrip(". ") + "."
    age = aujourd_hui.year - annee
    if autre:
        phrase = f"Un {'1er' if jour == 1 else jour} {MOIS[mois - 1]}, en {annee} : {texte}"
    else:
        phrase = f"Un jour comme aujourd'hui, il y a {age} an{'s' if age > 1 else ''}, en {annee} : {texte}"
    if len(evenements) > 1:
        annee2, texte2 = evenements[1]
        phrase += f" Et en {annee2} : {texte2.rstrip('. ')}."
    return phrase + " D'après Wikipédia."


# ---------- Poubelles : jours de ramassage dits à Jarvis, calculés sur ce PC ----------

_BAC = (r"(?:(?:les?|la|l'|des|mes|nos) ?)?(?:poubelles?|bacs?|conteneurs?|containers?|sacs?|ordures|verres?|emballages?|"
        r"encombrants?|d[ée]chets?|biod[ée]chets?|tri|recyclage|recyclables?|cartons?|papiers?)(?: [\w'-]+){0,3}?")
_REGLE = re.compile(
    r"^(?P<bac>" + _BAC + r") (?:(?:passe(?:nt)?|passera|se ramasse(?:nt)?|se sort(?:ent)?)|"
    r"(?:est|sont|c'est) (?:ramass[ée]e?s?|collect[ée]e?s?|sortie?s?)|c'est) "
    r"(?P<quand>.+)$")
_MOT_POUBELLE = re.compile(r"\b(poubelles?|bacs?|ordures|encombrants|ramassages?|collecte des d[ée]chets|"
                           r"conteneurs?|containers?)\b")
_QUESTION_POUBELLE = re.compile(r"\b(quelles?|quels?|quand|sortir|sors|sort|sortent|prochains?|ce soir|demain|aujourd'hui|"
                                r"passe(?:nt)?|ramass\w*)\b")
_PAS_POUR_MOI = re.compile(r"\b(rappelle|rappel|n'oublie pas|note que|minuteur|ajoute|retiens)\b")
_RANGS = [(1, r"1er|premiers?"), (2, r"2e|2[èe]me|deuxi[èe]mes?|seconds?"), (3, r"3e|3[èe]me|troisi[èe]mes?"),
          (4, r"4e|4[èe]me|quatri[èe]mes?"), (-1, r"derniers?")]
HEURE_RAPPEL = 18              # la veille du ramassage, à partir de cette heure


def _cle_bac(nom):
    """« les poubelles jaunes » -> « poubelle jaune » : pour retrouver un bac quelle que soit la façon de le dire."""
    nom = re.sub(r"^(?:les?|la|l'|des|mes|nos|du|de la|de l'|au|aux|à la) ?", "", _sans_accents(nom.lower()).strip())
    return " ".join(mot.rstrip("sx") if len(mot) > 3 else mot for mot in nom.split())


def _lire_regle(quand):
    """« le mercredi des semaines paires » -> jours, parité, rangs dans le mois. None si ce n'est pas compris."""
    q = " " + _sans_accents(quand.lower()) + " "
    jours = [i for i, nom in enumerate(JOURS) if re.search(r"\b" + nom + r"s?\b", q)]
    if not jours:
        return None
    if re.search(r"\b(une semaine sur deux|tous les quinze jours|toutes les deux semaines)\b", q):
        return "sur deux"
    parite = ("impaire" if re.search(r"\bimpaires?\b", q) else "paire" if re.search(r"\b(paires?|peres?|pair)\b", q) else None)
    rangs = [rang for rang, motif in _RANGS if re.search(r"\b(?:" + motif + r")\b", q)] if re.search(r"\bmois\b", q) else []
    return {"jours": jours, "parite": parite, "rangs": rangs}


def _passe_le(regle, jour):
    if jour.weekday() not in regle["jours"]:
        return False
    if regle.get("parite") and (jour.isocalendar()[1] % 2 == 0) != (regle["parite"] == "paire"):
        return False
    rangs = regle.get("rangs") or []
    if rangs:
        rang = (jour.day - 1) // 7 + 1
        dernier = jour.day + 7 > calendar.monthrange(jour.year, jour.month)[1]
        return rang in rangs or (-1 in rangs and dernier)
    return True


def _prochain(regle, depuis):
    for ecart in range(0, 100):
        jour = depuis + datetime.timedelta(days=ecart)
        if _passe_le(regle, jour):
            return jour
    return None


def _regle_dite(regle):
    jours = " et ".join("le " + JOURS[j] for j in regle["jours"])
    if regle.get("rangs"):
        noms = {1: "premier", 2: "deuxième", 3: "troisième", 4: "quatrième", -1: "dernier"}
        jours = " et ".join(noms[r] for r in regle["rangs"]) + " " + " et ".join(JOURS[j] for j in regle["jours"])
        jours = "le " + jours + " du mois"
    return jours + (f", les semaines {regle['parite']}s" if regle.get("parite") else "")


def _bacs():
    bacs = _lire().get("bacs")
    return bacs if isinstance(bacs, dict) else {}


def _enumerer(noms):
    noms = list(noms)
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def _ramassages(depuis):
    """Liste triée de (jour, [noms des bacs]) pour les prochains ramassages."""
    par_jour = {}
    for bac in _bacs().values():
        jour = _prochain(bac, depuis)
        if jour:
            par_jour.setdefault(jour, []).append(bac["nom"])
    return sorted(par_jour.items())


def _bac_cite(t):
    cles = _cle_bac(t).split()
    for cle, bac in _bacs().items():
        mots = cle.split()
        if all(mot in cles for mot in mots) or (len(mots) > 1 and mots[-1] in cles and mots[0] in ("poubelle", "bac", "sac")):
            return cle, bac
    return None, None


def commande_poubelles(t):
    t = _debut(t)
    # Rappels de la veille : « arrête les rappels de poubelles », « remets les rappels de poubelles »
    if _MOT_POUBELLE.search(t) and re.search(
            r"\b(?:arr[êe]te|d[ée]sactive|coupe|supprime)\b.{0,20}\b(?:rappels?|annonces?)\b|"
            r"\bne me (?:pr[ée]viens|dis|rappelle) plus\b|\bplus besoin de me pr[ée]venir\b", t):
        _regler("poubelles_muet", True)
        return "D'accord, je ne t'annoncerai plus les poubelles la veille. Tu peux toujours me les demander."
    if _MOT_POUBELLE.search(t) and re.search(
            r"\b(?:remets|r[ée]active|active|relance)\b.{0,20}\b(?:rappels?|annonces?)\b|\bpr[ée]viens[- ]moi\b.{0,25}\bveille\b", t):
        _regler("poubelles_muet", False)
        return "D'accord, je t'annoncerai de nouveau les poubelles la veille au soir."
    if _PAS_POUR_MOI.search(t):
        return None
    aujourd_hui = datetime.date.today()
    # Réglage : « la poubelle jaune passe le mercredi des semaines paires »
    m = _REGLE.match(t)
    if m and not re.search(r"\b(quand|quel|quelle)\b", t):
        regle = _lire_regle(m.group("quand"))
        if regle == "sur deux":
            return ("Pour un ramassage une semaine sur deux, dis-moi si ce sont les semaines paires ou impaires : "
                    f"cette semaine est la semaine {aujourd_hui.isocalendar()[1]}.")
        if regle:
            nom = re.sub(r"\s+", " ", m.group("bac")).strip()
            if not re.match(r"(?:les?|la|l'|des|mes|nos) ?", nom):
                nom = ("les " if nom.endswith("s") else "le ") + nom
            nom = re.sub(r"^(?:des|mes|nos) ", "les ", nom)
            regle["nom"] = nom
            with _verrou:
                donnees = _lire()
                bacs = donnees.get("bacs") if isinstance(donnees.get("bacs"), dict) else {}
                bacs[_cle_bac(nom)] = regle
                donnees["bacs"] = bacs
                _ecrire(donnees)
            prochain = _prochain(regle, aujourd_hui)
            return (f"C'est noté : {nom}, {_regle_dite(regle)}. Prochain ramassage {_jour_dit(prochain)}. "
                    "Je te le rappellerai la veille au soir.")
    cle, bac = _bac_cite(t)
    # Oubli : « oublie la poubelle jaune »
    if bac and re.search(r"\b(oublie|supprime|enl[èe]ve|retire|efface)\b", t):
        with _verrou:
            donnees = _lire()
            (donnees.get("bacs") or {}).pop(cle, None)
            _ecrire(donnees)
        return f"C'est oublié : je ne compte plus {bac['nom']}."
    question = _QUESTION_POUBELLE.search(t)
    if not question or not (_MOT_POUBELLE.search(t) or (bac and re.search(r"\b(quand|passe(?:nt)?|ramass\w*|sortir|sors)\b", t))):
        return None
    if not _bacs():
        return ("Je ne connais pas encore tes jours de ramassage. Dis-moi par exemple : "
                "« la poubelle jaune passe le mercredi des semaines paires ».")
    if re.search(r"\b(quels sont|donne[- ]moi|dis[- ]moi|rappelle[- ]moi)\b.{0,25}\bjours\b|\bjours de (?:ramassage|collecte|passage)\b", t):
        return "Voici ce que je connais : " + " ; ".join(f"{b['nom']}, {_regle_dite(b)}" for b in _bacs().values()) + "."
    if bac and not re.search(r"\b(quelles?|quels?) (poubelles?|bacs?)\b", t):
        jour = _prochain(bac, aujourd_hui)
        ecart = (jour - aujourd_hui).days
        phrase = f"{bac['nom'][0].upper() + bac['nom'][1:]} : prochain ramassage {_jour_dit(jour)}, {_dans(ecart)}."
        return phrase + (" Il faut les sortir ce soir." if ecart == 1 else "")
    depuis = aujourd_hui if time.localtime().tm_hour < 12 else aujourd_hui + datetime.timedelta(days=1)
    prevus = _ramassages(depuis)
    if not prevus:
        return "Je ne trouve aucun ramassage à venir."
    jour, noms = prevus[0]
    ecart = (jour - aujourd_hui).days
    if ecart == 0:
        phrase = f"Aujourd'hui, c'est le ramassage pour {_enumerer(noms)}."
    elif ecart == 1:
        phrase = f"Ce soir, il faut sortir {_enumerer(noms)} : ramassage demain, {_jour_dit(jour, False)}."
    else:
        phrase = f"Rien à sortir ce soir. Prochain ramassage {_jour_dit(jour)}, {_dans(ecart)} : {_enumerer(noms)}."
    if len(prevus) > 1:
        phrase += f" Ensuite, {_enumerer(prevus[1][1])}, {_jour_dit(prevus[1][0])}."
    return phrase


def surveiller_poubelles(annoncer):
    """La veille d'un ramassage, à partir de 18 heures : rappelle une seule fois quels bacs sortir."""
    def boucle():
        time.sleep(120)
        while True:
            try:
                donnees = _lire()
                aujourd_hui = datetime.date.today()
                if (not donnees.get("poubelles_muet") and donnees.get("poubelles_annonce") != aujourd_hui.isoformat()
                        and time.localtime().tm_hour >= HEURE_RAPPEL and _bacs()):
                    demain = aujourd_hui + datetime.timedelta(days=1)
                    noms = [bac["nom"] for bac in _bacs().values() if _passe_le(bac, demain)]
                    _regler("poubelles_annonce", aujourd_hui.isoformat())
                    if noms:
                        annoncer(f"Pense à sortir {_enumerer(noms)} ce soir : le ramassage, c'est demain.")
            except Exception as erreur:
                print("Poubelles :", erreur)
            time.sleep(600)
    threading.Thread(target=boucle, daemon=True).start()


# ---------- Point d'entrée ----------

def commande(t, enfant=False):
    """Essaie chaque information ; None si la demande ne concerne aucune d'elles."""
    return (commande_poubelles(t) or commande_vacances(t) or commande_carburant(t)
            or commande_ephemeride(t, enfant=enfant))
