"""
JARVIS - commandes instantanées.

Ces demandes simples sont traitées directement sur le PC, sans passer par Claude :
la réponse est immédiate et ton quota Claude est économisé.
  - l'heure et la date ;
  - la météo (aujourd'hui, demain, après-demain), par le service gratuit Open-Meteo ;
  - le volume (monter, baisser, régler à un pourcentage, couper, remettre) ;
  - la musique ou la vidéo en cours (pause, lecture, suivant, précédent) ;
  - les minuteurs et rappels (« rappelle-moi dans 20 minutes de sortir le linge ») ;
  - ouvrir une application ou un dossier courant, verrouiller le PC ;
  - l'état du PC (processeur, mémoire, programme le plus gourmand, place sur le disque) ;
  - les notes (« note que le plombier passe jeudi », « lis mes notes ») ;
  - les rappels à heure fixe (« rappelle-moi à 18 h d'appeler le garage »,
    « réveille-moi demain à 7 h »), gardés même si le PC redémarre ;
  - fermer une application, faire une capture d'écran, chercher un fichier ;
  - éteindre, redémarrer ou mettre en veille le PC, toujours après confirmation ;
  - les routines « bonjour » (date, météo, rappels du jour, état du PC) et « bonne nuit » ;
  - la dictée (« dicte : je serai là dans dix minutes ») dans la fenêtre active ;
  - la musique et les vidéos sur YouTube (« mets Get Lucky de Daft Punk ») ;
  - la mémoire durable (« retiens que... », « qu'est-ce que tu as retenu ? », « oublie que... ») ;
  - les fenêtres (« mets Imou en plein écran », « réduis la fenêtre », « mets Chrome à gauche »,
    « ferme la fenêtre », « affiche le bureau »), voir jarvis_fenetres.py.
Les applications que tu ouvres souvent sont retenues (applications.json) : Jarvis les reconnaît
ensuite même quand leur nom est mal entendu (« immo » pour Imou).
Tout ce qui n'est pas reconnu ici est envoyé à Claude, comme avant.
"""

import ctypes
import datetime
import difflib
import json
import os
import re
import subprocess
import threading
import time

import jarvis_config
import jarvis_ecran
import jarvis_fenetres
import jarvis_memoire
import urllib.parse
import urllib.request

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

PAS_VOLUME = 10   # pourcentage ajouté ou retiré par « monte le son » / « baisse le son »

# Ville utilisée quand tu demandes la météo sans préciser d'endroit.
# Elle se règle dans le fichier ville.txt (dans le dossier de Jarvis), qui reste sur ce PC (jamais envoyé sur GitHub) :
#   ligne 1 : Nom;latitude;longitude        (exemple : Paris;48.8566;2.3522)
#   ligne 2 : précision facultative          (exemple : en Île-de-France)
#   ligne 3 : noms de lieux à bien reconnaître, séparés par des virgules (facultatif)
FICHIER_VILLE = jarvis_config.chemin("ville.txt")


def _charger_ville():
    ville, precision, lieux = ("Paris", 48.8566, 2.3522), "", ""
    try:
        with open(FICHIER_VILLE, encoding="utf-8-sig") as f:
            lignes = [ligne.strip() for ligne in f.read().splitlines()]
        nom, latitude, longitude = [morceau.strip() for morceau in lignes[0].split(";")]
        ville = (nom, float(latitude.replace(",", ".")), float(longitude.replace(",", ".")))
        precision = lignes[1] if len(lignes) > 1 else ""
        lieux = lignes[2] if len(lignes) > 2 else ""
    except (OSError, ValueError, IndexError):
        pass
    return ville, precision, lieux


VILLE_DEFAUT, VILLE_PRECISION, LIEUX_CONNUS = _charger_ville()
DELAI_METEO = 5   # secondes maximum pour obtenir la météo, sinon la demande part à Claude

DOSSIER_PERSO = os.path.expanduser("~")
FICHIER_NOTES = jarvis_config.chemin("notes.txt")
FICHIER_RAPPELS = jarvis_config.chemin("rappels.json")
DELAI_EXTINCTION = 30    # secondes entre la confirmation et l'extinction (le temps d'annuler)
DELAI_CONFIRMATION = 20  # secondes pour répondre « oui » à une demande de confirmation
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PRENOM = jarvis_config.PRENOM      # se règle dans config.json
MUSIQUE_PAR_DEFAUT = "musique du moment playlist"   # lancée par « mets de la musique » sans précision

# applications que Jarvis peut fermer : mots-clés -> (programme, nom prononcé)
A_FERMER = [
    (r"chrome|navigateur|google", "chrome.exe", "Chrome"),
    (r"calculatrice|calculette", "CalculatorApp.exe", "la calculatrice"),
    (r"bloc[- ]?notes?", "notepad.exe", "le bloc-notes"),
    (r"gestionnaire des t[aâ]ches", "Taskmgr.exe", "le gestionnaire des tâches"),
    (r"param[eè]tres|r[eé]glages", "SystemSettings.exe", "les paramètres"),
]

_ETAT_PC = (r"\b(état|etat)\b.*\b(pc|ordinateur|ordi|système|systeme)\b"
            r"|comment va (le pc|l'ordinateur|l'ordi)"
            r"|\b(charge|utilisation) (du processeur|de la mémoire)\b"
            r"|pourquoi .*\b(rame|lent|ralenti\w*)\b"
            r"|qu'est-ce qui (rame|ralentit|consomme)")
