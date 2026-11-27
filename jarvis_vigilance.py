"""
JARVIS - les alertes de la Vigilance de Météo-France, pour ton département.

Jarvis retrouve ton département à partir de ta ville (celle de la météo), puis regarde la carte de
Vigilance de Météo-France toutes les 30 minutes. Dès qu'une vigilance jaune, orange ou rouge apparaît
pour aujourd'hui ou demain (orages, pluie-inondation, vent, neige-verglas, canicule, grand froid,
crues, avalanches, vagues-submersion), il te prévient une fois, et le réacteur s'anime à la couleur
de l'alerte, avec un symbole : un éclair, des gouttes, du givre...
À la voix : « Jarvis, y a-t-il une alerte météo ? », « quelle est la vigilance météo ? »

Aucune mise en place : Jarvis lit la carte de Vigilance que Météo-France publie en données ouvertes sur
data.gouv.fr (« Vigilance météorologique archivée », Licence Ouverte), disponible quelques secondes après
chaque nouvelle carte, sans compte ni clé.
Facultatif : si tu as une clé de l'API officielle de Météo-France (portail-api.meteofrance.fr, API « Données
Publiques Vigilance »), Jarvis s'en sert en secours quand data.gouv.fr ne répond pas. Pour la ranger :
    cmdkey /generic:Jarvis-MeteoFrance /user:vigilance /pass
Le département se règle tout seul ; pour le forcer : config.json, "departement": "33".
"""

import calendar
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jarvis_config
import jarvis_mails          # même rangement des secrets (Gestionnaire d'identification de Windows)

CIBLE = "Jarvis-MeteoFrance"
URL = "https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours"      # avec clé (secours)
OUVERT = "https://files.data.gouv.fr/meteofrance/data/vigilance/"       # données ouvertes de Météo-France, sans clé
AGE_MAX = 30 * 3600                                    # une carte plus vieille que ça n'est plus fiable
URL_DEPARTEMENT = "https://geo.api.gouv.fr/communes?lat={lat}&lon={lon}&fields=codeDepartement&format=json"
FICHIER = jarvis_config.chemin("vigilance.json")      # département retrouvé, alertes déjà annoncées
INTERVALLE = 30 * 60                                   # secondes entre deux vérifications
ACTIVE = True                                          # annonces automatiques des alertes
NIVEAU_MIN = 2                                         # 2 = jaune, 3 = orange, 4 = rouge

PHENOMENES = {"1": "vent violent", "2": "pluie-inondation", "3": "orages", "4": "crues",
              "5": "neige-verglas", "6": "canicule", "7": "grand froid", "8": "avalanches",
              "9": "vagues-submersion"}
COULEURS = {2: "jaune", 3: "orange", 4: "rouge"}

animation = None          # (moment, niveau, [phénomènes]) : lue par l'affichage du réacteur
_verrou = threading.Lock()


def _lire_fichier():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire_fichier(donnees):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
    except OSError:
        pass


def cle_api():
    ident = jarvis_mails.identifiants(CIBLE)
    return ident[1].strip() if ident and ident[1] else None


def _telecharger(url, entetes=None, delai=15):
    requete = urllib.request.Request(url, headers={"User-Agent": "Jarvis", **(entetes or {})})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


_carte_ouverte = {"modifie": None, "carte": None}      # dernière carte lue, pour ne pas la retélécharger


