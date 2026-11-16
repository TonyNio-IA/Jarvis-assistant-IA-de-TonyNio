"""
JARVIS - commandes instantanées.

Ces demandes simples sont traitées directement sur le PC, sans passer par Claude :
la réponse est immédiate et ton quota Claude est économisé.
  - l'heure et la date ;
  - la météo (aujourd'hui, demain, après-demain), par le service gratuit Open-Meteo ;
  - le volume (monter, baisser, régler à un pourcentage, couper, remettre) ;
  - la musique ou la vidéo en cours (pause, lecture, suivant, précédent) ;
  - les minuteurs et rappels (« rappelle-moi dans 20 minutes de sortir le linge ») ;
  - ouvrir une application ou un dossier courant, verrouiller le PC.
Tout ce qui n'est pas reconnu ici est envoyé à Claude, comme avant.
"""

import ctypes
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

PAS_VOLUME = 10   # pourcentage ajouté ou retiré par « monte le son » / « baisse le son »

# Ville utilisée quand tu demandes la météo sans préciser d'endroit
VILLE_DEFAUT = ("Paris", 48.8566, 2.3522)
DELAI_METEO = 5   # secondes maximum pour obtenir la météo, sinon la demande part à Claude

DOSSIER_PERSO = os.path.expanduser("~")

# mots-clés -> (ce qu'il faut ouvrir, nom prononcé)
APPLICATIONS = [
    (r"chrome|navigateur|google", "chrome", "Chrome"),
    (r"calculatrice|calculette", "calc", "la calculatrice"),
    (r"bloc[- ]?notes?", "notepad", "le bloc-notes"),
    (r"gestionnaire des t[aâ]ches", "taskmgr", "le gestionnaire des tâches"),
    (r"param[eè]tres|r[eé]glages", "ms-settings:", "les paramètres"),
    (r"t[eé]l[eé]chargements?", os.path.join(DOSSIER_PERSO, "Downloads"), "tes téléchargements"),
    (r"documents?", os.path.join(DOSSIER_PERSO, "Documents"), "tes documents"),
    (r"images?|photos?", os.path.join(DOSSIER_PERSO, "Pictures"), "tes images"),
    (r"explorateur|mes fichiers|fichiers", "explorer", "l'explorateur de fichiers"),
    (r"youtube", "https://www.youtube.com", "YouTube"),
]

# ---------- Nombres dits en toutes lettres ----------

_VALEURS = {"zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
            "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
            "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20,
            "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
            "cent": 100}


def _nombre_fin(mots):
    """Nombre situé à la fin d'une liste de mots (« ... vingt et une » -> 21)."""
    if not mots:
        return None
    if mots[-1].isdigit():
        return int(mots[-1])
    suite = []
    for mot in reversed(mots):
        if mot in _VALEURS or (mot == "et" and suite):
            suite.insert(0, mot)
        else:
            break
    total, vu = 0, False
    for mot in suite:
        if mot == "et":
            continue
        v = _VALEURS[mot]
        if v == 20 and total % 100 == 4:
            total += 76                  # quatre-vingt = 80
        else:
            total += v
        vu = True
    return total if vu else None


def _mots(t):
    return re.findall(r"\d+|[a-zàâäçéèêëîïôöùûüœ]+", t.replace("-", " "))


def _nombre(t):
    """Premier nombre trouvé dans la phrase, en chiffres ou en lettres."""
    mots = _mots(t)
    for i in range(1, len(mots) + 1):
        if mots[i - 1].isdigit() or mots[i - 1] in _VALEURS:
            j = i
            while j < len(mots) and (mots[j] in _VALEURS or mots[j] == "et"):
                j += 1
            return _nombre_fin(mots[:j])
    return None


# ---------- Heure et date ----------

def _heure():
    t = time.localtime()
    h, m = t.tm_hour, t.tm_min
    if h == 0:
        debut = "minuit"
    elif h == 12:
        debut = "midi"
    else:
        debut = f"{h} heure{'s' if h > 1 else ''}"
    return f"Il est {debut}{f' {m}' if m else ''}."