_LIRE_NOTES = r"\b(lis|relis|lire|quelles sont|dis-moi)\b.*\bnotes?\b"

# mots-clés -> (ce qu'il faut ouvrir, nom prononcé)
APPLICATIONS = [
    (r"d[eé]marrage", "shell:startup", "le dossier de démarrage"),
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
    defaut = _sans_accents(VILLE_DEFAUT[0])
    if not nom or _sans_accents(nom) in (defaut, defaut[:-1]):   # la dernière lettre est parfois mal entendue
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
            or re.search(rf"\b{media}\b.*\b(en pause|sur pause)\b", t) \
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


# ----- Rappels : gardés dans un fichier, donc conservés si le PC ou Jarvis redémarre -----

_verrou_rappels = threading.Lock()


def _lire_rappels():
    try:
        with open(FICHIER_RAPPELS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _ecrire_rappels(rappels):
    with open(FICHIER_RAPPELS, "w", encoding="utf-8") as f:
        json.dump(rappels, f, ensure_ascii=False, indent=1)


def _ajouter_rappel(quand, message):
    with _verrou_rappels:
        rappels = _lire_rappels()
        rappels.append({"quand": quand, "message": message, "debut": time.time()})
        _ecrire_rappels(rappels)


def prochain_rappel():
    """Le prochain minuteur ou rappel : (moment prévu, moment de création, message), ou None."""
    rappels = [r for r in _lire_rappels() if r.get("quand", 0) > time.time()]
    if not rappels:
        return None
    r = min(rappels, key=lambda x: x["quand"])
    return r["quand"], r.get("debut", r["quand"] - 3600), r.get("message", "")


def _heure_parlee(h, m):
    if h == 0 and m == 0:
        return "minuit"
    if h == 12 and m == 0:
        return "midi"
    return f"{h} heure{'s' if h > 1 else ''}{f' {m}' if m else ''}"


def demarrer_rappels(annoncer):
    """Surveille les rappels en arrière-plan et les fait dire par « annoncer »."""
    def boucle():
        while True:
            maintenant = time.time()
            try:
                with _verrou_rappels:
                    rappels = _lire_rappels()
                    dus = [r for r in rappels if r["quand"] <= maintenant]
                    if dus:
                        _ecrire_rappels([r for r in rappels if r["quand"] > maintenant])
                for r in dus:
                    if maintenant - r["quand"] > 120:      # le PC était éteint à ce moment-là
                        t = time.localtime(r["quand"])
                        annoncer(f"Tu avais un rappel prévu à {_heure_parlee(t.tm_hour, t.tm_min)}, "
                                 f"pendant que j'étais éteint. {r['message']}")
                    else:
                        annoncer(r["message"])
            except Exception as erreur:
                print("Rappels :", erreur)
            time.sleep(2)
    threading.Thread(target=boucle, daemon=True).start()


def _commande_minuteur(t, annoncer):
    if not re.search(r"\b(minuteur|compte à rebours|rappelle|rappel|préviens|réveille)\b", t):
        return None
    # « un rappel à 13 h 56 » donne une heure, pas une durée : ce n'est pas un minuteur
    if re.search(r"\b(à|a)\s+(\d|\S+\s+heures?\b)", t) and not re.search(r"\bdans\b|\bminuteur\b|compte à rebours", t):
        return None
    duree = _duree(t)
    if duree is None or duree > 24 * 3600:
        return None
    m = re.search(r"\b(?:minutes?|secondes?|heures?)\s+(?:de |d'|que |qu')(.+)$", t)
    if m:
        message = "Rappel : " + m.group(1).strip() + "."
    else:
        message = f"Le minuteur de {_duree_parlee(duree)} est terminé."
    _ajouter_rappel(time.time() + duree, message)
    return f"C'est noté, je te préviens dans {_duree_parlee(duree)}."


def _heure_fixe(t):
    """Heure dite dans la phrase (« à 18h30 », « à sept heures et demie », « à midi ») -> (h, m)."""
    if re.search(r"\bmidi\b", t):
        h, m = 12, 30 if re.search(r"midi et demie?", t) else 0
    elif re.search(r"\bminuit\b", t):
        h, m = 0, 30 if re.search(r"minuit et demie?", t) else 0
    else:
        mots = _mots(t)
        for i, mot in enumerate(mots):
            if mot not in ("h", "heure", "heures") or i == 0:
                continue
            if "dans" in mots[max(0, i - 4):i]:
                return None                      # « dans 2 heures » : c'est une durée
            h = _nombre_fin(mots[:i])
            if h is None or h > 23:
                continue
            suite, m = mots[i + 1:], 0
            if suite[:2] in (["et", "demie"], ["et", "demi"]):
                m = 30
            elif suite[:2] == ["et", "quart"]:
                m = 15
            elif suite and (suite[0].isdigit() or suite[0] in _VALEURS):
                j = 1
                while j < len(suite) and (suite[j] in _VALEURS or suite[j] == "et"):
                    j += 1
                m = _nombre_fin(suite[:j]) or 0
                if m > 59:
                    m = 0
            break
        else:
            return None
    if h < 12 and re.search(r"\b(du soir|de l'après[- ]midi)\b", t):
        h += 12
    return h, m


def _commande_rappel(t):
    if not re.search(r"\b(rappelle|rappels?|préviens|réveille|reveille|réveil|alarmes?|minuteurs?)\b", t):
        return None
    if re.search(r"\b(annule|supprime|efface|enlève)\b.*\b(rappels?|minuteurs?|alarmes?|réveil)\b", t):
        with _verrou_rappels:
            nombre = len(_lire_rappels())
            _ecrire_rappels([])
        return (f"J'ai annulé {nombre} rappel{'s' if nombre > 1 else ''}." if nombre
                else "Tu n'avais aucun rappel.")
    if re.search(r"\b(quels|quelles|liste|lis|dis-moi|ai-je|j'ai)\b.*\b(rappels?|minuteurs?|alarmes?)\b", t):
        rappels = sorted(_lire_rappels(), key=lambda r: r["quand"])
        if not rappels:
            return "Tu n'as aucun rappel."
        phrases = []
        for r in rappels[:5]:
            q = time.localtime(r["quand"])
            jour = "" if q.tm_yday == time.localtime().tm_yday else "demain " \
                if q.tm_yday == time.localtime(time.time() + 86400).tm_yday else f"le {q.tm_mday} "
            phrases.append(f"{jour}à {_heure_parlee(q.tm_hour, q.tm_min)} : {r['message']}")
        return f"Tu as {len(rappels)} rappel{'s' if len(rappels) > 1 else ''}. " + " ".join(phrases)
    if not re.search(r"\b(rappelle|préviens|réveille|reveille|alarme|réveil|rappel)\b", t):
        return None
    if re.search(r"\bdans\b", t) and not re.search(r"\b(à|a)\s+\d|\bheures?\b.*\bdans\b", t):
        return None                              # « un rappel dans 20 minutes » : c'est un minuteur
    if not re.search(r"\b(à|a|demain|midi|minuit|ce soir)\b", t):
        return None
    heure = _heure_fixe(t)
    if heure is None:
        return None
    h, m = heure
    decalage = 2 if re.search(r"après[- ]demain", t) else 1 if "demain" in t else 0
    maintenant = datetime.datetime.now()
    cible = maintenant.replace(hour=h, minute=m, second=0, microsecond=0) + datetime.timedelta(days=decalage)
    if cible <= maintenant:
        cible += datetime.timedelta(days=1)
        decalage = 1
    texte = None
    trouve = re.search(r"(?:rappelle|préviens)[- ]moi (?:de |d')(.+?)\s+(?:à|a|demain|après[- ]demain|ce soir)\b", t)
    if trouve:
        texte = trouve.group(1)
    else:
        # Le texte du rappel est ce qui suit « de » ou « d' », après l'heure
        heure_dite = re.search(r"\d{1,2}\s?h|\bheures?\b|\bmidi\b|\bminuit\b", t)
        if heure_dite:
            # ce qui suit l'heure, une fois retirés les minutes et « du matin », « de », « pour »...
            suite = t[heure_dite.end():].replace("-", " ").split()
            while suite and (suite[0].isdigit() or suite[0] in _VALEURS or suite[0] in ("et", "demie", "demi", "quart")):
                suite.pop(0)
            suite = re.sub(r"^(du matin|du soir|de l'après[- ]midi|de la matinée|pile|précises?)\b\s*", "", " ".join(suite))
            suite = re.sub(r"^(de |d'|que |qu'|pour |il faut |je dois )", "", suite).strip()
            if len(suite) >= 3:
                texte = suite
    if texte:
        message = "Rappel : " + texte.strip() + "."
    elif re.search(r"\b(réveille|reveille|réveil)\b", t):
        message = f"Il est {_heure_parlee(h, m)}, c'est l'heure de te réveiller."
    else:
        message = f"Il est {_heure_parlee(h, m)}, c'est l'heure de ton rappel."
    _ajouter_rappel(cible.timestamp(), message)
    jour = ("demain " if decalage == 1 else "après-demain " if decalage == 2 else "")
    return f"C'est noté, je te préviendrai {jour}à {_heure_parlee(h, m)}."


# ---------- Applications ----------

def _commande_ouvrir(t):
    m = re.search(r"\b(ouvre|ouvrir|ouvres|lance|lancer|lances|démarre|démarrer)\b(.*)", t)
    if not m:
        return None
    reste = m.group(2)
    # Une demande plus complexe (« ouvre Chrome et cherche... », « ferme ça et ouvre Chrome »)
    # reste pour Claude : sinon Jarvis n'en ferait que la moitié
    if re.search(r"\b(et|puis|pour|avec|sur|dans)\b", reste) \
            or re.search(r"\b(et|puis|ferme\w*|quitte\w*)\b", t[:m.start()]):
        return None
    for motif, cible, nom in APPLICATIONS:
        if re.search(rf"\b(?:{motif})\b", reste):
            os.startfile(cible)
            return f"J'ouvre {nom}."
    # Sinon, une application du menu Démarrer qui porte ce nom
    demande = _sans_accents(re.sub(r"\b(le|la|les|l'|mon|ma|mes|un|une|moi|logiciel|application|appli|programme|dossier)\b",
                                   " ", reste))
    if len(demande) >= 2:
        raccourcis = _menu_demarrer()
        choix = raccourcis.get(demande)
        if choix is None:
            # une application déjà ouverte par le passé, même si son nom est mal entendu
            choix = jarvis_fenetres.meilleur(demande, [((nom, infos["chemin"]), [nom])
                                                       for nom, infos in applications_connues().items()
                                                       if os.path.exists(infos["chemin"])])
        if choix is None and len(demande) >= 3:
            proches = difflib.get_close_matches(demande, list(raccourcis), 1, cutoff=0.82)
            choix = raccourcis[proches[0]] if proches else None
        if choix:
            nom, chemin = choix
            os.startfile(chemin)
            _apprendre(nom, chemin)
            return f"J'ouvre {nom}."
    return None


_raccourcis = None
FICHIER_APPLICATIONS = jarvis_config.chemin("applications.json")   # applications déjà ouvertes (reste sur ce PC)
_connues = None


def applications_connues():
    """Applications que tu as déjà ouvertes par Jarvis : nom -> {"chemin": ..., "fois": ...}."""
    global _connues
    if _connues is None:
        try:
            with open(FICHIER_APPLICATIONS, encoding="utf-8") as f:
                _connues = json.load(f)
        except (OSError, ValueError):
            _connues = {}
            try:                         # première fois : on reprend celles déjà ouvertes d'après le journal
                noms = {nom: chemin for nom, chemin in _menu_demarrer().values()}
                with open(jarvis_config.chemin("jarvis.log"), encoding="utf-8", errors="replace") as f:
                    for nom in re.findall(r"Commande instantanée : J'ouvre (.+?)\.", f.read()):
                        if nom in noms:
                            _connues.setdefault(nom, {"chemin": noms[nom], "fois": 0})["fois"] += 1
                if _connues:
                    _enregistrer_applications()
            except OSError:
                pass
    return _connues


def _enregistrer_applications():
    try:
        with open(FICHIER_APPLICATIONS, "w", encoding="utf-8") as f:
            json.dump(_connues, f, ensure_ascii=False, indent=1)
    except OSError as erreur:
        print("Applications : écriture impossible :", erreur)


def _apprendre(nom, chemin):
    connues = applications_connues()
    connues.setdefault(nom, {"chemin": chemin, "fois": 0})
    connues[nom]["chemin"] = chemin
    connues[nom]["fois"] += 1
    _enregistrer_applications()


def noms_applications(maximum=10):
    """Noms des applications les plus ouvertes (donnés à Whisper pour qu'il les reconnaisse)."""
    try:
        connues = applications_connues()
        return [nom for nom, _ in sorted(connues.items(), key=lambda x: -x[1].get("fois", 0))[:maximum]]
    except Exception:
        return []


def _menu_demarrer():
    """Applications du menu Démarrer : nom simplifié -> (nom affiché, raccourci)."""
    global _raccourcis
    if _raccourcis is None:
        _raccourcis = {}
        for racine in (os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
                       os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")):
            for dossier, _, fichiers in os.walk(racine):
                for fichier in fichiers:
                    nom = fichier[:-4]
                    if not fichier.lower().endswith(".lnk") or re.search(
                            r"uninst|d[ée]sinstall|manual|manuel|docs|notes|aide|nouveaut|registry|jarvis",
                            nom, re.I):
                        continue
                    _raccourcis[_sans_accents(nom)] = (nom, os.path.join(dossier, fichier))
    return _raccourcis


def _commande_fermer(t):
    m = re.search(r"\b(ferme|fermer|fermes|quitte|quitter)\b(.*)", t)
    if not m:
        return None
    for motif, programme, nom in A_FERMER:
        if re.search(rf"\b(?:{motif})\b", m.group(2)):
            # Fermeture normale (sans forcer) : l'application peut proposer d'enregistrer
            resultat = subprocess.run(["taskkill", "/IM", programme], capture_output=True,
                                      creationflags=SANS_FENETRE)
            return f"Je ferme {nom}." if resultat.returncode == 0 else f"{nom.capitalize()} n'est pas ouvert."
    return None


def _commande_capture(t):
    if not re.search(r"capture (d'|de l'|l'|de mon |de )?[ée]cran|copie d'[ée]cran|screenshot", t):
        return None
    dossier = os.path.join(DOSSIER_PERSO, "Pictures", "Jarvis")
    os.makedirs(dossier, exist_ok=True)
    fichier = os.path.join(dossier, time.strftime("capture_%Y-%m-%d_%Hh%Mm%S.png"))
    script = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
              "Add-Type 'using System.Runtime.InteropServices;public class JV{"
              "[DllImport(\"user32.dll\")]public static extern bool SetProcessDPIAware();}'; "
              "[JV]::SetProcessDPIAware() | Out-Null; "
              "$e=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
              "$b=New-Object System.Drawing.Bitmap $e.Width,$e.Height; "
              "$g=[System.Drawing.Graphics]::FromImage($b); "
              "$g.CopyFromScreen($e.Left,$e.Top,0,0,$b.Size); $b.Save($env:JARVIS_CAPTURE)")
    env = os.environ.copy()
    env["JARVIS_CAPTURE"] = fichier
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, creationflags=SANS_FENETRE, timeout=20)
    if os.path.exists(fichier):
        return "Capture enregistrée dans tes images, dossier Jarvis."
    return "Je n'ai pas réussi à faire la capture."


# ----- Éteindre, redémarrer, mettre en veille : toujours après confirmation -----

_attente = None      # (action, moment limite) quand Jarvis attend un « oui »


def confirmation_en_attente():
    return _attente is not None and time.time() < _attente[1]


def _executer_alimentation(action):
    if action == "effacer_memoire":
        jarvis_memoire.tout_effacer()
        return "C'est fait, ma mémoire est vide."
    if action == "bonne_nuit":
        for _, programme, _ in A_FERMER:
            subprocess.run(["taskkill", "/IM", programme], capture_output=True, creationflags=SANS_FENETRE)
        minuteur = threading.Timer(8, lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0))
        minuteur.daemon = True
        minuteur.start()
        return f"Bonne nuit{jarvis_config.SALUT}. Je ferme tes applications et je mets l'ordinateur en veille."
    if action == "eteindre":
        subprocess.run(["shutdown", "/s", "/t", str(DELAI_EXTINCTION)], creationflags=SANS_FENETRE)
        return (f"L'ordinateur s'éteindra dans {DELAI_EXTINCTION} secondes. "
                "Dis Jarvis, annule l'extinction, pour l'arrêter.")
    if action == "redemarrer":
        subprocess.run(["shutdown", "/r", "/t", str(DELAI_EXTINCTION)], creationflags=SANS_FENETRE)
        return (f"L'ordinateur redémarrera dans {DELAI_EXTINCTION} secondes. "
                "Dis Jarvis, annule l'extinction, pour l'arrêter.")
    minuteur = threading.Timer(4, lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0))
    minuteur.daemon = True
    minuteur.start()
    return "Je mets l'ordinateur en veille."