def _carte_donnees_ouvertes():
    """La dernière carte publiée sur data.gouv.fr. L'index des cartes n'est retéléchargé que s'il a changé."""
    entetes = {"User-Agent": "Jarvis"}
    if _carte_ouverte["modifie"] and _carte_ouverte["carte"]:
        entetes["If-Modified-Since"] = _carte_ouverte["modifie"]
    try:
        with urllib.request.urlopen(urllib.request.Request(OUVERT + "vigilance-hexagone-tree.json", headers=entetes),
                                    timeout=12) as reponse:
            modifie = reponse.headers.get("Last-Modified")
            arbre = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        if erreur.code == 304:                          # rien de nouveau depuis la dernière fois
            return _carte_ouverte["carte"]
        raise
    # La carte la plus récente, tous jours confondus : juste après minuit, le dossier du nouveau jour
    # existe déjà mais ne contient pas encore de carte (il faut alors prendre celle de la veille).
    publiees = [(annee, mois, jour, heure)
                for annee, les_mois in arbre.items() if isinstance(les_mois, dict)
                for mois, les_jours in les_mois.items() if isinstance(les_jours, dict)
                for jour, les_heures in les_jours.items() if isinstance(les_heures, dict)
                for heure, fichiers in les_heures.items() if "CDP_CARTE_EXTERNE.json" in (fichiers or [])]
    if not publiees:
        raise ValueError("aucune carte de vigilance publiée")
    annee, mois, jour, heure = max(publiees)
    carte = _telecharger(f"{OUVERT}metropole/{annee}/{mois}/{jour}/{heure}/CDP_CARTE_EXTERNE.json", delai=20)
    _carte_ouverte.update(modifie=modifie, carte=carte)
    return carte


def _carte():
    """La carte de Vigilance en cours : données ouvertes d'abord, API avec clé en secours."""
    try:
        carte = _carte_donnees_ouvertes()
        fait = calendar.timegm(time.strptime(carte["product"]["update_time"][:19], "%Y-%m-%dT%H:%M:%S"))
        if time.time() - fait > AGE_MAX:
            raise RuntimeError("carte trop ancienne sur data.gouv.fr")
        return carte
    except Exception as erreur:
        cle = cle_api()
        if not cle:
            raise
        print("Vigilance (data.gouv.fr) :", erreur, "- essai avec la clé de Météo-France")
        return _telecharger(URL, {"apikey": cle, "accept": "application/json"}, delai=20)


def departement():
    """Le numéro du département (« 33 », « 2A »...) d'après la ville de la météo, gardé en mémoire."""
    force = str(jarvis_config._lu.get("departement") or "").strip()
    if force:
        return force.upper().zfill(2)
    import jarvis_commandes
    try:
        _, lat, lon = jarvis_commandes.VILLE_DEFAUT
    except Exception:
        return None
    cle = f"{float(lat):.3f},{float(lon):.3f}"
    with _verrou:
        donnees = _lire_fichier()
        if donnees.get("position") == cle and donnees.get("departement"):
            return donnees["departement"]
    try:
        communes = _telecharger(URL_DEPARTEMENT.format(lat=lat, lon=lon))
        code = communes[0]["codeDepartement"] if communes else None
    except Exception as erreur:
        print("Département introuvable :", erreur)
        return None
    if code:
        with _verrou:
            donnees = _lire_fichier()
            donnees.update(position=cle, departement=code)
            _ecrire_fichier(donnees)
    return code


def lire():
    """{"aujourdhui": [(phénomène, niveau)], "demain": [...]} pour ton département.
    Lève ValueError si le département est inconnu."""
    dep = departement()
    if not dep:
        raise ValueError
    donnees = _carte()
    resultat = {"aujourdhui": [], "demain": []}
    periodes = (donnees.get("product") or {}).get("periods") or []
    for index, periode in enumerate(periodes[:2]):
        jour = "aujourdhui" if (periode.get("echeance") or ("J" if index == 0 else "J1")) == "J" else "demain"
        try:                                    # après minuit, la carte de la veille : son « demain » est aujourd'hui
            debut = calendar.timegm(time.strptime(periode["begin_validity_time"][:19], "%Y-%m-%dT%H:%M:%S"))
            fin = calendar.timegm(time.strptime(periode["end_validity_time"][:19], "%Y-%m-%dT%H:%M:%S"))
            if fin <= time.time():
                continue                        # période terminée
            jour = "aujourdhui" if debut <= time.time() else "demain"
        except (KeyError, ValueError, TypeError):
            pass
        domaines = (periode.get("timelaps") or {}).get("domain_ids") or []
        vus = {}
        for domaine in domaines:
            ident = str(domaine.get("domain_id") or "")
            if ident != dep and ident != dep + "10":            # « 3310 » : la partie littorale du département
                continue
            for item in domaine.get("phenomenon_items") or []:
                niveau = int(item.get("phenomenon_max_color_id") or 1)
                nom = PHENOMENES.get(str(item.get("phenomenon_id")))
                if nom and niveau >= NIVEAU_MIN:
                    vus[nom] = max(niveau, vus.get(nom, 0))
        resultat[jour] = sorted(vus.items(), key=lambda x: -x[1])
    return resultat