def _date():
    t = time.localtime()
    jour = "premier" if t.tm_mday == 1 else str(t.tm_mday)
    return f"Nous sommes le {JOURS[t.tm_wday]} {jour} {MOIS[t.tm_mon - 1]} {t.tm_year}."


# ---------- Météo (Open-Meteo, gratuit, sans clé) ----------

_CIEL = {0: "ciel dégagé", 1: "ciel peu nuageux", 2: "ciel partiellement nuageux", 3: "ciel couvert",
         45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine",
         55: "bruine forte", 56: "bruine verglaçante", 57: "bruine verglaçante",
         61: "pluie faible", 63: "pluie", 65: "forte pluie", 66: "pluie verglaçante",
         67: "pluie verglaçante", 71: "neige faible", 73: "neige", 75: "fortes chutes de neige",
         77: "neige en grains", 80: "averses", 81: "averses", 82: "fortes averses",
         85: "averses de neige", 86: "fortes averses de neige", 95: "orages",
         96: "orages avec grêle", 99: "orages avec grêle"}


def _json(url):
    with urllib.request.urlopen(url, timeout=DELAI_METEO) as reponse:
        return json.load(reponse)


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _lieu(nom):
    """Renvoie (nom, latitude, longitude), ou None si la ville n'est pas trouvée."""
    if not nom or _sans_accents(nom) in (_sans_accents(VILLE_DEFAUT[0]), "pari"):
        return VILLE_DEFAUT
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=5&language=fr&format=json&name="
           + urllib.parse.quote(nom))
    resultats = _json(url).get("results") or []
    if not resultats:
        return None
    choix = next((r for r in resultats if r.get("country_code") == "FR"), resultats[0])
    return choix["name"], choix["latitude"], choix["longitude"]


def _arrondi(x):
    return str(int(round(x)))


def _commande_meteo(t, brut):
    if not re.search(r"\b(météo|meteo|quel temps|temps qu'il fait|temps fait)\b", t):
        return None
    # Demande composée (« ouvre Chrome et cherche la météo ») : pour Claude
    if re.search(r"\b(ouvre|lance|cherche|recherche|site|page)\b", t):
        return None
    # Demandes plus fines (semaine, week-end, ce soir, un jour précis...) : pour Claude
    if re.search(r"\b(semaine|week|weekend|soir|nuit|matin|midi|heures?|" + "|".join(JOURS) + r")\b", t):
        return None
    jour = 2 if re.search(r"après[- ]demain", t) else 1 if "demain" in t else 0
    ville = None
    m = re.search(r"\b(?:à|au|aux|sur)\s+(?!demain|aujourd)([a-zA-ZÀ-ÿ' \-]+)", brut.strip(" .!?"))
    if m:
        ville = re.split(r"\s+(?:demain|après|aujourd'hui|s'il|stp|pour)\b", m.group(1))[0].strip()
    lieu = _lieu(ville)
    if lieu is None:
        return None
    nom, lat, lon = lieu
    d = _json("https://api.open-meteo.com/v1/forecast?"
              f"latitude={lat}&longitude={lon}"
              "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
              "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
              "&timezone=auto&forecast_days=3")
    q = d["daily"]
    mini, maxi = _arrondi(q["temperature_2m_min"][jour]), _arrondi(q["temperature_2m_max"][jour])
    pluie = q["precipitation_probability_max"][jour]
    pluie = f"Risque de pluie de {_arrondi(pluie)} pour cent." if pluie is not None else ""
    if jour == 0:
        c = d["current"]
        ciel = _CIEL.get(c["weather_code"], "temps variable")
        return (f"À {nom}, il fait {_arrondi(c['temperature_2m'])} degrés, {ciel}, "
                f"avec un vent de {_arrondi(c['wind_speed_10m'])} kilomètres heure. "
                f"Aujourd'hui, les températures vont de {mini} à {maxi} degrés. {pluie}").strip()
    quand = "Demain" if jour == 1 else "Après-demain"
    ciel = _CIEL.get(q["weather_code"][jour], "temps variable")
    return f"{quand} à {nom} : {ciel}, de {mini} à {maxi} degrés. {pluie}".strip()