def _commande_alimentation(t):
    global _attente
    if confirmation_en_attente():
        action = _attente[0]
        _attente = None
        if re.match(r"\W*(oui|ouais|confirme|je confirme|vas-y|d'accord|ok)\b", t):
            return _executer_alimentation(action)
        if re.match(r"\W*(non|annule|laisse|surtout pas)\b", t):
            return "D'accord, j'annule."
    _attente = None
    if re.search(r"\b(annule|arrête|stoppe)\b.*\b(extinction|arrêt|redémarrage)\b", t):
        resultat = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=SANS_FENETRE)
        return "L'extinction est annulée." if resultat.returncode == 0 else "Aucune extinction n'était prévue."
    machine = r".*\b(pc|ordinateur|ordi)\b"
    # (« éteins » est parfois entendu « et tel » ou « estelle » : la confirmation évite toute erreur)
    if re.search(r"(\b(éteins|éteindre|éteint|éteigne|eteins|eteindre|estelle)\b|^\W*et tel\b)" + machine, t):
        action, question = "eteindre", "éteindre l'ordinateur"
    elif re.search(r"\b(redémarre|redémarrer|redemarre|relance)\b" + machine, t):
        action, question = "redemarrer", "redémarrer l'ordinateur"
    elif re.search(r"\b(mets|mettre|passe|passer)\b" + machine + r".*\ben veille\b", t) \
            or re.search(r"\ben veille\b" + machine, t):
        action, question = "veille", "mettre l'ordinateur en veille"
    else:
        return None
    _attente = (action, time.time() + DELAI_CONFIRMATION)
    return f"Tu veux vraiment {question} ? Dis oui pour confirmer."