def _phrase(jour, alertes):
    quand = "aujourd'hui" if jour == "aujourdhui" else "demain"
    morceaux = [f"vigilance {COULEURS[n]} {nom}" for nom, n in alertes]
    liste = morceaux[0] if len(morceaux) == 1 else ", ".join(morceaux[:-1]) + " et " + morceaux[-1]
    return f"{liste.capitalize()} {quand} dans ton département."


def _animer(alertes):
    global animation
    if alertes:
        animation = (time.time(), max(n for _, n in alertes), [nom for nom, _ in alertes])


def _erreur(erreur):
    if isinstance(erreur, ValueError):
        return "Je ne connais pas encore ta ville : dis par exemple, ma ville est Bordeaux."
    if "401" in str(erreur) or "403" in str(erreur):
        return "Météo-France refuse ma clé : elle est peut-être expirée. Il faut en générer une nouvelle."
    cause = getattr(erreur, "reason", erreur)
    if isinstance(cause, (ConnectionError, TimeoutError, OSError)) or "timed out" in str(erreur):
        # le site répond mal ou plus du tout : ce n'est ni la connexion Internet ni Jarvis
        return "Le service qui fournit les alertes de Météo-France ne répond pas pour le moment. Réessaie un peu plus tard."
    return "Je n'arrive pas à lire les alertes de Météo-France pour le moment."


_DEMANDE = re.compile(r"\b(?:alertes? (?:météo|meteo|orange|rouge|jaune)|vigilances? (?:météo|meteo|orange|rouge|"
                      r"jaune)?|vigilance|météo[- ]france)\b")


def commande(t):
    """« y a-t-il une alerte météo ? », « quelle est la vigilance météo ? »"""
    if not _DEMANDE.search(t.replace("’", "'").lower()):
        return None
    try:
        alertes = lire()
    except Exception as erreur:
        print("Vigilance :", type(erreur).__name__, erreur)
        return _erreur(erreur)
    if not alertes["aujourdhui"] and not alertes["demain"]:
        return "Aucune vigilance météo dans ton département, ni aujourd'hui ni demain."
    phrases = [_phrase(j, alertes[j]) for j in ("aujourdhui", "demain") if alertes[j]]
    _animer(alertes["aujourdhui"] or alertes["demain"])
    return " ".join(phrases)


def surveiller(annoncer):
    """Vérifie toutes les 30 minutes ; annonce une fois chaque nouvelle vigilance (ou une hausse de niveau)."""
    def boucle():
        time.sleep(60)                                   # laisser Jarvis démarrer tranquillement
        while True:
            try:
                if ACTIVE:
                    alertes = lire()
                    with _verrou:
                        donnees = _lire_fichier()
                        deja = set(donnees.get("annoncees", []))
                        nouvelles = {}
                        date = {"aujourdhui": time.strftime("%Y-%m-%d"),
                                "demain": time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))}
                        for jour in ("aujourdhui", "demain"):
                            for nom, niveau in alertes[jour]:
                                cle = f"{date[jour]}|{nom}|{niveau}"
                                if cle not in deja:
                                    nouvelles.setdefault(jour, []).append((nom, niveau))
                                    deja.add(cle)
                        garder = sorted(c for c in deja if c[:10] >= time.strftime("%Y-%m-%d"))
                        donnees["annoncees"] = garder
                        _ecrire_fichier(donnees)
                    if nouvelles:
                        _animer(nouvelles.get("aujourdhui") or nouvelles.get("demain"))
                        texte = "Alerte météo. " + " ".join(_phrase(j, nouvelles[j])
                                                          for j in ("aujourdhui", "demain") if j in nouvelles)
                        annoncer(texte)
            except Exception as erreur:
                print("Vigilance :", type(erreur).__name__, erreur)
            time.sleep(INTERVALLE)
    threading.Thread(target=boucle, daemon=True).start()