# ---------- Volume et lecture ----------

def _volume():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def _commande_volume(t):
    if not re.search(r"\b(son|volume|sourdine|muet)\b", t):
        return None
    v = _volume()
    actuel = round(v.GetMasterVolumeLevelScalar() * 100)
    if re.search(r"\b(remets|remet|réactive|rétablis|rallume)\b", t):
        v.SetMute(0, None)
        return f"Le son est remis, à {actuel} pour cent."
    if re.search(r"\b(coupe|couper|sourdine|muet|mute)\b", t):
        v.SetMute(1, None)
        return "Le son est coupé."
    nombre = _nombre(t)
    if nombre is not None and re.search(r"\b(à|a|sur)\b", t):
        cible = max(0, min(100, nombre))
    elif re.search(r"\b(monte|monter|augmente|augmenter|plus fort)\b", t):
        cible = min(100, actuel + PAS_VOLUME)
    elif re.search(r"\b(baisse|baisser|diminue|diminuer|moins fort)\b", t):
        cible = max(0, actuel - PAS_VOLUME)
    elif re.search(r"\b(quel|combien)\b", t):
        return f"Le volume est à {actuel} pour cent."
    else:
        return None
    v.SetMute(0, None)
    v.SetMasterVolumeLevelScalar(cible / 100, None)
    return f"Volume à {cible} pour cent."


def _touche(code):
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)


def _commande_lecture(t):
    media = r"(musique|chanson|morceau|piste|titre|vidéo|video|lecture)"
    if re.search(rf"\b(suivante?|prochaine?)\b", t) and re.search(rf"\b{media}\b", t):
        _touche(0xB0)
        return "Suivant."
    if re.search(r"\bprécédente?\b", t) and re.search(rf"\b{media}\b", t):
        _touche(0xB1)
        return "Précédent."
    if re.search(rf"\b(pause|reprends|relance|remets|arrête|stoppe)\b.*\b{media}\b", t) \
            or re.search(r"^(mets (en )?pause|pause|lecture)$", t):
        _touche(0xB3)
        return "C'est fait."
    return None


# ---------- Minuteurs et rappels ----------

def _duree(t):
    """Durée en secondes trouvée dans la phrase, ou None."""
    total, trouve = 0, False
    if re.search(r"\bdemi[- ]heure\b", t):
        total, trouve = total + 1800, True
    if re.search(r"\bquart d'heure\b", t):
        total, trouve = total + 900, True
    mots = _mots(t)
    for i, mot in enumerate(mots):
        unite = (3600 if mot in ("heure", "heures") else 60 if mot in ("minute", "minutes")
                 else 1 if mot in ("seconde", "secondes") else None)
        if unite and i > 0 and mots[i - 1] not in ("demi", "d"):
            n = _nombre_fin(mots[:i])
            if n is not None:
                total, trouve = total + n * unite, True
                if unite == 3600 and i + 1 < len(mots):
                    suite = mots[i + 1:]
                    if suite[:2] == ["et", "demie"] or suite[:2] == ["et", "demi"]:
                        total += 1800
                    elif (suite[0].isdigit() or suite[0] in _VALEURS) and not any(
                            m in ("minute", "minutes", "seconde", "secondes") for m in suite[:4]):
                        j = 1
                        while j < len(suite) and (suite[j] in _VALEURS or suite[j] == "et"):
                            j += 1
                        total += (_nombre_fin(suite[:j]) or 0) * 60
    return total if trouve and total > 0 else None


def _duree_parlee(s):
    h, reste = divmod(s, 3600)
    m, sec = divmod(reste, 60)
    parties = []
    if h:
        parties.append(f"{h} heure{'s' if h > 1 else ''}")
    if m:
        parties.append(f"{m} minute{'s' if m > 1 else ''}")
    if sec:
        parties.append(f"{sec} seconde{'s' if sec > 1 else ''}")
    return " et ".join(parties)