def _commande_chercher_fichier(t):
    m = re.search(r"\b(?:cherche|trouve|recherche|retrouve)\b.*?\b(?:fichiers?|documents?|photos?|images?|vidéos?)\b"
                  r"\s+(?:qui s'appelle |qui s'appellent |nommée? |appelée? |intitulée? |de |du |des |d'|sur |avec )?(.+)$", t)
    if not m:
        return None
    termes = [x for x in _sans_accents(m.group(1)).split()
              if x not in ("le", "la", "les", "l", "un", "une", "mon", "ma", "mes", "de", "du", "des", "d")]
    if not termes:
        return None
    trouves, limite = [], time.time() + 5
    for nom in ("Documents", "Desktop", "Downloads", "Pictures", "Videos", "Music"):
        for dossier, sous, fichiers in os.walk(os.path.join(DOSSIER_PERSO, nom)):
            sous[:] = [d for d in sous if not d.startswith(".")]
            for fichier in fichiers:
                simple = _sans_accents(fichier)
                if all(terme in simple for terme in termes):
                    chemin = os.path.join(dossier, fichier)
                    try:
                        trouves.append((os.path.getmtime(chemin), chemin))
                    except OSError:
                        pass
            if time.time() > limite or len(trouves) >= 300:
                break
    recherche = " ".join(termes)
    if not trouves:
        return f"Je n'ai trouvé aucun fichier contenant {recherche} dans tes dossiers personnels."
    trouves.sort(reverse=True)
    chemin = trouves[0][1]
    subprocess.Popen(["explorer", "/select,", chemin])
    nombre = len(trouves)
    nom = os.path.splitext(os.path.basename(chemin))[0]
    debut = "J'ai trouvé un fichier" if nombre == 1 else f"J'ai trouvé {nombre} fichiers"
    intro = "Il s'appelle" if nombre == 1 else "Le plus récent est"
    return f"{debut} contenant {recherche}. {intro} {nom}, je te le montre dans l'explorateur."


def _commande_verrouiller(t):
    if re.search(r"\bverrouille\w*\b.*\b(pc|ordinateur|ordi|session|écran)\b", t):
        ctypes.windll.user32.LockWorkStation()
        return "Je verrouille l'ordinateur."
    return None


# ---------- Routines ----------

def _rappels_du_jour(decalage=0):
    jour = time.localtime(time.time() + 86400 * decalage).tm_yday
    return sorted((r for r in _lire_rappels() if time.localtime(r["quand"]).tm_yday == jour),
                  key=lambda r: r["quand"])


def _commande_routine(t):
    global _attente
    if re.match(r"\W*(bonjour|bonsoir|salut)\b(?! (à|a) )", t) and len(t.split()) <= 3:
        h = time.localtime().tm_hour
        phrases = [("Bonsoir" if h >= 18 else "Bonjour") + f"{jarvis_config.SALUT}.", _date(), _heure()]
        try:
            meteo = _commande_meteo("météo", "météo")
            if meteo:
                phrases.append(meteo)
        except Exception:
            pass
        rappels = _rappels_du_jour()
        if rappels:
            details = []
            for r in rappels[:4]:
                q = time.localtime(r["quand"])
                details.append(f"à {_heure_parlee(q.tm_hour, q.tm_min)}, {r['message']}")
            phrases.append(f"Tu as {len(rappels)} rappel{'s' if len(rappels) > 1 else ''} aujourd'hui : "
                           + " ".join(details))
        else:
            phrases.append("Tu n'as aucun rappel aujourd'hui.")
        try:
            import jarvis_systeme
            m = jarvis_systeme.mesures
            if m["pret"]:
                etat = f"Côté ordinateur, le processeur est à {m['cpu']:.0f} pour cent"
                if m["temp"] is not None:
                    etat += f" et la température à {m['temp']:.0f} degrés"
                phrases.append(etat + ".")
        except Exception:
            pass
        return " ".join(phrases)
    if re.match(r"\W*bonne nuit\b", t):
        demain = _rappels_du_jour(1)
        info = ""
        if demain:
            q = time.localtime(demain[0]["quand"])
            info = f"Ton premier rappel de demain est à {_heure_parlee(q.tm_hour, q.tm_min)}. "
        _attente = ("bonne_nuit", time.time() + DELAI_CONFIRMATION)
        return info + "Tu veux que je ferme tes applications et que je mette l'ordinateur en veille ? Dis oui pour confirmer."
    return None