def _commande_minuteur(t, annoncer):
    if annoncer is None or not re.search(
            r"\b(minuteur|compte à rebours|rappelle|rappel|préviens|réveille)\b", t):
        return None
    duree = _duree(t)
    if duree is None or duree > 24 * 3600:
        return None
    m = re.search(r"\b(?:minutes?|secondes?|heures?)\s+(?:de |d'|que |qu')(.+)$", t)
    if m:
        message = "Rappel : " + m.group(1).strip() + "."
    else:
        message = f"Le minuteur de {_duree_parlee(duree)} est terminé."
    minuteur = threading.Timer(duree, annoncer, args=(message,))
    minuteur.daemon = True
    minuteur.start()
    return f"C'est noté, je te préviens dans {_duree_parlee(duree)}."


# ---------- Applications ----------

def _commande_ouvrir(t):
    m = re.search(r"\b(ouvre|ouvrir|ouvres|lance|lancer|lances|démarre|démarrer)\b(.*)", t)
    if not m:
        return None
    reste = m.group(2)
    # Une demande plus complexe (« ouvre Chrome et cherche... ») reste pour Claude
    if re.search(r"\b(et|puis|pour|avec|sur|dans)\b", reste):
        return None
    for motif, cible, nom in APPLICATIONS:
        if re.search(rf"\b(?:{motif})\b", reste):
            os.startfile(cible)
            return f"J'ouvre {nom}."
    return None


def _commande_verrouiller(t):
    if re.search(r"\bverrouille\w*\b.*\b(pc|ordinateur|ordi|session|écran)\b", t):
        ctypes.windll.user32.LockWorkStation()
        return "Je verrouille l'ordinateur."
    return None


# ---------- Point d'entrée ----------

def _propre(brut):
    return brut.lower().replace("’", "'").strip(" .!?")


def sans_whisper(texte_vosk):
    """Vrai si la phrase entendue est une commande simple, comprise sans la
    retranscription précise (Whisper) : on gagne environ 2 secondes."""
    t = _propre(texte_vosk)
    if re.search(r"\b(cherche|recherche|puis)\b", t):
        return False
    if re.search(r"\b(quelle heure|quel jour|quelle date|point du jour|nouvelle conversation|"
                 r"oublie tout|répète|verrouille)\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t):
        return True
    if re.search(r"\b(son|volume|sourdine)\b", t):
        return True
    if re.search(r"\b(météo|quel temps)\b", t) and not re.search(r"\b(à|au|aux|sur|et)\s+\w", t):
        return True
    if re.search(r"\b(ouvre|lance)\b", t) and not re.search(r"\b(et|puis|pour|avec|sur|dans)\b", t):
        return any(re.search(rf"\b(?:{motif})\b", t) for motif, _, _ in APPLICATIONS)
    return False


def commande_instantanee(textes, annoncer=None):
    """
    textes   : les retranscriptions de la demande (Whisper et Vosk).
    annoncer : fonction appelée plus tard avec un texte à dire (minuteurs).
    Renvoie la réponse à dire, ou None si la demande doit aller à Claude.
    """
    for brut in textes:
        if not brut:
            continue
        t = _propre(brut)
        try:
            if re.search(r"\bquelle heure\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t):
                return _heure()
            if re.search(r"\b(quel jour|quelle date|on est le combien|nous sommes le combien)\b", t) \
                    and not re.search(r"\b(sera|était|demain|hier)\b", t):
                return _date()
            for commande in (lambda: _commande_minuteur(t, annoncer),
                             lambda: _commande_meteo(t, brut),
                             lambda: _commande_volume(t),
                             lambda: _commande_lecture(t),
                             lambda: _commande_ouvrir(t),
                             lambda: _commande_verrouiller(t)):
                reponse = commande()
                if reponse:
                    return reponse
        except Exception as erreur:
            print("Commande instantanée impossible :", erreur)
            return None
    return None