# ---------- Dictée : Jarvis tape le texte dans la fenêtre active ----------

class _CLAVIER(ctypes.Structure):
    _fields_ = [("touche", ctypes.c_ushort), ("code", ctypes.c_ushort), ("drapeaux", ctypes.c_ulong),
                ("temps", ctypes.c_ulong), ("extra", ctypes.c_size_t)]


class _SOURIS(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("donnees", ctypes.c_ulong),
                ("drapeaux", ctypes.c_ulong), ("temps", ctypes.c_ulong), ("extra", ctypes.c_size_t)]


class _UNION(ctypes.Union):
    _fields_ = [("clavier", _CLAVIER), ("souris", _SOURIS)]


class _ENTREE(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _UNION)]


def taper(texte):
    """Tape un texte dans la fenêtre active, caractère par caractère (accents compris)."""
    code = texte.encode("utf-16-le")
    unites = [int.from_bytes(code[i:i + 2], "little") for i in range(0, len(code), 2)]
    entrees = (_ENTREE * (2 * len(unites)))()
    for i, unite in enumerate(unites):
        for j, drapeaux in enumerate((0x0004, 0x0004 | 0x0002)):       # appui, puis relâchement
            entrees[2 * i + j].type = 1
            entrees[2 * i + j].u.clavier = _CLAVIER(0, unite, drapeaux, 0, 0)
    return ctypes.windll.user32.SendInput(len(entrees), entrees, ctypes.sizeof(_ENTREE))


def _commande_dictee(t, brut):
    if re.match(r"\W*(appuie sur|tape|fais) entrée\W*$", t) or re.match(r"\W*(valide|envoie)\W*$", t):
        _touche(0x0D)
        return "C'est fait."
    m = re.match(r"\W*(?:dicte|dictée|dicter|saisis|tape|écris ceci|ecris ceci|écris le texte)\b[\s:,]*(.+)",
                 brut.strip(), re.I | re.S)
    if not m:
        return None
    texte = m.group(1).strip()
    texte = texte[0].upper() + texte[1:]
    threading.Timer(0.3, taper, args=(texte,)).start()
    return "C'est écrit."


# ---------- Musique et vidéos sur YouTube ----------

def _youtube(recherche):
    """Première vidéo trouvée pour cette recherche : (identifiant, titre), ou None."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(recherche)
    requete = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9", "Cookie": "SOCS=CAI; CONSENT=YES+1"})
    with urllib.request.urlopen(requete, timeout=8) as reponse:
        page = reponse.read().decode("utf-8", "replace")
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', page, re.S)
    if not m:
        return None
    try:
        titre = json.loads('"' + m.group(2) + '"')
    except ValueError:
        titre = m.group(2)
    return m.group(1), titre


_MOTS_MUSIQUE = r"\b(musiques?|chansons?|morceaux?|titre|clip|vidéos?|video|youtube|album|playlist)\b"


_PAS_UN_TITRE = (r"\b(applications?|applis?|fenêtres?|écran|ecran|ordinateur|ordi|pc|programmes?|logiciels?|dossiers?|"
                 r"fichiers?|onglets?|page|site|navigateur|chrome|bureau|souris|clavier|micro|mode|plein|grande?s?|"
                 r"petite?s?|taille|premier plan|côté|gauche|droite|jour|heure|réveil|rappel|alarme|minuteur|"
                 r"mémoire|note|notes|veille|pause|son|volume|luminosité|wifi|bluetooth)\b")


def _commande_musique(t):
    # « mets » est souvent entendu « mais », « mes » ou « les » : on le rétablit quand la
    # phrase parle clairement de musique (« mais de la musique », « mais 50 Cent sur YouTube »).
    if re.match(r"\W*(mais|mes|mai|m'est|les)\b", t) and re.search(_MOTS_MUSIQUE, t) \
            and len(t.split()) <= 10:
        t = re.sub(r"^\W*(mais|mes|mai|m'est|les)\b", "mets", t)
    if not re.match(r"\W*(mets|mets-moi|met|mettre|joue|joue-moi|jouer|lance|passe|passe-moi)\b", t):
        return None
    # Avec un mot comme « musique » ou « chanson », ou bien « mets » / « joue » suivi d'un titre.
    # (Minuteur, volume, pause, veille... sont reconnus avant d'arriver ici.)
    simple = re.match(r"\W*(mets|mets-moi|joue|joue-moi)\s+(?!à |a |en |au |aux |sur |dans |ça |le pc|l'ordi)\S+\s+\S+", t)
    # « mets l'application en grand écran » n'est pas un titre de chanson : ces demandes vont à Claude
    if simple and re.search(_PAS_UN_TITRE, t):
        simple = None
    if not (re.search(_MOTS_MUSIQUE, t)
            or re.match(r"\W*joue\b", t) or simple):
        return None
    recherche = re.sub(r"^\W*(mets-moi|mets|met|mettre|joue-moi|joue|jouer|lance|passe-moi|passe)\b", " ", t)
    recherche = re.sub(r"\b(sur youtube|youtube|s'il te plaît|stp)\b", " ", recherche)
    recherche = re.sub(r"^\s*(moi\s+)?(de la musique|la musique|une musique|la chanson|une chanson|le morceau|"
                       r"un morceau|le titre|le clip|la vidéo|une vidéo|la video|l'album|la playlist|du|de la|des|de l'|de|un peu de)\b",
                       " ", recherche)
    recherche = " ".join(recherche.split()).strip(" .,!?")
    if recherche in ("musique", "musiques", "de musique", "les musiques"):
        recherche = ""
    precise = bool(recherche)
    try:
        video = _youtube(recherche or MUSIQUE_PAR_DEFAUT)
    except Exception as erreur:
        print("YouTube :", erreur)
        video = None
    if video is None:
        os.startfile("https://www.youtube.com/results?search_query="
                     + urllib.parse.quote(recherche or MUSIQUE_PAR_DEFAUT))
        return "Je n'ai pas pu lancer la lecture directement, je t'ouvre la recherche sur YouTube."
    os.startfile("https://www.youtube.com/watch?v=" + video[0])
    return f"Je lance {video[1]}." if precise else "Je lance de la musique."


# ---------- Mémoire durable ----------

def _commande_memoire(brut):
    """« retiens que... », « qu'est-ce que tu as retenu ? », « oublie que... » (voir jarvis_memoire)."""
    global _attente
    resultat = jarvis_memoire.commande(brut)
    if resultat is None:
        return None
    action, texte = resultat
    if action == "confirmer_effacement":
        _attente = ("effacer_memoire", time.time() + DELAI_CONFIRMATION)
    return texte


# ---------- État du PC et notes ----------

def _commande_etat_pc(t):
    if not re.search(_ETAT_PC, t):
        return None
    import jarvis_systeme
    return jarvis_systeme.rapport()


def _commande_notes(t, brut):
    if re.search(_LIRE_NOTES, t):
        try:
            with open(FICHIER_NOTES, encoding="utf-8") as f:
                notes = [ligne.split(" : ", 1)[-1].strip() for ligne in f if ligne.strip()]
        except OSError:
            notes = []
        if not notes:
            return "Tu n'as aucune note."
        dernieres = notes[-5:]
        debut = (f"Tu as {len(notes)} notes. Voici les {len(dernieres)} dernières : "
                 if len(notes) > 5 else "Voici tes notes : " if len(notes) > 1 else "Tu as une note : ")
        return debut + " ".join(n if n.endswith((".", "!", "?")) else n + "." for n in dernieres)
    m = re.match(r"\W*(?:prends note|ajoute une note|note|notes)\b[\s:,]*(?:que |qu')?(.+)",
                 brut.strip(), re.I | re.S)
    if not m or len(m.group(1).split()) < 2:
        return None
    contenu = m.group(1).strip()
    with open(FICHIER_NOTES, "a", encoding="utf-8") as f:
        f.write(time.strftime("%d/%m/%Y %H:%M") + " : " + contenu + "\n")
    return "C'est noté."


# ---------- Point d'entrée ----------

def _propre(brut):
    t = brut.lower().replace("’", "'").strip(" .!?")
    # « mets » est presque toujours entendu « mais » en début de demande (« mais la fenêtre en plein
    # écran », « mais un rappel à 14 h ») : on le rétablit, sauf devant « oui », « non »...
    return re.sub(r"^(\W*(?:jarvis\W+)?)(?:mais|m'est)\s+(?!oui\b|non\b|si\b|pourquoi\b|comment\b|qu|je\b|tu\b|il\b|c')",
                  r"\1mets ", t)


_ACTIONS = (r"(?:ouvre|ouvres|ferme|fermes|lance|quitte|mets|cherche|recherche|trouve|monte|baisse|coupe|"
            r"éteins|redémarre|démarre|joue|affiche|envoie|écris|crée|supprime|télécharge)")
_DEUX_DEMANDES = re.compile(r"\b" + _ACTIONS + r"\b.*\b(?:et|puis|ensuite|par la suite|après)\b.*\b" + _ACTIONS + r"\b")
_TEXTE_LIBRE = re.compile(r"^\W*(?:jarvis\W+)?(?:dicte|dictée|écris|tape|note|retiens|retient|souviens-toi|"
                          r"rappelle-moi|rappelle-toi|n'oublie pas|mémorise)\b")


def deux_demandes(t):
    """Vrai pour une phrase qui contient deux actions (« ferme Imou et ouvre Chrome ») : elle est
    confiée en entier à Claude, sinon Jarvis n'en ferait que la moitié. Les phrases dictées,
    notées ou retenues ne comptent pas : leur texte est libre."""
    return bool(_DEUX_DEMANDES.search(t)) and not _TEXTE_LIBRE.match(t)


# Réponses très courtes : Whisper les comprend mal (« oui » devient « Où est-il ? »),
# alors que la première écoute (Vosk) les reconnaît bien. On garde donc sa version.
MOTS_COURTS = {"oui", "ouais", "non", "si", "ok", "d'accord", "quoi", "comment", "pardon", "vas-y", "oui vas-y",
               "exactement", "voilà", "bien sûr", "pas du tout", "c'est ça", "annule", "continue", "peut-être",
               "oui merci", "non merci", "oui s'il te plaît", "non c'est bon", "oui c'est ça", "non pas du tout"}


def mot_court(texte):
    return _propre(texte).strip(" ,;:") in MOTS_COURTS


def sans_whisper(texte_vosk):
    """Vrai si la phrase entendue est une commande simple, comprise sans la
    retranscription précise (Whisper) : on gagne environ 2 secondes."""
    t = _propre(texte_vosk)
    if confirmation_en_attente():
        return True
    if re.match(r"\W*(bonjour|bonsoir|salut|bonne nuit)\W*$", t):
        return True
    if deux_demandes(t):
        return False
    if t in MOTS_COURTS:
        return True
    if re.search(r"\b(cherche|recherche|puis)\b", t):
        return False
    if re.search(r"\b(éteins|redémarre|en veille|capture d'écran|annule l'extinction)\b", t):
        return True
    if re.search(r"\b(ferme|quitte)\b", t):
        return any(re.search(rf"\b(?:{motif})\b", t) for motif, _, _ in A_FERMER)
    if re.search(r"\b(quelle heure|quel jour|quelle date|point du jour|nouvelle conversation|"
                 r"oublie tout|répète|verrouille)\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t):
        return True
    if re.search(r"\b(son|volume|sourdine)\b", t):
        return True
    if re.search(_ETAT_PC, t) or re.search(_LIRE_NOTES, t):
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
    if not confirmation_en_attente() and any(deux_demandes(_propre(b)) for b in textes if b):
        return None
    for brut in textes:
        if not brut:
            continue
        t = _propre(brut)
        try:
            if confirmation_en_attente():
                reponse = _commande_alimentation(t)
                if reponse:
                    return reponse
            if re.search(r"\bquelle heure\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t):
                return _heure()
            if re.search(r"\b(quel jour|quelle date|on est le combien|nous sommes le combien)\b", t) \
                    and not re.search(r"\b(sera|était|demain|hier)\b", t):
                return _date()
            for commande in (lambda: _commande_memoire(brut),
                             lambda: _commande_routine(t),
                             lambda: jarvis_ecran.lecture_directe(t),
                             lambda: _commande_dictee(t, brut),
                             lambda: _commande_alimentation(t),
                             lambda: _commande_rappel(t),
                             lambda: _commande_minuteur(t, annoncer),
                             lambda: _commande_meteo(t, brut),
                             lambda: _commande_volume(t),
                             lambda: _commande_lecture(t),
                             lambda: _commande_fermer(t),
                             lambda: jarvis_fenetres.commande(t),
                             lambda: _commande_musique(t),
                             lambda: _commande_ouvrir(t),
                             lambda: _commande_capture(t),
                             lambda: _commande_chercher_fichier(t),
                             lambda: _commande_verrouiller(t),
                             lambda: _commande_etat_pc(t),
                             lambda: _commande_notes(t, brut)):
                reponse = commande()
                if reponse:
                    return reponse
        except Exception as erreur:
            print("Commande instantanée impossible :", erreur)
            return None
    return None
