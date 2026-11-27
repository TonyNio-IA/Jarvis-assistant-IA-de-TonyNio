"""
JARVIS - la fenêtre de réglages, aux couleurs de Jarvis.

Ouverture : clic droit sur le réacteur, puis « Réglages… », ou à la voix : « Jarvis, ouvre les réglages ».
Chaque réglage s'applique tout de suite, sans redémarrer (sauf la taille du réacteur, au prochain démarrage),
et il est gardé dans preferences.json (fichier qui reste sur ce PC).

Onglets, rangés par famille : Apparence, Réacteur, Son | Profils (avec le mode enfant), Comptes (agenda, boîte mail, navigateur), Claude,
Alertes | Rapports, Historique | Système (démarrage avec Windows, sauvegarde et restauration, paramètres par défaut), Santé |
Aide, À propos. Un petit réacteur en direct montre l'effet des réglages.

« Paramètres par défaut » remet tous les réglages comme à l'installation, après confirmation. Il ne touche
jamais aux profils, aux mémoires, aux voix enregistrées, aux rappels, aux notes ni aux listes.
"""

import jarvis_tk_sur  # noqa: F401  (images et variables Tk : jamais liberees depuis un autre fil)
import datetime
import json
import math
import os
import re
import sys
import threading
import time
import zipfile

import jarvis_config

FICHIER = jarvis_config.chemin("preferences.json")
DOSSIER_SAUVEGARDES = os.path.join(os.path.expanduser("~"), "Documents", "Jarvis - sauvegardes")
# Fichiers personnels mis dans une sauvegarde (jamais publiés)
FICHIERS_SAUVEGARDE = ("config.json", "ville.txt", "memoire.json", "rappels.json", "applications.json", "notes.txt",
                       "position.txt", "volumes.json", "liste.json", "reglages_voix.json", "enfant.json",
                       "apparence.json", "accueil.json", "profils.json", "calendrier.json", "messages.json",
                       "preferences.json", "rappels_faits.json")
DOSSIERS_SAUVEGARDE = ("profils",)

# Palette violette douce : fond presque noir teinté de violet, cartes un peu plus claires, accent lavande
FOND, PANNEAU, PANNEAU2 = "#0f0b1a", "#171126", "#211a35"
BORD, SURVOL, ASCENS, OFF, CREUX, ENCRE = "#30264b", "#41346a", "#54458a", "#3d3358", "#2d2447", "#1a1030"
ACCENT = "#a98bff"
TEXTE, DISCRET = "#efe9fb", "#a094c0"
NOMS_COULEURS = ("FOND", "PANNEAU", "PANNEAU2", "BORD", "SURVOL", "ASCENS", "OFF", "CREUX", "ENCRE", "ACCENT",
                 "TEXTE", "DISCRET")
# La fenêtre prend la teinte du thème du réacteur (Vice City par défaut : violet doux)
TEINTES = {"vice city": "#9d4dff", "bleu": "#2f9bff", "vert": "#2bff88", "rouge": "#ff3b3b", "violet": "#9d4dff",
           "orange": "#ff8c42", "iron man": "#ff3b2f", "océan": "#00b4d8", "forêt": "#3ddc84", "aurore": "#00b4d8",
           "galaxie": "#7b5cff"}


_CACHE_IMG = {}


def _image_aa(w, h, fond, dessin, cle=None, ss=3):
    """Une image lissée pour Tk : on dessine en grand avec pygame, puis on réduit (bords nets, sans escaliers)."""
    import pygame
    import tkinter as tk
    if cle is not None and cle in _CACHE_IMG:
        return _CACHE_IMG[cle]
    w, h = max(1, int(w)), max(1, int(h))
    surface = pygame.Surface((w * ss, h * ss))
    surface.fill(_rgb(fond))
    dessin(surface, ss)
    petit = pygame.transform.smoothscale(surface, (w, h))
    # la réduction décale parfois le fond de 1 ou 2 niveaux : on le recale, sinon un rectangle apparaît
    ref, voulu = petit.get_at((0, 0)), _rgb(fond)
    plus = tuple(max(0, voulu[i] - ref[i]) for i in range(3))
    moins = tuple(max(0, ref[i] - voulu[i]) for i in range(3))
    if any(plus):
        petit.fill(plus, special_flags=pygame.BLEND_RGB_ADD)
    if any(moins):
        petit.fill(moins, special_flags=pygame.BLEND_RGB_SUB)
    image = tk.PhotoImage(data=b"P6 %d %d 255\n" % (w, h) + pygame.image.tobytes(petit, "RGB"))
    if cle is not None:
        if len(_CACHE_IMG) > 300:
            _CACHE_IMG.clear()
        _CACHE_IMG[cle] = image
    return image


def _rect_rond(toile, x1, y1, x2, y2, r, **options):
    """Rectangle aux coins arrondis sur un Canvas."""
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
           x1, y2 - r, x1, y1 + r, x1, y1]
    return toile.create_polygon(pts, smooth=True, **options)


def _nom_theme():
    """Le thème choisi pour le réacteur (lu dans apparence.json, « vice city » par défaut)."""
    try:
        with open(jarvis_config.chemin("apparence.json"), encoding="utf-8") as f:
            return str(json.load(f).get("couleur", "vice city")).lower()
    except (OSError, ValueError):
        return "vice city"


def _couleurs_ui():
    return {n: globals()[n] for n in NOMS_COULEURS}


def _poser_theme(nom):
    """Calcule les couleurs de la fenêtre à partir de la teinte du thème et les pose."""
    import colorsys
    tint = TEINTES.get(nom)
    if tint is None:
        try:
            import jarvis_extras
            tint = jarvis_extras.PALETTES[nom][0]
        except Exception:
            tint = TEINTES["vice city"]
    r, g, b = (int(tint[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, sat, _ = colorsys.rgb_to_hsv(r, g, b)
    sb = min(0.58, 0.25 + sat * 0.4)

    def c(s_, v_):
        return "#%02x%02x%02x" % tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, s_, v_))
    global FOND, PANNEAU, PANNEAU2, BORD, SURVOL, ASCENS, OFF, CREUX, ENCRE, ACCENT, TEXTE, DISCRET
    FOND, PANNEAU, PANNEAU2 = c(sb, .10), c(sb, .15), c(sb, .21)
    BORD, SURVOL, ASCENS = c(sb * .95, .28), c(sb, .38), c(sb * .8, .50)
    OFF, CREUX, ENCRE = c(sb * .6, .32), c(sb, .23), c(sb, .13)
    ACCENT = c(min(0.6, 0.2 + sat * 0.5), 1.0)
    TEXTE, DISCRET = c(0.07, .97), c(0.2, .75)
POLICE = ("Segoe UI", 10)
POLICE_TITRE = ("Segoe UI Semibold", 11)


# ---------- Où se trouvent les réglages ----------

def _module(nom):
    if nom == "reacteur":
        for cle in ("__main__", "jarvis_reacteur"):
            m = sys.modules.get(cle)
            if m is not None and hasattr(m, "COULEURS_VEILLE"):
                return m
        return None
    try:
        return __import__(nom)
    except Exception:
        return None


# Préréglages : un seul choix règle plusieurs valeurs
SENSIBILITE_MICRO = {
    "calme": {"SEUIL_SON_MIN": 0.005, "SEUIL_SON_MAX": 0.008},
    "normale": {"SEUIL_SON_MIN": 0.008, "SEUIL_SON_MAX": 0.012},
    "bruyante": {"SEUIL_SON_MIN": 0.015, "SEUIL_SON_MAX": 0.022},
}
SENSIBILITE_REVEIL = {
    "sensible": {"PAUSE_AVANT_JARVIS": 0.2, "PAUSE_LONGUE_AVANT_JARVIS": 0.6},
    "normale": {"PAUSE_AVANT_JARVIS": 0.3, "PAUSE_LONGUE_AVANT_JARVIS": 0.8},
    "prudente": {"PAUSE_AVANT_JARVIS": 0.5, "PAUSE_LONGUE_AVANT_JARVIS": 1.1},
}
NUIT_AUTO = {"non": None, "22 h à 7 h": (22, 7), "21 h à 7 h": (21, 7), "23 h à 7 h": (23, 7), "22 h à 8 h": (22, 8)}
COINS = ("en bas à droite", "en bas à gauche", "en haut à droite", "en haut à gauche")

# (clé, onglet, libellé, type, module, attribut, options)
#   type : "bool", "nombre" (min, max, pas, unité), "choix" (liste)
REGLAGES = [
    ("cycle", "Apparence", "Vitesse du défilement des couleurs", "nombre", "reacteur", "CYCLE_VEILLE", (4, 30, 1, "s")),
    ("vitesse_reflet", "Apparence", "Vitesse des reflets de la fenêtre", "nombre", "jarvis_affichage", "VITESSE_REFLET", (40, 400, 2, "")),
    ("longueur_reflet", "Apparence", "Longueur des reflets", "nombre", "jarvis_affichage", "LONGUEUR_REFLET", (20, 320, 5, "")),
    ("nb_reflets", "Apparence", "Nombre de reflets", "nombre", "jarvis_affichage", "NB_REFLETS", (1, 4, 1, "")),
    ("tour_reacteur", "Apparence", "Tour du reflet autour du cercle", "nombre", "jarvis_affichage", "TOUR_REFLET_REACTEUR", (2, 20, 0.5, "s")),
    ("reflet_reacteur", "Apparence", "Reflet autour du cercle du réacteur", "bool", "jarvis_affichage", "REFLET_REACTEUR", None),
    ("devant", "Réacteur", "Réacteur toujours au premier plan (sinon il reste sur le Bureau)", "bool", "jarvis_affichage", "TOUJOURS_DEVANT", None),
    ("regard", "Réacteur", "Le cœur suit la souris", "bool", "jarvis_affichage", "REGARD_SOURIS", None),
    ("force_regard", "Réacteur", "Intensité du suivi de la souris", "nombre", "jarvis_affichage", "FORCE_REGARD", (0.05, 0.35, 0.005, "")),
    ("danse", "Réacteur", "Le réacteur danse avec la musique", "bool", "jarvis_affichage", "DANSE_MUSIQUE", None),
    ("force_danse", "Réacteur", "Intensité de la danse", "nombre", "jarvis_affichage", "FORCE_DANSE", (0.05, 0.5, 0.01, "")),
    ("doux_nuit", "Apparence", "Plus doux la nuit", "bool", "jarvis_affichage", "DOUX_LA_NUIT", None),
    ("douceur_nuit", "Apparence", "Luminosité la nuit", "nombre", "jarvis_affichage", "DOUCEUR_NUIT", (0.3, 1.0, 0.02, "")),
    ("discret", "Réacteur", "Mode discret en veille", "bool", "jarvis_affichage", "MODE_DISCRET", None),
    ("delai_discret", "Réacteur", "Se réduit après", "duree", "jarvis_affichage", "DELAI_DISCRET", (5, 300, 5)),
    ("taille_discrete", "Réacteur", "Taille en mode discret", "nombre", "jarvis_affichage", "TAILLE_DISCRETE", (0.25, 0.8, 0.01, "")),
    ("panneau_compact", "Réacteur", "Jauges visibles en mode discret", "bool", "jarvis_affichage", "PANNEAU_COMPACT", None),
    ("icones", "Réacteur", "Icônes des jauges", "bool", "jarvis_affichage", "ICONES_JAUGES", None),
    ("halo", "Réacteur", "Halo lumineux", "bool", "jarvis_affichage", "HALO", None),
    ("relief", "Réacteur", "Effet de relief (disque et panneaux)", "bool", "jarvis_affichage", "RELIEF", None),
    ("fetes", "Réacteur", "Animations de minuit et d'anniversaire", "bool", "jarvis_affichage", "FETES", None),
    ("taille", "Réacteur", "Taille du réacteur (au prochain démarrage)", "nombre", "reacteur", "TAILLE", (180, 400, 10, "")),
    ("volume_bip", "Son", "Volume du bip de réveil", "nombre", "jarvis_voix", "VOLUME_BIP", (0.05, 1.0, 0.05, "")),
    ("volume_fin", "Son", "Son de fin d'écoute (part du bip)", "nombre", "jarvis_voix", "VOLUME_FIN_ECOUTE", (0.0, 1.5, 0.05, "")),
    ("delai_suite", "Son", "Enchaîner sans redire « Jarvis » pendant", "nombre", "jarvis_claude", "DELAI_SUITE", (3, 20, 1, "s")),
    ("deux_voix", "Profils", "Histoires à deux voix", "bool", "jarvis_enfant", "DEUX_VOIX", None),
    ("variation", "Son", "Voix légèrement variée d'une phrase à l'autre", "bool", "jarvis_voix", "VARIATION_VOIX", None),
    ("francais", "Profils", "Vidéos des enfants : en français seulement", "bool", "jarvis_enfant", "FRANCAIS_SEULEMENT", None),
    ("alertes", "Alertes", "Annoncer les alertes météo", "bool", "jarvis_vigilance", "ACTIVE", None),
    ("niveau_alertes", "Alertes", "À partir de la vigilance", "choix", "jarvis_vigilance", "NIVEAU_MIN", [("jaune", 2), ("orange", 3), ("rouge", 4)]),
]
JAUGES_POSSIBLES = (("CPU", "Processeur"), ("RAM", "Mémoire"), ("GPU", "Carte graphique"), ("NET", "Réseau"), ("TMP", "Température"))

# Une courte phrase grise sous les réglages qui ne s'expliquent pas tout seuls
AIDES = {
    "cycle": "Plus le nombre est petit, plus les couleurs défilent vite.",
    "discret": "Quand Jarvis est au repos, le réacteur se réduit pour moins gêner sur le Bureau.",
    "delai_discret": "Temps de repos avant que le réacteur se réduise. À droite du curseur : il ne se réduit jamais.",
    "delai_suite": "Après une réponse, Jarvis écoute encore ce temps-là : tu peux enchaîner sans redire « Jarvis ». Plus c'est "
                   "long, plus la conversation est naturelle, mais Jarvis risque de prendre pour lui une phrase dite à quelqu'un "
                   "d'autre. Il n'écoute jamais de suite quand le PC joue du son.",
    "volume_fin": "Réglé en part du bip de réveil : tout à gauche, ce son est muet.",
    "niveau_alertes": "« jaune » annonce tout, « rouge » seulement les alertes les plus graves.",
}
# Comment afficher la valeur d'un curseur : "pour_cent" (0,72 -> 72 %), "plage" (sa place entre le mini et le maxi), "px"
FORMATS = {
    "vitesse_reflet": "plage", "longueur_reflet": "plage", "force_regard": "plage", "force_danse": "plage",
    "douceur_nuit": "pour_cent", "taille_discrete": "pour_cent", "volume_bip": "pour_cent", "volume_fin": "pour_cent",
    "taille": "px",
}

DEFAUTS = {}
_charge = False


def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    provisoire = FICHIER + ".tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=1)
    os.replace(provisoire, FICHIER)


def valeur(cle):
    for c, _, _, _, mod, attr, _ in REGLAGES:
        if c == cle:
            m = _module(mod)
            return getattr(m, attr, None) if m else None
    return None


def _appliquer(cle, val):
    """Applique un réglage tout de suite (sans l'enregistrer)."""
    for c, _, _, genre, mod, attr, options in REGLAGES:
        if c == cle:
            m = _module(mod)
            if m is None:
                return
            if genre == "nombre":
                val = type(getattr(m, attr, val))(val) if isinstance(getattr(m, attr, None), int) and float(val).is_integer() else float(val)
            setattr(m, attr, val)
            return
    if cle == "micro" and val in SENSIBILITE_MICRO:
        m = _module("jarvis_claude")
        for attr, v in SENSIBILITE_MICRO[val].items():
            setattr(m, attr, v)
    elif cle == "reveil" and val in SENSIBILITE_REVEIL:
        m = _module("jarvis_claude")
        for attr, v in SENSIBILITE_REVEIL[val].items():
            setattr(m, attr, v)
    elif cle == "micro_coupe":
        m = _module("jarvis_claude")
        if m is not None:
            m.micro_coupe = bool(val)
            if val:
                print("(Micro coupé : réglage retrouvé au démarrage.)")
    elif cle == "nuit_auto" and val in NUIT_AUTO:
        jarvis_config.HEURES_NUIT = NUIT_AUTO[val]
    elif cle == "jauges":
        m = _module("jarvis_affichage")
        if m and isinstance(val, (list, tuple)) and val:
            m.JAUGES = tuple(val)


def regler(cle, val):
    """Applique et enregistre un réglage."""
    _appliquer(cle, val)
    donnees = _lire()
    donnees[cle] = val
    _ecrire(donnees)


def charger():
    """Au démarrage : retient les valeurs d'origine (pour « par défaut »), puis applique preferences.json."""
    global _charge
    if not _charge:
        for c, _, _, _, mod, attr, _ in REGLAGES:
            m = _module(mod)
            if m is not None and hasattr(m, attr):
                DEFAUTS[c] = getattr(m, attr)
        DEFAUTS.update(micro="normale", reveil="normale", nuit_auto="non", micro_coupe=False)
        m = _module("jarvis_affichage")
        if m is not None:
            DEFAUTS["jauges"] = list(m.JAUGES)
        _charge = True
    for cle, val in _lire().items():
        try:
            _appliquer(cle, val)
        except Exception as erreur:
            print("Réglage ignoré :", cle, erreur)


def par_defaut():
    """Remet tous les réglages comme à l'origine. Ne touche ni aux profils, ni aux mémoires, ni aux voix."""
    for cle, val in DEFAUTS.items():
        try:
            _appliquer(cle, val)
        except Exception:
            pass
    for fichier in (FICHIER, jarvis_config.chemin("apparence.json")):
        try:
            os.remove(fichier)
        except OSError:
            pass
    try:
        import jarvis_extras
        jarvis_extras.appliquer_couleur("vice city")
        import jarvis_voix
        jarvis_voix.regler_voix("henri", jarvis_voix.VITESSE_NORMALE)
    except Exception as erreur:
        print("Par défaut :", erreur)
    demarrage_windows(True)


def choix_actuel(cle):
    val = _lire().get(cle)
    return val if val is not None else DEFAUTS.get(cle)


# ---------- Démarrage avec Windows ----------

def _raccourci_demarrage():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", "Jarvis.lnk")


def _raccourci_range():
    return jarvis_config.chemin("Jarvis-demarrage-desactive.lnk")


def demarrage_actif():
    return os.path.exists(_raccourci_demarrage())


def demarrage_windows(actif):
    """Active ou non le lancement avec Windows : le raccourci est rangé dans le dossier de Jarvis, jamais effacé."""
    import shutil
    lien, range_ = _raccourci_demarrage(), _raccourci_range()
    try:
        if actif and not os.path.exists(lien):
            source = range_ if os.path.exists(range_) else jarvis_config.chemin("Jarvis.lnk")
            if os.path.exists(source):
                (shutil.move if source == range_ else shutil.copy)(source, lien)
        elif not actif and os.path.exists(lien):
            shutil.move(lien, range_)
    except OSError as erreur:
        print("Démarrage avec Windows :", erreur)
    return demarrage_actif()


# ---------- Sauvegarde ----------

def sauvegarder():
    os.makedirs(DOSSIER_SAUVEGARDES, exist_ok=True)
    chemin = os.path.join(DOSSIER_SAUVEGARDES, "Jarvis-sauvegarde-" + time.strftime("%Y-%m-%d_%Hh%M") + ".zip")
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for nom in FICHIERS_SAUVEGARDE:
            if os.path.isfile(jarvis_config.chemin(nom)):
                z.write(jarvis_config.chemin(nom), nom)
        for dossier in DOSSIERS_SAUVEGARDE:
            racine = jarvis_config.chemin(dossier)
            for base, _, fichiers in os.walk(racine):
                for f in fichiers:
                    complet = os.path.join(base, f)
                    z.write(complet, os.path.relpath(complet, jarvis_config.DOSSIER))
    return chemin


def restaurer(chemin):
    """Remet les fichiers d'une sauvegarde (seulement des fichiers personnels connus, jamais de programme)."""
    autorises = set(FICHIERS_SAUVEGARDE)
    remis = 0
    with zipfile.ZipFile(chemin) as z:
        for nom in z.namelist():
            propre = nom.replace("\\", "/")
            if ".." in propre or propre.startswith("/"):
                continue
            if propre in autorises or (propre.split("/")[0] in DOSSIERS_SAUVEGARDE and not propre.endswith(".py")):
                cible = jarvis_config.chemin(*propre.split("/"))
                os.makedirs(os.path.dirname(cible), exist_ok=True)
                with z.open(nom) as source, open(cible, "wb") as sortie:
                    sortie.write(source.read())
                remis += 1
    return remis


# ---------- Aide ----------

AIDE = [
    ("Bases", "« Jarvis », puis ta demande", "Un bip : Jarvis écoute. Un son léger : il a entendu."),
    ("Bases", "« Jarvis, stop » / « tais-toi »", "Il se tait. Dire « Jarvis » pendant qu'il parle lui coupe la parole."),
    ("Bases", "« Jarvis, répète »", "Redit la dernière réponse."),
    ("Bases", "« nouvelle conversation »", "Repart de zéro."),
    ("Bases", "Ctrl + Alt + J", "Ouvre la fenêtre pour écrire à Jarvis, depuis n'importe quelle fenêtre."),
    ("Bases", "« règle ton micro »", "Jarvis mesure le bruit de la pièce et choisit sa sensibilité tout seul."),
    ("Bases", "« qu'est-ce que tu sais faire ? »", "Le résumé des commandes."),
    ("Bases", "« quand tu entends mes mots, c'est mets-moi »", "Jarvis retient la correction pour la suite. « oublie la correction mes mots »."),
    ("Bases", "« oui » / « non » après « Tu voulais dire… ? »",
     "Quand une phrase ressemble de très près à une commande connue, Jarvis la propose au lieu de se tromper."),
    ("Bases", "« premiers pas »", "Rouvre la fenêtre de bienvenue : comment me parler et quoi essayer."),
    ("Bases", "« fais un diagnostic »", "Vérifie le micro, le son, Whisper, Claude et la connexion (onglet Santé)."),
    ("Heure et météo", "« quelle heure est-il ? », « quel jour sommes-nous ? »", ""),
    ("Heure et météo", "« quelle heure est-il à Tokyo ? »", "L'heure dans une autre ville."),
    ("Heure et météo", "« quel temps fait-il demain ? »", "La météo de ta ville (« ma ville est … » pour la changer)."),
    ("Heure et météo", "« y a-t-il une alerte météo ? »", "La vigilance de Météo-France pour ton département."),
    ("Rappels", "« minuteur pâtes 10 minutes »", "« combien de temps pour les pâtes ? », « annule le minuteur du four »."),
    ("Rappels", "« rappelle-moi à 18 h d'appeler le garage »", "« quels sont mes rappels ? », « annule mes rappels »."),
    ("Rappels", "« réveille-moi demain à 7 h »", ""),
    ("Rappels", "« lance un chrono », « arrête le chrono »", ""),
    ("Famille", "« crée un profil pour Marie », « Jarvis, c'est Marie »", "Chaque profil a sa mémoire et ses notes."),
    ("Famille", "« apprends ma voix », « oublie ma voix »", "Jarvis reconnaît qui parle et change de profil tout seul."),
    ("Famille", "« Léo a piscine mercredi à 14 h »", "Calendrier : rappel la veille et une heure avant. « qu'est-ce qu'on a demain ? »"),
    ("Famille", "« dis à Marie que je rentre tard »", "Le message est dit dès que Marie parle à Jarvis."),
    ("Famille", "« on fait un quiz en famille »", "Chacun son tour, les points de chacun. « on arrête le quiz »."),
    ("Famille", "« qu'est-ce qu'on a fait aujourd'hui ? »", "Le résumé de la journée."),
    ("Famille", "« ma musique du matin, c'est … »", "« Jarvis, bonjour » la lance ensuite."),
    ("Enfants", "« active le mode enfant »", "YouTube Kids, recherches filtrées, quiz, devinettes, histoires."),
    ("Enfants", "« mets une vidéo de dinosaures »", "Cherche sur YouTube Kids et lance la première vidéo en français."),
    ("Enfants", "« raconte-moi une histoire », « raconte la suite »", "Histoires lues à deux voix."),
    ("Enfants", "« on fait les devoirs », « on arrête les devoirs »", "Au niveau de sa classe (« Léo est en CE1 »)."),
    ("Enfants", "« donne-moi mon défi », « combien j'ai d'étoiles ? »", "Une étoile par défi réussi, bilan le dimanche."),
    ("Enfants", "« c'est l'heure du dodo »", "Histoire calme, puis Jarvis s'endort jusqu'au matin."),
    ("Musique et vidéo", "« mets Get Lucky de Daft Punk », « mets de la musique »", ""),
    ("Musique et vidéo", "« pause », « suivant », « monte le son », « baisse le son du navigateur »", ""),
    ("Musique et vidéo", "« qu'est-ce qui joue ? », « c'est quoi cette musique ? »",
     "Spotify, Deezer, YouTube, VLC… : le titre que l'application donne à Windows."),
    ("Musique et vidéo", "« avance de 30 secondes », « recule de 10 secondes »", ""),
    ("Musique et vidéo", "« résume cette vidéo »", "Sur YouTube, avec la transcription de la vidéo."),
    ("Navigateur", "« cherche des recettes de crêpes sur YouTube »", "Aussi Google, Amazon, Wikipédia, Leboncoin..."),
    ("Navigateur", "« clique sur Connexion », « la deuxième vidéo »", "« fais défiler », « reviens en arrière »."),
    ("Navigateur", "« lis-moi cette page », « résume cette page »", ""),
    ("Navigateur", "« où j'en étais ? »", "Rouvre tes onglets (Chrome, Edge, Firefox, Brave...)."),
    ("PC", "« ouvre le navigateur », « ouvre Chrome », « ferme Firefox », « ferme tout »",
     "Le navigateur est celui choisi dans Windows. « ferme tout » demande confirmation."),
    ("PC", "« mets Chrome à gauche », « affiche le bureau »", ""),
    ("PC", "« fais une capture d'écran », « qu'est-ce qu'il y a à l'écran ? »", ""),
    ("PC", "« ouvre le dernier téléchargement »", ""),
    ("PC", "« cherche le fichier facture »", ""),
    ("PC", "« état du PC », « pourquoi ça rame ? »", ""),
    ("PC", "« plus fort », « moins fort », « mets le son à fond »", ""),
    ("PC", "« zoom avant », « zoom arrière », « zoom normal »", "Dans le navigateur et la plupart des applications."),
    ("PC", "« active le Wi-Fi », « coupe le Wi-Fi », « le Wi-Fi est activé ? »", "Le Wi-Fi de ce PC."),
    ("PC", "« vide la corbeille »", "Jarvis dit ce qu'elle contient, puis la vide seulement après « oui »."),
    ("PC", "« ouvre le panneau de configuration », « va sur Ameli », « ouvre Leboncoin »",
     "Sites courants : Amazon, Gmail, CAF, Ameli, impôts, La Poste, Doctolib…"),
    ("PC", "« ne me préviens plus pour le disque », « préviens-moi pour le disque »",
     "Jarvis prévient une fois quand le disque est presque plein."),
    ("PC", "« installe une IA gratuite sur mon PC »",
     "Jarvis vérifie d'abord si le PC le permet, puis guide l'installation pas à pas. Rien ne sort du PC."),
    ("PC", "« déconnecte-toi de Claude », « change de compte Claude »", "Ouvre les Réglages, onglet Assistants."),
    ("PC", "« éteins l'ordinateur », « mets l'ordinateur en veille »", "Toujours avec confirmation."),
    ("Textes", "« dicte : je serai là dans dix minutes »", "Tape le texte dans la fenêtre active."),
    ("Textes", "« lis ça », « lis ce que j'ai copié », « traduis le texte copié en anglais »", ""),
    ("Textes", "« note que… », « lis mes notes »", ""),
    ("Textes", "« ajoute du pain à la liste », « lis-moi la liste »", ""),
    ("Cuisine", "« donne-moi la recette des crêpes étape par étape »", "Puis « étape suivante », « répète l'étape »."),
    ("Mémoire", "« retiens que… », « qu'est-ce que tu as retenu ? », « oublie que… »", ""),
    ("Mémoire", "« qu'est-ce que tu as retenu sur ma voiture ? », « rappelle-moi ce qu'on avait décidé pour la terrasse »",
     "Jarvis cherche dans ce qu'il a retenu. Tout se voit et se corrige dans Réglages, onglet Historique."),
    ("Modes", "« active le mode nuit »", "Réponses écrites, sans voix ni bip (les rappels sonnent)."),
    ("Modes", "« active le mode cinéma », « active le mode invité »", ""),
    ("Modes", "« mets le réacteur en bleu »", "Thèmes : Vice City, Iron Man, Océan, Forêt, Aurore, Galaxie, bleu, vert, rouge, violet, orange."),
    ("Voix", "« prends une voix de femme », « parle plus vite »", ""),
    ("Agenda", "« relie mon agenda »", "Google Agenda, Outlook, iCloud ou un autre : une fenêtre te guide."),
    ("Agenda", "« qu'est-ce que j'ai demain ? », « c'est quand le dentiste ? »", "Rappel la veille à 19 h."),
    ("Mails", "« relie mes mails »", "Gmail, Orange, Free, La Poste, Yahoo, iCloud ou une autre : une fenêtre te guide."),
    ("Mails", "« est-ce que j'ai des nouveaux mails ? », « lis-moi mes mails »", "Chaque profil a sa boîte mail."),
    ("Mails", "« envoie un mail à Marie pour lui dire que… », « envoie-moi un mail pour me rappeler de… »",
     "Lu et affiché, puis envoyé seulement après « oui ». Destinataire : quelqu'un à qui tu as déjà écrit "
     "(ou un contact iCloud)."),
    ("Maison", "« allume la télé », « mets France 2 », « monte le son de la télé », « lance Netflix sur la télé »",
     "Par le Freebox Player POP. Une fois au début : « associe la télé »."),
    ("Maison", "« allume l'Apple TV », « mets l'Apple TV en pause », « qu'est-ce qui passe sur l'Apple TV ? », "
     "« lance Netflix sur l'Apple TV »", "Une fois au début : « associe l'Apple TV »."),
    ("Maison", "« mets France 2 sur la télé de la chambre », « éteins la télé du salon »",
     "Plusieurs télés : décrites dans le fichier tele/teles.json, puis « associe la télé de la chambre »."),
    ("Maison", "« est-ce que la PS5 est allumée ? », « allume la PS5 », « mets la PS5 en veille »",
     "Une fois au début : « relie la PS5 » (compte PlayStation, puis code affiché par la console)."),
    ("Maison", "« il reste combien d'encre ? », « l'imprimante est allumée ? »", "Lecture seule, rien n'est imprimé."),
    ("Jarvis", "Écrire au lieu de parler : clique dans la fenêtre au-dessus du réacteur, écris, puis Entrée",
     "Jarvis répond au même endroit, et à voix haute (sauf en mode nuit). Échap annule, Ctrl+V colle."),
    ("Jarvis", "« active la tablette », « montre le QR code de la tablette », « désactive la tablette »",
     "Jarvis sur une tablette de la maison : on vise le QR code, puis on ajoute la page à l'écran d'accueil. "
     "Il y parle comme en mode enfant et n'y fait aucune action sur le PC."),
    ("Jarvis", "« ouvre les réglages »", "Cette fenêtre."),
    ("Jarvis", "« cherche les mises à jour », « mets-toi à jour », « quelle est ta version ? »", ""),
    ("Jarvis", "« redémarre-toi »", ""),
    ("Jarvis", "Désinstaller Jarvis : onglet « À propos », bouton « Désinstaller Jarvis »",
     "Retire tout ce qui a été installé pour lui, après une dernière confirmation. Tu peux garder tes fichiers personnels."),
]


# ---------- Historique ----------

_ATTENTES = set()


def _phrases_d_attente():
    """Les phrases d'attente de Jarvis (« Une petite seconde. », « Ça prend un peu plus de temps que d'habitude. »...),
    lues dans jarvis_claude.py sans le charger : elles ne sont pas la réponse et ne vont pas dans l'historique."""
    if not _ATTENTES:
        try:
            import ast
            with open(jarvis_config.chemin("jarvis_claude.py"), encoding="utf-8") as f:
                arbre = ast.parse(f.read())
            for n in arbre.body:
                if isinstance(n, ast.Assign) and any(getattr(c, "id", "") in ("PATIENCE", "PATIENCE_SUITE",
                                                                                "PATIENCE_PAR_SUJET") for c in n.targets):
                    for s in ast.walk(n.value):
                        if isinstance(s, ast.Constant) and isinstance(s.value, str) and not s.value.startswith("\\b"):
                            _ATTENTES.add(s.value)
        except Exception:
            pass
        _ATTENTES.update(("Je m'en occupe.", "C'est parti.", "Je regarde ça.", "Une petite seconde.", "Laisse-moi voir.",
                          "Ça prend un peu plus de temps que d'habitude.", "Je suis toujours dessus, merci de patienter.",
                          "Encore un petit instant, j'y suis presque."))
    return _ATTENTES


def historique(nombre=60):
    """[(demande, réponse)] : les dernières demandes, d'après le journal de Jarvis (les phrases d'attente sont sautées)."""
    try:
        with open(jarvis_config.chemin("jarvis.log"), encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()[-4000:]
    except OSError:
        return []
    attentes = _phrases_d_attente()
    resultat, demande = [], None
    for ligne in lignes:
        ligne = ligne.rstrip("\n")
        if ligne.startswith("Demande :"):
            texte = ligne[len("Demande :"):].strip()
            m = re.match(r"«\s*(.*?)\s*»", texte)
            demande = m.group(1) if m else texte
        elif ligne.startswith("JARVIS :") and demande:
            reponse = ligne[len("JARVIS :"):].strip()
            if reponse in attentes:
                continue
            resultat.append((demande, reponse))
            demande = None
    return resultat[-nombre:][::-1]


# ---------- La fenêtre ----------

_fenetre = {"ouverte": False, "devant": False}



def _texte_souple(etiquette):
    """Texte d'une ligne de réglage : il prend la place laissée par l'élément de droite et passe à la ligne selon
    la largeur réelle (petits écrans, échelles Windows), au lieu d'être coupé."""
    etiquette.pack(side="left", fill="x", expand=True, padx=12, pady=9)
    etiquette.bind("<Configure>", lambda e: etiquette.config(wraplength=max(60, e.width - 4)), add="+")
    return etiquette

def ouvrir():
    """Ouvre la fenêtre de réglages (ou la ramène devant si elle est déjà ouverte)."""
    if _fenetre["ouverte"]:
        fil = _fenetre.get("fil")
        bloquee = (fil is not None and not fil.is_alive()) or time.time() - _fenetre.get("pouls", 0) > 8
        if not bloquee:
            _fenetre["devant"] = True
            return
        # la fenêtre ne donne plus signe de vie (fil mort ou figé) : on repart sur une neuve
        print("(Réglages : l'ancienne fenêtre ne répondait plus, j'en ouvre une neuve.)")
    jeton = object()
    _fenetre["jeton"] = jeton
    _fenetre["ouverte"] = True
    _fenetre["pouls"] = time.time()
    fil = threading.Thread(target=_fenetre_principale, args=(jeton,), daemon=True)
    _fenetre["fil"] = fil
    fil.start()


def _couleurs_theme():
    m = _module("reacteur")
    palette = getattr(m, "COULEURS_VEILLE", None) if m else None
    return list(palette) if palette else ["#ff2e97", "#ff8c42", "#9d4dff"]


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(x))) for x in c)


def _melange(a, b, f):
    return tuple(a[i] + (b[i] - a[i]) * f for i in range(3))


def _degrade(palette, t):
    n = len(palette)
    i = int(t) % n
    f = t - int(t)
    f = f * f * (3 - 2 * f)
    return _melange(_rgb(palette[i]), _rgb(palette[(i + 1) % n]), f)


def _fenetre_principale(jeton=None):
    try:
        _construire()
    except Exception as erreur:
        print("Fenêtre de réglages :", erreur)
    finally:
        # Tk n'aime pas qu'un autre fil libère ses objets (interpréteur « abandonné », images qui ne
        # se suppriment pas) : on vide tout ici, dans le fil de la fenêtre, avant qu'il se termine.
        try:
            _CACHE_IMG.clear()
            import gc
            gc.collect()
        except Exception:
            pass
        if jeton is None or _fenetre.get("jeton") is jeton:
            _fenetre["ouverte"] = False


def _construire():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    import jarvis_extras
    import jarvis_profils

    if not _charge:
        charger()
    _CACHE_IMG.clear()
    theme_pose = {"nom": _nom_theme()}
    _poser_theme(theme_pose["nom"])
    racine = tk.Tk()
    racine.title("Jarvis - Réglages")
    racine.configure(bg=FOND)
    # Jarvis connaît la vraie résolution de l'écran : tout est agrandi comme les polices (125 %, 150 %...)
    sc = max(1.0, racine.winfo_fpixels("1i") / 96.0)

    def px(v):
        return int(round(v * sc))
    largeur = min(px(1000), int(racine.winfo_screenwidth() * 0.9))
    hauteur = min(px(680), int(racine.winfo_screenheight() * 0.82))
    racine.geometry(f"{largeur}x{hauteur}")
    racine.minsize(min(px(880), largeur), min(px(480), hauteur))
    try:
        racine.iconbitmap(jarvis_config.chemin("installateur", "jarvis.ico"))
    except Exception:
        pass
    try:                                          # barre de titre sombre (Windows 10/11)
        import ctypes
        racine.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(racine.winfo_id())
        sombre = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(sombre), 4)
    except Exception:
        pass

    accent = {"c": ACCENT}
    survol = {"p": None, "nom": ""}       # thème survolé : l'aperçu le montre avant qu'on clique

    # --- En-tête : titre et ligne lumineuse animée ---
    entete = tk.Canvas(racine, height=px(74), bg=FOND, highlightthickness=0)
    entete.pack(fill="x")
    import jarvis_claude
    entete.create_text(px(28), px(28), text="J A R V I S", anchor="w", fill=TEXTE, font=("Segoe UI Light", 20))
    entete.create_text(px(30), px(54), text="Réglages · version " + jarvis_claude.VERSION, anchor="w", fill=DISCRET, font=POLICE)

    corps = tk.Frame(racine, bg=FOND)
    corps.pack(fill="both", expand=True, padx=16, pady=(4, 14))
    menu_cadre = tk.Frame(corps, bg=FOND)
    menu_cadre.pack(side="left", fill="y", padx=(0, 12))
    # Sur un petit écran ou dans une fenêtre réduite, tous les onglets ne tiennent pas : la colonne défile
    # (molette sur la colonne, ou clic sur un onglet qui se remet de lui-même en vue), avec une fine barre.
    menu_barre = tk.Canvas(menu_cadre, width=px(6), bg=FOND, highlightthickness=0)
    menu_toile = tk.Canvas(menu_cadre, width=px(150), bg=FOND, highlightthickness=0)
    menu_barre.pack(side="right", fill="y", pady=4)
    menu_toile.pack(side="left", fill="y")
    menu = tk.Frame(menu_toile, bg=FOND)
    menu_fenetre = menu_toile.create_window((0, 0), window=menu, anchor="nw")

    def position_barre_menu(debut, fin):
        menu_barre.delete("all")
        debut, fin = float(debut), float(fin)
        if fin - debut < 0.999:
            h = menu_barre.winfo_height()
            menu_barre.create_line(px(3), debut * h + px(3), px(3), max(debut * h + px(8), fin * h - px(3)), width=px(4),
                                   capstyle="round", fill=ASCENS)
    menu_toile.configure(yscrollcommand=position_barre_menu)
    menu.bind("<Configure>", lambda e: menu_toile.configure(scrollregion=(0, 0, e.width, e.height)))
    menu_toile.bind("<Configure>", lambda e: menu_toile.itemconfigure(menu_fenetre, width=e.width))
    contenu_cadre = tk.Frame(corps, bg=PANNEAU, highlightthickness=1, highlightbackground=BORD)
    contenu_cadre.pack(side="left", fill="both", expand=True)
    apercu = tk.Canvas(corps, width=px(230), bg=FOND, highlightthickness=0)
    apercu.pack(side="left", fill="y", padx=(12, 0))

    # Zone de contenu défilante
    toile = tk.Canvas(contenu_cadre, bg=PANNEAU, highlightthickness=0)
    # pas de barre de défilement Windows (claire) : la molette fait défiler, et une fine barre est dessinée
    barre = tk.Canvas(contenu_cadre, width=px(6), bg=PANNEAU, highlightthickness=0)

    def position_barre(debut, fin):
        barre.delete("all")
        debut, fin = float(debut), float(fin)
        if fin - debut < 0.999:
            h = barre.winfo_height()
            barre.create_line(px(3), debut * h + px(3), px(3), max(debut * h + px(8), fin * h - px(3)), width=px(4),
                              capstyle="round", fill=ASCENS)
    toile.configure(yscrollcommand=position_barre)
    barre.pack(side="right", fill="y", pady=4)
    toile.pack(side="left", fill="both", expand=True)
    page = tk.Frame(toile, bg=PANNEAU)
    fenetre_page = toile.create_window((0, 0), window=page, anchor="nw")
    page.bind("<Configure>", lambda e: toile.configure(scrollregion=toile.bbox("all")))
    toile.bind("<Configure>", lambda e: toile.itemconfigure(fenetre_page, width=e.width))

    def molette(e):
        cible = toile
        try:
            w = racine.winfo_containing(e.x_root, e.y_root)
            while w is not None:
                if w is menu_cadre:
                    debut, fin = menu_toile.yview()
                    if fin - debut < 0.999:           # la colonne déborde : c'est elle qui défile
                        cible = menu_toile
                    break
                w = w.master
        except Exception:
            pass
        cible.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
    racine.bind_all("<MouseWheel>", molette)

    def vider():
        for w in page.winfo_children():
            w.destroy()
        toile.yview_moveto(0)

    def titre(texte, sous=""):
        tk.Label(page, text=texte, bg=PANNEAU, fg=TEXTE, font=("Segoe UI Semibold", 15)).pack(anchor="w", padx=22, pady=(18, 0))
        if sous:
            tk.Label(page, text=sous, bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=(2, 8))

    def section(texte):
        ligne_s = tk.Frame(page, bg=PANNEAU)
        ligne_s.pack(anchor="w", fill="x", padx=22, pady=(16, 4))
        Lb, Hb = px(5), px(14)

        def dessin_s(sf, k):
            __import__("pygame").draw.rect(sf, _rgb(accent["c"]), (0, 0, Lb * k, Hb * k), border_radius=px(2.5) * k)
        barre = tk.Label(ligne_s, image=_image_aa(Lb, Hb, PANNEAU, dessin_s, ("section", accent["c"], PANNEAU)), bg=PANNEAU, bd=0)
        barre.pack(side="left", padx=(0, 8))
        tk.Label(ligne_s, text=texte.upper(), bg=PANNEAU, fg=accent["c"], font=("Segoe UI Semibold", 9)).pack(side="left")

    def carte(parent):
        """Une carte aux coins arrondis, avec une ombre dessous et un reflet dessus (effet de relief)."""
        haut = tk.Canvas(parent, bg=PANNEAU, highlightthickness=0, height=px(52))
        haut.pack(fill="x", padx=px(14), pady=px(2))
        cadre = tk.Frame(haut, bg=PANNEAU2)
        fen = haut.create_window(px(9), px(5), window=cadre, anchor="nw")

        def redessiner(_=None):
            w = max(haut.winfo_width(), 20)
            h = cadre.winfo_reqheight() + px(12)
            if int(float(haut.cget("height"))) != h:
                haut.configure(height=h)
            haut.itemconfigure(fen, width=max(1, w - px(18)))
            haut.delete("fond")
            ombre = _hex(_melange(_rgb(PANNEAU), (0, 0, 0), 0.55))
            lumiere = _hex(_melange(_rgb(PANNEAU2), (255, 255, 255), 0.16))

            def dessin(sf, k, w=w, h=h):
                pygame_ = __import__("pygame")
                pygame_.draw.rect(sf, _rgb(ombre), (2 * k, px(5) * k, (w - 4) * k, (h - px(5) - 1) * k), border_radius=px(13) * k)
                pygame_.draw.rect(sf, _rgb(PANNEAU2), (k, k, (w - 3) * k, (h - px(5) - 1) * k), border_radius=px(13) * k)
                pygame_.draw.rect(sf, _rgb(BORD), (k, k, (w - 3) * k, (h - px(5) - 1) * k), width=max(1, k), border_radius=px(13) * k)
                # effet verre : reflet translucide sur le haut de la carte, bord haut brillant, liseré clair en bas
                x0_, y0_, ww_, hh_ = k, k, (w - 3) * k, (h - px(5) - 1) * k
                masque = pygame_.Surface((w * k, h * k), pygame_.SRCALPHA)
                pygame_.draw.rect(masque, (255, 255, 255, 255), (x0_, y0_, ww_, hh_), border_radius=px(13) * k)
                reflet = pygame_.Surface((w * k, h * k), pygame_.SRCALPHA)
                haut_reflet = px(5) * k
                for yy in range(haut_reflet):
                    alpha = int(150 * (1 - yy / haut_reflet) ** 1.2)
                    pygame_.draw.line(reflet, (255, 255, 255, alpha), (0, y0_ + yy), (w * k, y0_ + yy))
                reflet.blit(masque, (0, 0), special_flags=pygame_.BLEND_RGBA_MULT)
                sf.blit(reflet, (0, 0))
                pygame_.draw.line(sf, _rgb(_hex(_melange(_rgb(PANNEAU2), (255, 255, 255), 0.6))),
                                  (px(15) * k, 2 * k), ((w - px(15)) * k, 2 * k), max(1, k))
                pygame_.draw.line(sf, _rgb(_hex(_melange(_rgb(PANNEAU2), (255, 255, 255), 0.12))),
                                  (px(15) * k, y0_ + hh_ - 2 * k), ((w - px(15)) * k, y0_ + hh_ - 2 * k), max(1, k))
            img = _image_aa(w, h, PANNEAU, dessin, ("carte2", w, h, PANNEAU, PANNEAU2, BORD))
            haut.create_image(0, 0, anchor="nw", image=img, tags="fond")
            haut.tag_lower("fond")
        cadre.bind("<Configure>", redessiner)
        haut.bind("<Configure>", redessiner)
        return cadre

    def ligne():
        return carte(page)

    def bouton(parent, texte, action, fort=False):
        import tkinter.font as tkfont
        police_b = ("Segoe UI Semibold", 10)
        fond_parent = parent.cget("bg")
        L_b = tkfont.Font(family="Segoe UI Semibold", size=10).measure(texte) + px(36)
        H_b = px(34)

        def image_bouton(survole):
            base = accent["c"] if fort else BORD
            col = (_hex(_melange(_rgb(accent["c"]), (255, 255, 255), 0.25)) if fort else SURVOL) if survole else base
            haut_c = _hex(_melange(_rgb(col), (255, 255, 255), 0.18))
            bas_c = _hex(_melange(_rgb(col), (0, 0, 0), 0.35))

            def dessin(sf, k):
                pg = __import__("pygame")
                pg.draw.rect(sf, _rgb(bas_c), (k, 2 * k, (L_b - 2) * k, (H_b - 2) * k), border_radius=px(10) * k)
                pg.draw.rect(sf, _rgb(col), (k, k, (L_b - 2) * k, (H_b - px(3)) * k), border_radius=px(10) * k)
                pg.draw.line(sf, _rgb(haut_c), (px(9) * k, 2 * k), ((L_b - px(9)) * k, 2 * k), k)
            return _image_aa(L_b, H_b, fond_parent, dessin, ("bouton", L_b, col, fond_parent))
        b = tk.Label(parent, text=texte, image=image_bouton(False), compound="center", bg=fond_parent,
                     fg=ENCRE if fort else TEXTE, font=police_b, padx=0, pady=0, bd=0, cursor="hand2")
        b.bind("<Button-1>", lambda e: action())
        b.bind("<Enter>", lambda e: b.configure(image=image_bouton(True)))
        b.bind("<Leave>", lambda e: b.configure(image=image_bouton(False)))
        return b

    def interrupteur(parent, actif, changer):
        etat = {"v": bool(actif)}
        c = tk.Canvas(parent, width=px(46), height=px(24), bg=PANNEAU2, highlightthickness=0, cursor="hand2")

        def dessiner():
            c.delete("all")
            fond = accent["c"] if etat["v"] else OFF
            L_, H_ = px(46), px(24)

            def dessin(sf, k):
                pg = __import__("pygame")
                pg.draw.rect(sf, _rgb(fond), (2 * k, 2 * k, (L_ - 4) * k, (H_ - 4) * k), border_radius=H_ * k // 2)
                x_ = (L_ - px(12) if etat["v"] else px(12)) * k
                y_ = H_ * k // 2
                r_ = px(8) * k
                pg.draw.circle(sf, _rgb(_hex(_melange(_rgb(fond), (0, 0, 0), 0.5))), (x_, y_ + k), r_)
                pg.draw.circle(sf, (251, 249, 255), (x_, y_), r_)
            img = _image_aa(L_, H_, PANNEAU2, dessin, ("inter", etat["v"], fond, PANNEAU2, OFF))
            c.create_image(0, 0, anchor="nw", image=img)

        def basculer(_=None):
            etat["v"] = not etat["v"]
            dessiner()
            changer(etat["v"])
        c.bind("<Button-1>", basculer)
        dessiner()
        return c

    def fabrique_curseur(parent, val, mini, maxi, pas, commande):
        """Curseur dessiné : rail arrondi qui se remplit, bouton rond avec une ombre."""
        L, H, marge, r = px(190), px(30), px(12), px(10)
        c = tk.Canvas(parent, width=L, height=H, bg=PANNEAU2, highlightthickness=0, cursor="hand2")

        def cale(v):
            v = min(float(maxi), max(float(mini), float(v)))
            if pas:
                v = round((v - mini) / pas) * pas + mini
            return min(float(maxi), max(float(mini), v))
        etat = {"v": cale(val)}

        def dessiner():
            c.delete("all")
            y = H // 2
            fraction = (etat["v"] - mini) / (maxi - mini) if maxi > mini else 0.0
            x = marge + fraction * (L - 2 * marge)

            def dessin(sf, k):
                pg = __import__("pygame")
                ep_ = px(7) * k
                for a_, b_, col in ((marge, L - marge, CREUX), (marge, x, accent["c"])):
                    if b_ - a_ < 1 and col != CREUX:
                        continue
                    pg.draw.line(sf, _rgb(col), (a_ * k, y * k), (b_ * k, y * k), ep_)
                    pg.draw.circle(sf, _rgb(col), (a_ * k, y * k), ep_ // 2)
                    pg.draw.circle(sf, _rgb(col), (b_ * k, y * k), ep_ // 2)
                pg.draw.circle(sf, _rgb(_hex(_melange(_rgb(PANNEAU2), (0, 0, 0), 0.55))), (x * k, (y + px(3)) * k), r * k)
                pg.draw.circle(sf, (251, 249, 255), (x * k, y * k), r * k)
                pg.draw.circle(sf, _rgb(accent["c"]), (x * k, y * k), r * k, width=px(2) * k)
                pg.draw.circle(sf, _rgb(accent["c"]), (x * k, y * k), int(px(3.5) * k))
            c._img_curseur = _image_aa(L, H, PANNEAU2, dessin)
            c.create_image(0, 0, anchor="nw", image=c._img_curseur)

        def regler_v(v):
            v = cale(v)
            if v != etat["v"]:
                etat["v"] = v
                dessiner()
                commande(v)

        def souris(e):
            f = min(1.0, max(0.0, (e.x - marge) / max(1, L - 2 * marge)))
            regler_v(mini + f * (maxi - mini))
        c.bind("<Button-1>", souris)
        c.bind("<B1-Motion>", souris)
        c.set = regler_v                      # même usage qu'un curseur Tk : .set(valeur)
        c.get = lambda: etat["v"]
        c.mini, c.maxi, c._curseur = float(mini), float(maxi), True
        dessiner()
        return c

    def curseur(parent, val, mini, maxi, pas, changer, unite="", formate=None):
        cadre = tk.Frame(parent, bg=PANNEAU2)
        affiche = tk.Label(cadre, width=8, bg=PANNEAU2, fg=TEXTE, font=POLICE, anchor="e")

        def montrer(v):
            v = float(v)
            if formate:
                affiche.configure(text=formate(v))
                return
            affiche.configure(text=(f"{v:.0f}" if pas >= 1 else f"{v:.2f}".rstrip("0").rstrip(".")) + (f" {unite}" if unite else ""))

        def bouge(v):
            montrer(v)
            changer(round(float(v) / pas) * pas if pas else float(v))
        echelle = fabrique_curseur(cadre, val, mini, maxi, pas, bouge)
        echelle.pack(side="left")
        affiche.pack(side="left", padx=(6, 0))
        montrer(val)
        return cadre

    def choix(parent, actuel, options, changer):
        variable = tk.StringVar(parent, value=actuel)
        o = tk.OptionMenu(parent, variable, *options, command=changer)
        fond_p = parent.cget("bg")
        L_o, H_o = px(190), px(34)

        def image_o(survole):
            col = SURVOL if survole else BORD
            haut_c = _hex(_melange(_rgb(col), (255, 255, 255), 0.18))
            bas_c = _hex(_melange(_rgb(col), (0, 0, 0), 0.35))

            def dessin(sf, k):
                pg = __import__("pygame")
                pg.draw.rect(sf, _rgb(bas_c), (k, 2 * k, (L_o - 2) * k, (H_o - 2) * k), border_radius=px(10) * k)
                pg.draw.rect(sf, _rgb(col), (k, k, (L_o - 2) * k, (H_o - px(3)) * k), border_radius=px(10) * k)
                pg.draw.line(sf, _rgb(haut_c), (px(9) * k, 2 * k), ((L_o - px(9)) * k, 2 * k), k)
            return _image_aa(L_o, H_o, fond_p, dessin, ("choix", L_o, col, fond_p))
        o.configure(bg=fond_p, fg=TEXTE, activebackground=fond_p, activeforeground=TEXTE, highlightthickness=0,
                    bd=0, relief="flat", font=POLICE, indicatoron=0, padx=0, pady=0,
                    image=image_o(False), compound="center")
        o.bind("<Enter>", lambda e: o.configure(image=image_o(True)))
        o.bind("<Leave>", lambda e: o.configure(image=image_o(False)))
        o["menu"].configure(bg=BORD, fg=TEXTE, activebackground=accent["c"], activeforeground=ENCRE, bd=0, font=POLICE)
        return o

    def reglage(cle, libelle, genre, options, onglet_actuel):
        cadre = ligne()
        tk.Label(cadre, text=libelle, bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        val = valeur(cle)
        if genre == "bool":
            interrupteur(cadre, val, lambda v, c=cle: regler(c, bool(v))).pack(side="right", padx=12)
        elif genre == "nombre":
            mini, maxi, pas, unite = options
            mode, formate = FORMATS.get(cle), None
            if mode == "pour_cent":
                formate = lambda v: f"{round(v * 100)} %"
            elif mode == "plage":
                formate = lambda v, a=mini, b=maxi: f"{round((v - a) / (b - a) * 100)} %"
            elif mode == "px":
                formate = lambda v: f"{int(round(v))} px"
            curseur(cadre, val if val is not None else mini, mini, maxi, pas, lambda v, c=cle: regler(c, v), unite,
                    formate).pack(side="right", padx=12)
        elif genre == "duree":
            # curseur de mini à maxi secondes, puis une dernière position « Illimité » (valeur 0)
            mini, maxi, pas = options
            illimite = maxi + pas
            depart = illimite if not val else min(max(float(val), mini), maxi)
            bloc = tk.Frame(cadre, bg=PANNEAU2)         # même présentation que les autres curseurs
            bloc.pack(side="right", padx=12)
            texte = tk.Label(bloc, bg=PANNEAU2, fg=TEXTE, font=POLICE, width=8, anchor="e")

            def nom_duree(s):
                s = int(round(float(s)))
                if s > maxi:
                    return "Illimité"
                if s < 60:
                    return f"{s} s"
                m, r = divmod(s, 60)
                return f"{m} min" + (f" {r:02d}" if r else "")

            def bouge_duree(v, c=cle):
                s = int(round(float(v) / pas) * pas)
                texte.configure(text=nom_duree(s))
                regler(c, 0 if s > maxi else s)
            fabrique_curseur(bloc, depart, mini, illimite, pas, bouge_duree).pack(side="left")
            texte.pack(side="left", padx=(6, 0))
            texte.configure(text=nom_duree(depart))
        elif genre == "choix":
            noms = [n for n, _ in options]
            actuel = next((n for n, v in options if v == val), None)
            actuel = actuel or noms[0]
            choix(cadre, actuel, noms, lambda n, c=cle, o=options: regler(c, dict(o)[n])).pack(side="right", padx=12, pady=4)
        if cle in AIDES:                       # une courte phrase grise juste sous la carte du réglage
            aide = tk.Label(page, text=AIDES[cle], bg=PANNEAU, fg=DISCRET, font=("Segoe UI", 9), wraplength=px(480),
                            justify="left", anchor="w")
            aide.pack(fill="x", padx=24, pady=(0, 4))     # passe à la ligne selon la vraie largeur (jamais coupé)
            aide.bind("<Configure>", lambda e, a=aide: a.config(wraplength=max(60, e.width - 4)), add="+")

    def remise_page(onglet, en_plus, refaire):
        """En bas d'une page : « Remettre cette page par défaut » (seulement les réglages de cette page)."""
        def remettre():
            if not messagebox.askyesno("Jarvis", "Remettre les réglages de cette page comme à l'installation ?\n\n"
                                                 "Les autres pages ne sont pas touchées.", parent=racine):
                return
            donnees = _lire()
            for cle in [e[0] for e in REGLAGES if e[1] == onglet] + list(en_plus):
                if cle in DEFAUTS:
                    try:
                        _appliquer(cle, DEFAUTS[cle])
                    except Exception as erreur:
                        print("Remise par défaut :", cle, erreur)
                donnees.pop(cle, None)
            _ecrire(donnees)
            try:
                if onglet == "Apparence":
                    jarvis_extras.choisir_couleur("vice city")
                    suivre()
                elif onglet == "Son":
                    import jarvis_voix
                    jarvis_voix.regler_voix("henri", jarvis_voix.VITESSE_NORMALE)
            except Exception as erreur:
                print("Remise par défaut :", erreur)
            refaire()
        bouton(page, "Remettre cette page par défaut", remettre).pack(anchor="w", padx=22, pady=(18, 20))

    # --- Les pages ---

    def page_apparence():
        vider()
        titre("Apparence", "Tout s'applique en direct sur le réacteur, et dans l'aperçu à droite.")
        section("Thème")
        cadre = tk.Frame(page, bg=PANNEAU)
        cadre.pack(fill="x", padx=18, pady=4)
        try:
            with open(jarvis_config.chemin("apparence.json"), encoding="utf-8") as f:
                theme_actuel = json.load(f).get("couleur", "vice city")
        except (OSError, ValueError):
            theme_actuel = "vice city"
        for i, (nom, palette) in enumerate(jarvis_extras.PALETTES.items()):
            tuile = tk.Canvas(cadre, width=px(112), height=px(58), bg=PANNEAU, highlightthickness=0, cursor="hand2")
            # une bande arrondie en dégradé, qui passe par les couleurs du thème
            x0, x1, y0, y1, rb = px(6), px(106), px(6), px(36), px(8)
            cols = [_rgb(c) for c in palette]
            for x in range(x0, x1):
                p = (x - x0) / max(1, x1 - x0 - 1) * (len(cols) - 1)
                a, b = cols[int(p)], cols[min(len(cols) - 1, int(p) + 1)]
                coupe = 0
                if x < x0 + rb:
                    coupe = rb - math.sqrt(max(0.0, rb * rb - (x0 + rb - x) ** 2))
                elif x > x1 - rb:
                    coupe = rb - math.sqrt(max(0.0, rb * rb - (x - (x1 - rb)) ** 2))
                tuile.create_line(x, y0 + coupe, x, y1 - coupe, fill=_hex(_melange(a, b, p - int(p))))
            tuile.create_text(px(56), px(47), text=nom.title(), fill=TEXTE if nom != theme_actuel else palette[0], font=("Segoe UI", 9))
            if nom == theme_actuel:
                tuile.create_rectangle(px(2), px(2), px(110), px(56), outline=palette[0], width=2)

            def choisir(_=None, n=nom):
                survol["p"] = None
                jarvis_extras.choisir_couleur(n)
                if not suivre():
                    page_apparence()
            tuile.bind("<Button-1>", choisir)
            # au survol, l'aperçu à droite prend ce thème (sans rien changer tant qu'on ne clique pas)
            tuile.bind("<Enter>", lambda e, p=palette, n=nom: survol.update(p=list(p), nom=n))
            tuile.bind("<Leave>", lambda e: survol.update(p=None))
            tuile.grid(row=i // 4, column=i % 4, padx=4, pady=4)
        for groupe, cles in (("Couleurs", ("cycle",)),
                             ("Reflets lumineux", ("vitesse_reflet", "longueur_reflet", "nb_reflets", "reflet_reacteur", "tour_reacteur")),
                             ("La nuit", ("doux_nuit", "douceur_nuit"))):
            section(groupe)
            for c, onglet, libelle, genre, _, _, options in REGLAGES:
                if c in cles:
                    reglage(c, libelle, genre, options, "Apparence")
            if groupe == "La nuit":
                cadre = ligne()
                tk.Label(cadre, text="Mode nuit automatique", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
                choix(cadre, choix_actuel("nuit_auto"), list(NUIT_AUTO), lambda n: regler("nuit_auto", n)).pack(side="right", padx=12, pady=4)
        remise_page("Apparence", ("nuit_auto",), page_apparence)

    def page_reacteur():
        vider()
        titre("Réacteur", "Comment il vit, quand il se fait discret, ses jauges, sa taille et sa place.")
        for groupe, cles in (("Vie du réacteur", ("regard", "force_regard", "danse", "force_danse", "fetes", "halo", "relief")),
                             ("Mode discret", ("discret", "delai_discret", "taille_discrete", "panneau_compact"))):
            section(groupe)
            for c, onglet, libelle, genre, _, _, options in REGLAGES:
                if c in cles:
                    reglage(c, libelle, genre, options, "Réacteur")
        section("Jauges")
        r = next(x for x in REGLAGES if x[0] == "icones")
        reglage("icones", r[2], r[3], r[6], "Apparence")
        for code, nom in JAUGES_POSSIBLES:
            cadre = ligne()
            tk.Label(cadre, text=nom, bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
            m = _module("jarvis_affichage")

            def changer(v, code=code):
                actuelles = list(getattr(_module("jarvis_affichage"), "JAUGES", ()))
                if v and code not in actuelles:
                    actuelles.append(code)
                elif not v and code in actuelles:
                    actuelles.remove(code)
                regler("jauges", [c for c, _ in JAUGES_POSSIBLES if c in actuelles])
            interrupteur(cadre, m is not None and code in m.JAUGES, changer).pack(side="right", padx=12)
        section("Taille et place")
        for c in ("taille", "devant"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Apparence")
        cadre = ligne()
        tk.Label(cadre, text="Placer le réacteur", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, "choisir…", list(COINS), placer).pack(side="right", padx=12, pady=4)
        remise_page("Réacteur", ("jauges",), page_reacteur)

    def placer(coin):
        import ctypes
        m = _module("jarvis_affichage")
        aff = getattr(m, "actuel", None) if m else None
        if aff is None:
            return
        user32 = ctypes.windll.user32
        largeur, hauteur = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = largeur - aff.w - 40 if "droite" in coin else 40
        y = hauteur - aff.h - 140 if "bas" in coin else 40
        user32.SetWindowPos(aff.hwnd, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
        aff.enregistrer_position()

    def page_son():
        vider()
        titre("Son", "Le bip, la voix et l'écoute.")
        section("Bips")
        for c in ("volume_bip", "volume_fin"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Son")
        cadre = ligne()
        tk.Label(cadre, text="Écouter les sons", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)

        def essayer():
            import jarvis_voix

            def jouer():
                jarvis_voix.bip()
                time.sleep(0.6)
                jarvis_voix.bip_fin_ecoute()
            threading.Thread(target=jouer, daemon=True).start()
        bouton(cadre, "Essayer", essayer).pack(side="right", padx=12, pady=5)
        section("Voix")
        import jarvis_voix
        cadre = ligne()
        tk.Label(cadre, text="Voix de Jarvis", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        actuelle = "Denise (femme)" if jarvis_voix.VOIX == jarvis_voix.VOIXS["denise"] else "Henri (homme)"
        choix(cadre, actuelle, ["Henri (homme)", "Denise (femme)"],
              lambda n: jarvis_voix.regler_voix("denise" if n.startswith("Denise") else "henri")).pack(side="right", padx=12, pady=4)
        cadre = ligne()
        tk.Label(cadre, text="Vitesse de la voix", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        curseur(cadre, int(jarvis_voix.VITESSE.rstrip("%")), -30, 50, 1,
                lambda v: jarvis_voix.regler_voix(vitesse=int(v)), "%").pack(side="right", padx=12)
        for c in ("variation",):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Son")
        section("Écoute")
        for c in ("delai_suite",):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Son")
        cadre = ligne()
        tk.Label(cadre, text="Pièce (sensibilité du micro)", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, choix_actuel("micro"), list(SENSIBILITE_MICRO), lambda n: regler("micro", n)).pack(side="right", padx=12, pady=4)
        cadre = ligne()
        tk.Label(cadre, text="Mot de réveil « Jarvis »", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, choix_actuel("reveil"), list(SENSIBILITE_REVEIL), lambda n: regler("reveil", n)).pack(side="right", padx=12, pady=4)
        tk.Label(page, text="« prudente » : il se réveille moins souvent par erreur quand on parle de lui ; "
                            "« sensible » : il répond plus facilement.", bg=PANNEAU, fg=DISCRET, font=POLICE,
                 wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=6)
        remise_page("Son", ("micro", "reveil"), page_son)

    def page_alertes():
        vider()
        titre("Alertes météo", "La Vigilance de Météo-France pour ton département, vérifiée toutes les 30 minutes.")
        for c in ("alertes", "niveau_alertes"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Alertes")
        remise_page("Alertes", (), page_alertes)

    def page_profils():
        vider()
        titre("Profils", "Chaque personne a sa mémoire, ses notes et, si elle le veut, sa voix reconnue.")
        lignes = [("", jarvis_profils.PRINCIPAL["prenom"] or "Profil principal", False)]
        lignes += [(i, p.get("prenom", i), bool(p.get("enfant"))) for i, p in jarvis_profils._lire().items()]
        import jarvis_famille
        for ident, prenom, enfant in lignes:
            cadre = ligne()
            tk.Label(cadre, text=prenom, bg=PANNEAU2, fg=TEXTE, font=("Segoe UI Semibold", 11)).pack(side="left", padx=12, pady=10)
            infos = ["profil principal" if not ident else ("enfant" if enfant else "adulte")]
            classe = jarvis_famille._classe_de(ident or None)
            if classe:
                infos.append(classe)
            voix = os.path.exists(os.path.join(jarvis_profils.DOSSIER, ident or "_principal", "voix.json"))
            infos.append("voix reconnue" if voix else "voix pas encore apprise")
            etoiles = len(jarvis_profils._lire().get(ident, {}).get("etoiles") or []) if ident else 0
            if etoiles:
                infos.append(f"{etoiles} étoile{'s' if etoiles > 1 else ''}")
            if (jarvis_profils.actif() or "") == ident:
                infos.append("en ce moment")
            tk.Label(cadre, text=" · ".join(infos), bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(330),
                     justify="right").pack(side="right", padx=12)
        tk.Label(page, text="À la voix : « crée un profil pour Marie », « crée un profil enfant pour Léo », « Jarvis, c'est "
                            "Marie », « apprends ma voix », « supprime le profil de Marie ».", bg=PANNEAU, fg=DISCRET,
                 font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=12)
        section("Mode enfant")
        for c in ("deux_voix", "francais"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Profils")

    def page_aide():
        vider()
        titre("Aide", "Toutes les commandes, rangées par thème. Tape un mot pour chercher.")
        recherche = tk.StringVar(racine)
        champ = tk.Entry(page, textvariable=recherche, bg=BORD, fg=TEXTE, insertbackground=TEXTE, relief="flat",
                         font=("Segoe UI", 11), highlightthickness=1, highlightbackground=SURVOL, highlightcolor=accent["c"])
        champ.pack(fill="x", padx=22, pady=(4, 8), ipady=6)
        liste = tk.Frame(page, bg=PANNEAU)
        liste.pack(fill="both", expand=True)

        def remplir(*_):
            for w in liste.winfo_children():
                w.destroy()
            cherche = recherche.get().lower().strip()
            theme = None
            for groupe, commande, detail in AIDE:
                if cherche and cherche not in (groupe + commande + detail).lower():
                    continue
                if groupe != theme:
                    theme = groupe
                    tk.Label(liste, text=groupe.upper(), bg=PANNEAU, fg=accent["c"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=22, pady=(12, 3))
                cadre = carte(liste)
                tk.Label(cadre, text=commande, bg=PANNEAU2, fg=TEXTE, font=POLICE, wraplength=px(500), justify="left").pack(anchor="w", padx=12, pady=(6, 0 if detail else 6))
                if detail:
                    tk.Label(cadre, text=detail, bg=PANNEAU2, fg=DISCRET, font=("Segoe UI", 9), wraplength=px(500), justify="left").pack(anchor="w", padx=12, pady=(0, 6))
        recherche.trace_add("write", remplir)
        remplir()
        champ.focus_set()

    def page_historique():
        vider()
        titre("Historique", "Ce que Jarvis a retenu, puis les dernières demandes et ses réponses. Tout reste sur ce PC.")
        section("Ce que Jarvis a retenu")
        try:
            import jarvis_memoire
            invite = jarvis_memoire._invite()
        except Exception as erreur:
            jarvis_memoire, invite = None, False
            print("Réglages (mémoire) :", erreur)
        if invite:                                  # mode invité : la mémoire du foyer ne se montre pas
            tk.Label(page, text="Mode invité : la mémoire n'est pas affichée.", bg=PANNEAU, fg=DISCRET,
                     font=POLICE).pack(anchor="w", padx=22)
        elif jarvis_memoire is not None:
            cadre = ligne()
            saisie = tk.StringVar(racine)

            def ajouter(*_):
                texte = saisie.get().strip()
                if len(texte.split()) >= 2:
                    jarvis_memoire.retenir(texte)
                    page_historique()

            bouton(cadre, "Retenir", ajouter).pack(side="right", padx=12, pady=8)
            champ = tk.Entry(cadre, textvariable=saisie, bg=BORD, fg=TEXTE, insertbackground=TEXTE, relief="flat",
                             font=POLICE, highlightthickness=1, highlightbackground=SURVOL, highlightcolor=accent["c"])
            champ.pack(side="left", fill="x", expand=True, padx=12, pady=8, ipady=5)
            champ.bind("<Return>", ajouter)
            faits = jarvis_memoire.tous()
            if not faits:
                tk.Label(page, text="Rien pour l'instant. Dis « Jarvis, retiens que… », ou écris-le dans la case.",
                         bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22)

            def oublier(texte):
                jarvis_memoire.oublier_exact(texte)
                page_historique()

            for nom in [c[0] for c in jarvis_memoire.CATEGORIES] + ["Autre"]:
                du_rang = [f for f in faits if f["categorie"] == nom]
                if not du_rang:
                    continue
                tk.Label(page, text=f"{nom.upper()}  ({len(du_rang)})", bg=PANNEAU, fg=accent["c"],
                         font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=22, pady=(10, 2))
                for f in du_rang:
                    cadre = ligne()
                    bouton(cadre, "Oublier", lambda t=f["texte"]: oublier(t)).pack(side="right", padx=12, pady=6)
                    note = ("   (ancien : Jarvis ne le rappelle plus)" if f["perime"]
                            else "   (retenu par Jarvis de lui-même)" if f["source"] == "jarvis" else "")
                    _texte_souple(tk.Label(cadre, text=f["texte"] + note, wraplength=px(400), justify="left", anchor="w",
                                           bg=PANNEAU2, fg=DISCRET if f["perime"] else TEXTE, font=POLICE))
        section("Dernières demandes")
        echanges = historique()
        if not echanges:
            tk.Label(page, text="Rien pour l'instant.", bg=PANNEAU, fg=DISCRET, font=POLICE).pack(anchor="w", padx=22)
        for demande, reponse in echanges:
            cadre = ligne()
            tk.Label(cadre, text="Toi : " + demande, bg=PANNEAU2, fg=TEXTE, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=12, pady=(7, 0))
            tk.Label(cadre, text="Jarvis : " + reponse[:400], bg=PANNEAU2, fg=DISCRET, font=("Segoe UI", 9), wraplength=px(520), justify="left").pack(anchor="w", padx=12, pady=(1, 7))

    def page_sante():
        vider()
        titre("Santé", "Vérifie que tout ce dont Jarvis a besoin fonctionne. "
                       "Tu peux aussi dire « Jarvis, fais un diagnostic ».")
        section("Diagnostic")
        couleurs = {"ok": "#3ddc84", "attention": "#ffb340", "erreur": "#ff5c5c", "inconnu": DISCRET}
        zone = tk.Frame(page, bg=PANNEAU)
        zone.pack(fill="x")
        cadre = ligne()
        etat = tk.Label(cadre, text="", bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(330), justify="left")
        etat.pack(side="left", padx=12, pady=9)

        def lancer():
            import jarvis_sante
            for w in zone.winfo_children():
                w.destroy()
            etat.configure(text="Vérification en cours…")
            resultat = {}
            threading.Thread(target=lambda: resultat.update(liste=jarvis_sante.diagnostic()), daemon=True).start()

            def attendre():
                if "liste" not in resultat:
                    racine.after(250, attendre)
                    return
                try:
                    if not zone.winfo_exists():
                        return
                except tk.TclError:
                    return
                for nom, e, detail in resultat["liste"]:
                    l = carte(zone)
                    tk.Label(l, text="●", bg=PANNEAU2, fg=couleurs.get(e, DISCRET), font=("Segoe UI", 12)).pack(side="left", padx=(12, 4), pady=7)
                    tk.Label(l, text=nom, bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", pady=7)
                    tk.Label(l, text=detail, bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(260),
                             justify="right").pack(side="right", padx=12, pady=7)
                problemes = sum(1 for _, e, _ in resultat["liste"] if e in ("erreur", "attention"))
                etat.configure(text="Tout fonctionne." if not problemes else
                               f"{problemes} point{'s' if problemes > 1 else ''} à regarder.")
            attendre()
        bouton(cadre, "Relancer le diagnostic", lancer, fort=True).pack(side="right", padx=12, pady=5)
        lancer()

    def carte_mode_leger():
        """Mode léger (petits PC) : automatique, toujours ou jamais. Pris en compte au prochain démarrage."""
        import json as _json
        fichier = jarvis_config.chemin("mode_leger.json")
        try:
            with open(fichier, encoding="utf-8") as f:
                etat = _json.load(f)
            etat = etat if isinstance(etat, dict) else {}
        except (OSError, ValueError):
            etat = {}
        noms = {"auto": "Automatique", "toujours": "Toujours", "jamais": "Jamais"}
        cadre = ligne()
        gauche = tk.Frame(cadre, bg=PANNEAU2)
        gauche.pack(side="left", padx=12, pady=9)
        tk.Label(gauche, text="Mode léger (pour les PC peu puissants)", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(anchor="w")
        actif = etat.get("choix") == "toujours" or (etat.get("choix") != "jamais" and etat.get("actif"))
        detail = ("En ce moment : activé" + (f" depuis le {etat['depuis']}" if etat.get("depuis") else "") if actif
                  else "En ce moment : désactivé") + (". Les commandes simples (son, fenêtres, musique…) partent tout "
                                                       "de suite, sans attendre la reconnaissance précise.")
        note = tk.Label(gauche, text=detail, bg=PANNEAU2, fg=DISCRET, font=("Segoe UI", 9), wraplength=px(330),
                        justify="left")
        note.pack(anchor="w")

        def changer(nom):
            cle = next(k for k, v in noms.items() if v == nom)
            try:
                with open(fichier, encoding="utf-8") as f:
                    d = _json.load(f)
                d = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                d = {}
            d["choix"] = cle
            if cle == "jamais":
                d["actif"] = False
            try:
                with open(fichier, "w", encoding="utf-8") as f:
                    _json.dump(d, f, ensure_ascii=False)
                note.configure(text="Pris en compte au prochain démarrage de Jarvis (dis « Jarvis, redémarre »).")
            except OSError:
                note.configure(text="Je n'ai pas pu enregistrer ce choix.")
        choix(cadre, noms.get(etat.get("choix", "auto"), "Automatique"), list(noms.values()), changer).pack(
            side="right", padx=12, pady=4)

    def page_systeme():
        vider()
        titre("Système", "Démarrage, sauvegarde et remise à zéro des réglages.")
        section("Démarrage")
        cadre = ligne()
        tk.Label(cadre, text="Lancer Jarvis avec Windows", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        interrupteur(cadre, demarrage_actif(), demarrage_windows).pack(side="right", padx=12)
        section("Vitesse")
        try:
            carte_mode_leger()
        except Exception as erreur:
            print("Réglages (mode léger) :", erreur)
        section("Sauvegarde")
        cadre = ligne()
        tk.Label(cadre, text="Réglages, profils, mémoires, rappels, notes et listes", bg=PANNEAU2, fg=TEXTE, font=POLICE,
                 wraplength=px(300), justify="left").pack(side="left", padx=12, pady=9)

        def faire_sauvegarde():
            try:
                chemin = sauvegarder()
                messagebox.showinfo("Jarvis", "Sauvegarde faite :\n" + chemin, parent=racine)
            except Exception as erreur:
                messagebox.showerror("Jarvis", f"Sauvegarde impossible : {erreur}", parent=racine)

        def faire_restauration():
            chemin = filedialog.askopenfilename(parent=racine, title="Choisir une sauvegarde de Jarvis",
                                                initialdir=DOSSIER_SAUVEGARDES if os.path.isdir(DOSSIER_SAUVEGARDES) else None,
                                                filetypes=[("Sauvegarde de Jarvis", "*.zip")])
            if not chemin:
                return
            if not messagebox.askyesno("Jarvis", "Remettre cette sauvegarde ? Tes réglages, profils, mémoires, rappels et "
                                                 "notes actuels seront remplacés par ceux de la sauvegarde.\n\n"
                                                 "Jarvis redémarrera ensuite.", parent=racine):
                return
            try:
                sauvegarder()                       # par précaution : l'état actuel est gardé avant
                n = restaurer(chemin)
                messagebox.showinfo("Jarvis", f"{n} fichier(s) remis. Jarvis redémarre.", parent=racine)
                racine.destroy()
                jarvis_claude.redemarrer()
            except Exception as erreur:
                messagebox.showerror("Jarvis", f"Restauration impossible : {erreur}", parent=racine)
        boites = tk.Frame(cadre, bg=PANNEAU2)
        boites.pack(side="right", padx=8)
        bouton(boites, "Restaurer…", faire_restauration).pack(side="right", padx=4, pady=5)
        bouton(boites, "Sauvegarder", faire_sauvegarde, fort=True).pack(side="right", padx=4, pady=5)
        tk.Label(page, text="Les sauvegardes vont dans Documents, dossier « Jarvis - sauvegardes ».", bg=PANNEAU,
                 fg=DISCRET, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=4)
        section("Paramètres par défaut")
        cadre = ligne()
        tk.Label(cadre, text="Tout remettre comme à l'installation", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)

        def remettre():
            if messagebox.askyesno("Jarvis", "Remettre tous les réglages par défaut ?\n\nLes profils, les mémoires, les voix "
                                             "enregistrées, les rappels, les notes et les listes ne sont pas touchés.",
                                   parent=racine):
                par_defaut()
                accent["c"] = ACCENT
                page_systeme()
                messagebox.showinfo("Jarvis", "C'est fait : les réglages sont revenus par défaut.", parent=racine)
        bouton(cadre, "Par défaut…", remettre).pack(side="right", padx=12, pady=5)

    def page_a_propos():
        vider()
        titre("À propos")
        for texte in (f"Jarvis, version {jarvis_claude.VERSION}", "Assistant vocal pour Windows, par TonyNio.",
                      "Licence PolyForm Strict 1.0.0.", "github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio"):
            tk.Label(page, text=texte, bg=PANNEAU, fg=TEXTE if texte.startswith("Jarvis") else DISCRET,
                     font=POLICE_TITRE if texte.startswith("Jarvis") else POLICE).pack(anchor="w", padx=22, pady=3)
        section("Mises à jour")
        cadre = ligne()
        etat = tk.Label(cadre, text="Vérifie s'il existe une version plus récente sur GitHub.", bg=PANNEAU2, fg=TEXTE,
                        font=POLICE, wraplength=px(330), justify="left")
        etat.pack(side="left", padx=12, pady=9)
        boites = tk.Frame(cadre, bg=PANNEAU2)
        boites.pack(side="right", padx=8)
        resultat = {}

        def installer():
            import jarvis_maj
            version = resultat.get("version", "")
            if not messagebox.askyesno("Jarvis", f"Installer la version {version} maintenant ?\n\nJarvis va se fermer "
                                                 "quelques instants puis redémarrer. Tes réglages, ta mémoire, tes rappels, "
                                                 "tes listes et tes profils sont gardés.", parent=racine):
                return
            etat.configure(text="Téléchargement de la mise à jour…")

            def travail():
                try:
                    resultat["installation"] = jarvis_maj.installer()
                except Exception as erreur:
                    resultat["installation"] = f"Mise à jour impossible : {erreur}"
            threading.Thread(target=travail, daemon=True).start()

            def attendre():
                if "installation" in resultat:
                    etat.configure(text=resultat["installation"])
                else:
                    racine.after(300, attendre)
            attendre()

        def verifier():
            import jarvis_maj
            etat.configure(text="Je regarde sur GitHub…")
            for w in boites.winfo_children():
                w.destroy()
            resultat.clear()

            def travail():
                try:
                    trouve = jarvis_maj.verifier()
                    resultat["version"] = trouve[0] if trouve else None
                    resultat["titre"] = trouve[1] if trouve else ""
                except Exception:
                    resultat["erreur"] = True
                resultat["fini"] = True
            threading.Thread(target=travail, daemon=True).start()

            def attendre():
                if not resultat.get("fini"):
                    racine.after(250, attendre)
                    return
                if resultat.get("erreur"):
                    etat.configure(text="Je n'arrive pas à joindre GitHub pour le moment. Réessaie plus tard.")
                    bouton(boites, "Réessayer", verifier).pack(side="right", padx=4, pady=5)
                elif resultat.get("version"):
                    etat.configure(text=f"La version {resultat['version']} est disponible"
                                        + (f" : {resultat['titre']}." if resultat.get("titre") else "."))
                    bouton(boites, "Installer", installer, fort=True).pack(side="right", padx=4, pady=5)
                else:
                    etat.configure(text=f"Jarvis est à jour : version {jarvis_maj.version_actuelle()}.")
                    bouton(boites, "Vérifier", verifier).pack(side="right", padx=4, pady=5)
            attendre()
        bouton(boites, "Vérifier les mises à jour", verifier, fort=True).pack(side="right", padx=4, pady=5)
        section("Désinstallation")
        cadre = ligne()
        tk.Label(cadre, text="Retirer Jarvis de ce PC, avec tout ce qui a été installé pour lui. Rien n'est supprimé "
                             "avant une dernière confirmation.", bg=PANNEAU2, fg=TEXTE, font=POLICE,
                 wraplength=px(330), justify="left").pack(side="left", padx=12, pady=9)

        def desinstaller():
            try:
                import jarvis_desinstaller
                jarvis_desinstaller.ouvrir(racine)
            except Exception as erreur:
                messagebox.showerror("Jarvis", f"La fenêtre de désinstallation n'a pas pu s'ouvrir : {erreur}", parent=racine)
        bouton(cadre, "Désinstaller Jarvis…", desinstaller).pack(side="right", padx=12, pady=5)

    def page_rapports():
        import json as _json
        import tempfile
        import jarvis_rapports
        import jarvis_rapports_ui
        vider()
        titre("Rapports", "Aider à améliorer Jarvis : ce que Jarvis envoie à son créateur, et quand. "
                          "Rien ne part sans votre accord, sauf un compteur anonyme que vous pouvez couper.")
        section("Ce que j'accepte d'envoyer")
        # (l'élément de droite est placé AVANT le texte : il garde toujours sa place, et le texte passe à la ligne)
        cadre = ligne()
        noms = list(jarvis_rapports.NIVEAUX.values())
        cles = list(jarvis_rapports.NIVEAUX)
        choix(cadre, jarvis_rapports.NIVEAUX[jarvis_rapports.niveau()], noms,
              lambda n: jarvis_rapports.choisir_niveau(cles[noms.index(n)])).pack(side="right", padx=12, pady=4)
        _texte_souple(tk.Label(cadre, text="Rapport toutes les heures, s'il y a du nouveau (technique : sans les "
                                           "conversations ; complet : avec)",
                               wraplength=px(330), justify="left", anchor="w", bg=PANNEAU2, fg=TEXTE, font=POLICE))
        cadre = ligne()
        interrupteur(cadre, jarvis_rapports.valeur("compteur", True),
                     lambda v: jarvis_rapports.regler("compteur", bool(v))).pack(side="right", padx=12)
        _texte_souple(tk.Label(cadre, text="Compteur anonyme (combien de personnes utilisent Jarvis, et sur quel "
                                           "type de PC)",
                               wraplength=px(400), justify="left", anchor="w", bg=PANNEAU2, fg=TEXTE, font=POLICE))
        cadre = ligne()
        interrupteur(cadre, jarvis_rapports.valeur("testeur", False),
                     lambda v: jarvis_rapports.regler("testeur", bool(v))).pack(side="right", padx=12)
        _texte_souple(tk.Label(cadre, text="Je veux tester les nouvelles versions en avance", wraplength=px(400),
                               justify="left", anchor="w", bg=PANNEAU2, fg=TEXTE, font=POLICE))
        section("Écrire au créateur de Jarvis")
        cadre = ligne()
        bouton(cadre, "Signaler un problème", lambda: jarvis_rapports_ui.ouvrir_message("probleme"),
               fort=True).pack(side="left", padx=12, pady=8)
        bouton(cadre, "Proposer une amélioration", lambda: jarvis_rapports_ui.ouvrir_message("idee")).pack(
            side="left", pady=8)
        section("Mes données")

        def voir():
            rap, n = jarvis_rapports.construire_rapport()
            chemin = os.path.join(tempfile.gettempdir(), "Jarvis - prochain rapport.json")
            with open(chemin, "w", encoding="utf-8") as f:
                _json.dump(rap, f, ensure_ascii=False, indent=2)
            os.startfile(chemin)

        def effacer():
            if not messagebox.askyesno("Jarvis", "Effacer tout ce qui a été envoyé depuis ce PC, et le journal en "
                                                 "attente sur ce PC ?", parent=racine):
                return
            ok = jarvis_rapports.effacer_mes_donnees()
            messagebox.showinfo("Jarvis", "C'est fait : vos données sont effacées." if ok else
                                "Le journal de ce PC est vidé, mais le dépôt n'a pas répondu (Internet ?). "
                                "Réessayez plus tard.", parent=racine)
        cadre = ligne()
        bouton(cadre, "Voir ce qui partirait", voir).pack(side="left", padx=12, pady=8)
        bouton(cadre, "Effacer mes données", effacer).pack(side="left", pady=8)
        bouton(cadre, "Page d'information", jarvis_rapports_ui.ouvrir_page_info).pack(side="left", padx=12, pady=8)
        tk.Label(page, text=jarvis_rapports_ui.DETAIL, bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520),
                 justify="left").pack(anchor="w", padx=22, pady=12)

        # Les dernières demandes dites à voix haute sont gardées sur ce PC (jamais envoyées) pour régler l'écoute
        section("Mes enregistrements de voix")
        dossier_sons = jarvis_config.chemin("enregistrements")

        def nombre_sons():
            try:
                return sum(1 for f in os.listdir(dossier_sons) if f.endswith(".wav"))
            except OSError:
                return 0

        texte_sons = tk.StringVar(racine)

        def maj_sons():
            n = nombre_sons()
            texte_sons.set(f"Jarvis garde sur ce PC le son de vos dernières demandes ({n} en ce moment), avec ce qu'il "
                           "a compris. Ils servent seulement à améliorer son écoute, ne quittent jamais ce PC, et les plus "
                           "anciens s'effacent tout seuls.")

        def effacer_sons():
            if not messagebox.askyesno("Jarvis", "Effacer tous les enregistrements de vos demandes gardés sur ce PC ?",
                                       parent=racine):
                return
            import shutil
            shutil.rmtree(dossier_sons, ignore_errors=True)
            try:
                os.remove(jarvis_config.chemin("derniere_demande.wav"))
            except OSError:
                pass
            maj_sons()
            messagebox.showinfo("Jarvis", "C'est fait : les enregistrements sont effacés." if not nombre_sons() else
                                "Une partie n'a pas pu être effacée (un fichier est en cours d'écriture). Réessayez.",
                                parent=racine)
        maj_sons()
        cadre = ligne()
        bouton(cadre, "Effacer mes enregistrements", effacer_sons).pack(side="right", padx=12, pady=8)
        tk.Label(cadre, textvariable=texte_sons, wraplength=px(300), justify="left", bg=PANNEAU2, fg=TEXTE,
                 font=POLICE).pack(side="left", padx=12, pady=9)

    def page_comptes():
        vider()
        try:
            qui = jarvis_profils.prenom_actif() or ""
        except Exception:
            qui = ""
        titre("Comptes" + (f" de {qui}" if qui else ""),
              "Chaque profil a sa boîte mail et son agenda, et ne voit que les siens : ici, ceux du profil en cours. "
              "Les liens et les mots de "
              "passe restent sur ce PC, dans le coffre de Windows.")
        try:
            import jarvis_enfant
            reserve = jarvis_enfant.actif() or jarvis_extras.invite()
        except Exception:
            reserve = False
        if reserve:
            tk.Label(page, text="Ces réglages sont réservés aux parents : ils ne s'ouvrent pas en mode enfant ni en "
                                "mode invité.", bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520),
                     justify="left").pack(anchor="w", padx=22, pady=12)
            return

        def carte(texte, sous, libelle, action, fort):
            cadre = ligne()
            gauche = tk.Frame(cadre, bg=PANNEAU2)
            gauche.pack(side="left", padx=12, pady=9)
            tk.Label(gauche, text=texte, bg=PANNEAU2, fg=TEXTE, font=("Segoe UI Semibold", 10), wraplength=px(300),
                     justify="left").pack(anchor="w")
            if sous:
                tk.Label(gauche, text=sous, bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(300),
                         justify="left").pack(anchor="w")
            bouton(cadre, libelle, action, fort=fort).pack(side="right", padx=12, pady=8)

        section("Agenda")
        try:
            import jarvis_agenda_ui
            relie = jarvis_agenda_ui.relie()
            service = jarvis_agenda_ui.nom_service(jarvis_agenda_ui.service_relie())
            foyer = jarvis_agenda_ui.agenda_du_foyer()
            carte(("✓ Agenda " + service + " relié." if service else "✓ Un agenda est relié.") if relie
                  else "Tu lis l'agenda du foyer." if foyer else "Aucun agenda relié.",
                  "« Qu'est-ce que j'ai demain ? », rappel la veille au soir." if relie else
                  "Tu peux relier le tien : Google Agenda, Outlook, iCloud ou un autre." if foyer else
                  "Google Agenda, Outlook, iCloud ou un autre.",
                  "Changer ou retirer" if relie else "Relier mon agenda", jarvis_agenda_ui.ouvrir, not relie)
        except Exception as erreur:
            print("Réglages (agenda) :", erreur)
        section("Boîte mail")
        try:
            import jarvis_mails
            import jarvis_mails_ui
            adresse = jarvis_mails_ui.compte_relie()
            nom = jarvis_mails.reglages(adresse)["nom"] if adresse else ""
            carte(("✓ " + adresse) if adresse else "Aucune boîte mail reliée.",
                  (("Autre messagerie" if nom == "ta messagerie" else "Boîte mail " + nom)
                   + " reliée. « Est-ce que j'ai des nouveaux mails ? »") if adresse else
                  "Gmail, Orange, Free, La Poste, Yahoo, iCloud ou une autre.",
                  "Changer ou retirer" if adresse else "Relier ma boîte mail", jarvis_mails_ui.ouvrir, not adresse)
        except Exception as erreur:
            print("Réglages (mails) :", erreur)
        section("Navigateur")
        try:
            import jarvis_web
            nav = jarvis_web.navigateur_par_defaut()
            carte(nav["nom"], "C'est le navigateur choisi dans Windows. Jarvis l'utilise pour « ouvre le navigateur » "
                              "et « où j'en étais ? ».",
                  "Changer dans Windows", lambda: os.startfile("ms-settings:defaultapps"), False)
        except Exception as erreur:
            print("Réglages (navigateur) :", erreur)
        bas = tk.Frame(page, bg=PANNEAU)
        bas.pack(fill="x", padx=18, pady=(14, 4))
        bouton(bas, "Actualiser", page_comptes).pack(side="left")
        tk.Label(page, text="À la voix : « relie mon agenda », « relie mes mails ».", bg=PANNEAU, fg=DISCRET,
                 font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=8)

    claude_en_cours = {"v": False}

    def page_claude():
        """(Ancien onglet « Claude » : désormais en haut de l'onglet Assistants. Gardé pour les anciens appels.)"""
        ouvrir_assistants()

    def bloc_claude():
        """Claude, l'assistant principal : état, installation, connexion du compte. En haut de l'onglet Assistants."""
        import webbrowser
        import jarvis_claude_reglages as cr
        section("Claude, l'assistant principal")
        tk.Label(page, text="Avec un abonnement Claude, Jarvis répond à n'importe quelle question et agit sur ton PC. "
                            "Ici, tu peux l'installer et relier ton compte, sans refaire l'installation.",
                 bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22,
                                                                                               pady=(0, 4))
        carte_etat = ligne()
        corps = tk.Frame(carte_etat, bg=PANNEAU2)
        corps.pack(fill="x", padx=12, pady=9)
        t_titre = tk.Label(corps, text="Je regarde où en est Claude…", bg=PANNEAU2, fg=TEXTE,
                           font=("Segoe UI Semibold", 10), wraplength=px(480), justify="left")
        t_titre.pack(anchor="w")
        t_sous = tk.Label(corps, text="", bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(480), justify="left")
        t_sous.pack(anchor="w", pady=(2, 0))
        t_message = tk.Label(corps, text="", bg=PANNEAU2, fg=accent["c"], font=POLICE, wraplength=px(480), justify="left")
        t_message.pack(anchor="w", pady=(6, 0))
        boutons = tk.Frame(page, bg=PANNEAU)
        boutons.pack(fill="x", padx=18, pady=(6, 2))

        def vivante():
            try:
                return t_titre.winfo_exists()
            except Exception:
                return False

        def dans_fenetre(f):
            try:
                racine.after(0, lambda: vivante() and f())
            except Exception:
                pass

        def afficher(etat_claude, message=""):
            if not vivante():
                return
            titre_txt, sous_txt = cr.TEXTES[etat_claude]
            t_titre.configure(text=titre_txt)
            t_sous.configure(text=sous_txt)
            t_message.configure(text=message)
            for w in boutons.winfo_children():
                w.destroy()
            if claude_en_cours["v"]:
                return
            if etat_claude == "absent":
                bouton(boutons, "Installer Claude", installer_claude, fort=True).pack(side="left", padx=2)
                bouton(boutons, "Prendre un abonnement", lambda: webbrowser.open(cr.ADRESSE_ABONNEMENT)).pack(
                    side="left", padx=8)
            elif etat_claude == "deconnecte":
                bouton(boutons, "Connecter mon compte", connecter_claude, fort=True).pack(side="left", padx=2)
                bouton(boutons, "Prendre un abonnement", lambda: webbrowser.open(cr.ADRESSE_ABONNEMENT)).pack(
                    side="left", padx=8)
            else:
                bouton(boutons, "Changer de compte", changer_compte).pack(side="left", padx=2)
            bouton(boutons, "Actualiser", verifier).pack(side="left", padx=8)

        def verifier(message=""):
            t_titre.configure(text="Je regarde où en est Claude…")
            t_sous.configure(text="")

            def travail():
                e = cr.etat()
                dans_fenetre(lambda: afficher(e, message))
            threading.Thread(target=travail, daemon=True).start()

        def occupe(texte):
            claude_en_cours["v"] = True
            for w in boutons.winfo_children():
                w.destroy()
            t_message.configure(text=texte)

        def fini(ok, message, redemarrer=False):
            claude_en_cours["v"] = False
            if ok and redemarrer:
                def relancer():
                    if messagebox.askyesno("Jarvis", message + "\n\nJarvis doit redémarrer pour utiliser Claude. "
                                                      "Redémarrer maintenant ?", parent=racine):
                        racine.destroy()
                        jarvis_claude.redemarrer()
                    else:
                        verifier(message)
                dans_fenetre(relancer)
            else:
                dans_fenetre(lambda: verifier(message))

        def installer_claude():
            if not messagebox.askyesno("Jarvis", "Installer Claude Code (le programme officiel d'Anthropic, environ "
                                                 "370 Mo) ? Cela prend plusieurs minutes.\n\nIl faut un abonnement "
                                                 "Claude (Pro ou supérieur) pour l'utiliser.", parent=racine):
                return
            occupe("Installation de Claude en cours, plusieurs minutes… Tu peux continuer à utiliser Jarvis.")

            def travail():
                ok, message = cr.installer()
                if not ok:
                    return fini(False, message)
                dans_fenetre(lambda: t_message.configure(text="Claude est installé. Connexion de ton compte…"))
                ok2, message2 = cr.connecter()
                fini(ok2, message2 if ok2 else message + " " + message2, redemarrer=ok2)
            threading.Thread(target=travail, daemon=True).start()

        def connecter_claude():
            occupe("Ton navigateur s'ouvre sur la page de connexion de Claude : connecte-toi puis accepte "
                   "l'autorisation. J'attends (5 minutes au plus)…")

            def travail():
                ok, message = cr.connecter()
                fini(ok, message, redemarrer=ok)
            threading.Thread(target=travail, daemon=True).start()

        def changer_compte():
            if not messagebox.askyesno("Jarvis", "Délier le compte Claude de ce PC, puis en connecter un autre ?",
                                       parent=racine):
                return
            occupe("Changement de compte…")

            def travail():
                cr.deconnecter()
                ok, message = cr.connecter()
                fini(ok, message, redemarrer=ok)
            threading.Thread(target=travail, daemon=True).start()

        if claude_en_cours["v"]:
            afficher("absent" if not cr.installe() else "deconnecte", "Une opération est déjà en cours…")
            for w in boutons.winfo_children():
                w.destroy()
        else:
            verifier()
        tk.Label(page, text="À la voix : « premiers pas » rappelle ce que Claude apporte.", bg=PANNEAU, fg=DISCRET,
                 font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=8)

    assistants_etat = {"fournisseur": None, "message": "", "occupe": False, "avance": False, "cle_visible": False,
                       "cle": "", "nom": "", "adresse": "", "modele": ""}

    def ouvrir_assistants():
        """Clic sur « Assistants » dans le menu : on repart toujours de la première page (la liste des assistants),
        même si un formulaire était resté à moitié rempli. (Les boutons internes redessinent avec page_assistants.)"""
        if not assistants_etat["occupe"]:
            assistants_etat.update(fournisseur=None, message="", cle="", nom="", adresse="", modele="",
                                   avance=False, cle_visible=False)
        page_assistants()

    def page_assistants():
        """BÊTA - connecter d'autres assistants IA (secours quand Claude n'est pas là ou a atteint sa limite)."""
        import webbrowser
        import time as _t
        import jarvis_assistants as ja
        vider()
        titre("Assistants IA",
              "Claude est l'assistant principal de Jarvis. Tu ne l'as pas ? Pas de problème : branche un autre "
              "assistant (Gemini, Groq, Mistral…), il répondra à tes questions. Si tu as Claude, il reste le premier ; "
              "les autres prennent le relais quand il n'est pas disponible. Tout est expliqué pas à pas ci-dessous.")
        if assistants_etat["message"]:               # résultat de la dernière action, bien visible tout en haut
            tk.Label(page, text=assistants_etat["message"], bg=PANNEAU2, fg=accent["c"],
                     font=("Segoe UI Semibold", 10), wraplength=px(500), justify="left", padx=12, pady=8
                     ).pack(anchor="w", padx=22, pady=(4, 6))
        try:
            import jarvis_enfant
            if jarvis_enfant.actif() or jarvis_extras.invite():
                tk.Label(page, text="Ces réglages sont réservés aux parents : ils ne s'ouvrent pas en mode enfant ni "
                                    "en mode invité.", bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520),
                         justify="left").pack(anchor="w", padx=22, pady=12)
                return
        except Exception:
            pass
        try:                                         # Claude d'abord (ancien onglet « Claude », rangé ici)
            bloc_claude()
        except Exception as erreur:
            print("Réglages (Claude) :", erreur)

        def texte(parent, contenu, fort=False, couleur=None, haut=0):
            tk.Label(parent, text=contenu, bg=PANNEAU2, fg=couleur or (TEXTE if fort else DISCRET),
                     font=("Segoe UI Semibold", 10) if fort else POLICE, wraplength=px(480),
                     justify="left").pack(anchor="w", pady=(haut, 0))

        def maj():
            """Redessine la page, seulement si on est encore dessus."""
            try:
                if courant.get("nom") == "Assistants":
                    page_assistants()
            except Exception:
                pass

        def plus_tard(f):
            try:
                racine.after(0, f)
            except Exception:
                pass

        d = ja.charger()

        # --- l'avertissement bêta
        section("Les autres assistants (bêta)")
        cb = tk.Frame(ligne(), bg=PANNEAU2)
        cb.pack(fill="x", padx=12, pady=9)
        texte(cb, "VERSION DE TEST (BÊTA)", fort=True, couleur="#E8A33D")
        texte(cb, "Cette partie est nouvelle : il peut y avoir des problèmes. Si quelque chose ne marche pas, rien "
                  "n'est cassé : Claude continue de fonctionner comme avant, et tu peux retirer un assistant à tout "
                  "moment. Dis-le-moi si tu rencontres un souci.", haut=2)

        section("Comment ça marche")
        cc = tk.Frame(ligne(), bg=PANNEAU2)
        cc.pack(fill="x", padx=12, pady=9)
        texte(cc, "Claude reste l'assistant principal : Jarvis lui pose toujours la question en premier.")
        texte(cc, "Si Claude n'est pas installé, pas connecté, ou a atteint sa limite d'utilisation, Jarvis pose la "
                  "question au premier assistant de ta liste. S'il est lui aussi à court, il passe au suivant.",
              haut=4)
        texte(cc, "Ces assistants répondent par du texte. Ils ne peuvent pas agir sur ton PC (ouvrir, modifier, "
                  "chercher sur ton ordinateur) : cela reste réservé à Claude.", haut=4)
        texte(cc, "Ils ne se connectent pas avec ton mot de passe, mais avec une « clé » que tu crées toi-même sur "
                  "le site de l'assistant : c'est expliqué à l'étape 2.", haut=4)

        # --- étape 1 : l'accord
        section("Étape 1 : donner ton accord")
        c1 = tk.Frame(ligne(), bg=PANNEAU2)
        c1.pack(fill="x", padx=12, pady=9)
        if d.get("consentement"):
            texte(c1, "✓ Les autres assistants sont autorisés.", fort=True)
            texte(c1, "Seul le texte de ta question est envoyé au service que tu as choisi, sur Internet. Tu peux "
                      "tout arrêter quand tu veux.", haut=2)
            bouton(c1, "Tout arrêter", lambda: (ja.accepter_consentement(False), maj())).pack(anchor="w", pady=(8, 0))
        else:
            texte(c1, "Avant de commencer, une chose importante :", fort=True)
            texte(c1, "quand Jarvis se tourne vers un autre assistant, le texte de ta question est envoyé par "
                      "Internet à l'entreprise qui le fait fonctionner (Google, Mistral, etc.), qui la traite avec "
                      "ses propres règles de confidentialité. Rien d'autre de ton PC n'est envoyé : ni tes fichiers, "
                      "ni ta mémoire, ni tes mots de passe. Tant que tu n'as pas donné ton accord, rien ne part.",
                  haut=2)
            bouton(c1, "J'ai compris, j'autorise", lambda: (ja.accepter_consentement(True), maj()),
                   fort=True).pack(anchor="w", pady=(8, 0))

        # --- étape 2 : ajouter un assistant
        section("Étape 2 : ajouter un assistant")
        marqueur = tk.Frame(page, bg=PANNEAU, height=1)
        marqueur.pack(fill="x")
        if assistants_etat.pop("aller", False):      # après un ajout : retour en haut de la page Assistants
            def _aller_haut():
                try:
                    page.update_idletasks()
                    toile.yview_moveto(0)
                except Exception:
                    pass
            racine.after(60, _aller_haut)
            racine.after(300, _aller_haut)
        f_choisi = ja.PAR_ID.get(assistants_etat["fournisseur"])
        if not f_choisi:
            c2 = tk.Frame(ligne(), bg=PANNEAU2)
            c2.pack(fill="x", padx=12, pady=9)
            texte(c2, "A. Choisis l'assistant que tu veux ajouter.", fort=True)
            texte(c2, "Tu peux en ajouter plusieurs, et même plusieurs comptes du même assistant. Si tu n'en as "
                      "aucun, les plus simples pour commencer sont Gemini et Groq (gratuits, sans carte bancaire). "
                      "Les « gratuit » peuvent changer : vérifie sur leur site.", haut=2)
            payants = [f for f in ja.FOURNISSEURS if f.get("groupe") == "payant"]
            ouverts = assistants_etat.get("payants_ouverts", False)
            for f in ja.FOURNISSEURS:
                if f.get("groupe") == "gratuit" and f is ja.FOURNISSEURS[0]:
                    section("Gratuits")
                if f.get("groupe") == "payant" and f is payants[0]:
                    connectes = sum(1 for p in payants for c in d.get("comptes", []) if c.get("fournisseur") == p["id"])
                    section("Payants (crédit ou abonnement nécessaire)")
                    cp = tk.Frame(ligne(), bg=PANNEAU2)
                    cp.pack(fill="x", padx=12, pady=9)
                    texte(cp, f"{len(payants)} assistants qui demandent de payer pour marcher"
                              + (f", dont {connectes} déjà ajouté(s) chez toi" if connectes else "") + ".")
                    bouton(cp, "Masquer" if ouverts else "Voir les assistants payants",
                           lambda: (assistants_etat.update(payants_ouverts=not ouverts), maj())).pack(anchor="w", pady=(6, 0))
                if f.get("groupe") == "autre" and (not payants or f is ja.FOURNISSEURS[-1]):
                    section("Autre service")
                if f.get("groupe") == "payant" and not ouverts:
                    continue
                cadre = ligne()
                g = tk.Frame(cadre, bg=PANNEAU2)
                g.pack(side="left", padx=12, pady=8)
                tk.Label(g, text=f["nom"], bg=PANNEAU2, fg=TEXTE, font=("Segoe UI Semibold", 10),
                         wraplength=px(290), justify="left").pack(anchor="w")
                tk.Label(g, text=f["gratuit"], bg=PANNEAU2, fg=DISCRET, font=POLICE, wraplength=px(290),
                         justify="left").pack(anchor="w")
                deja = [c for c in d.get("comptes", []) if c.get("fournisseur") == f["id"]]
                if deja:
                    prets = sum(1 for c in deja if c.get("actif", True))
                    tk.Label(g, text=("✓ Connecté" if len(deja) == 1 else f"✓ Connecté ({len(deja)} comptes)")
                             + ("" if prets == len(deja) else " (à vérifier dans la liste)"),
                             bg=PANNEAU2, fg="#5FBF7F", font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(2, 0))

                def choisir(i=f["id"]):
                    assistants_etat.update(fournisseur=i, message="", cle="", nom="", adresse="", modele="",
                                           avance=(i == "autre"))
                    maj()
                bouton(cadre, "Ajouter un autre compte" if deja else "Choisir", choisir).pack(side="right", padx=12, pady=8)
        else:
            c2 = tk.Frame(ligne(), bg=PANNEAU2)
            c2.pack(fill="x", padx=12, pady=9)
            texte(c2, "Assistant choisi : " + f_choisi["nom"], fort=True)
            bouton(c2, "Changer d'assistant",
                   lambda: (assistants_etat.update(fournisseur=None, message=""), maj())).pack(anchor="w", pady=(6, 0))

            sans_cle = bool(f_choisi.get("sans_cle"))
            c3 = tk.Frame(ligne(), bg=PANNEAU2)
            c3.pack(fill="x", padx=12, pady=9)
            if sans_cle:
                texte(c3, "B. Prépare Ollama sur ce PC.", fort=True)
                texte(c3, f_choisi["aide"], haut=2)
                texte(c3, "Ollama n'a pas besoin de clé. Quand c'est prêt, passe à l'étape D.", haut=4)
            else:
                texte(c3, "B. Crée ta clé sur le site de l'assistant.", fort=True)
                texte(c3, "Une « clé API » est une longue suite de lettres et de chiffres, comme un mot de passe "
                          "spécial réservé aux programmes. Tu la crées toi-même, gratuitement, dans ton compte sur "
                          "le site de l'assistant. Ton vrai mot de passe ne sert qu'à te connecter là-bas : "
                          "Jarvis ne le demande jamais.", haut=2)
                texte(c3, f_choisi["aide"], haut=4)
                texte(c3, "Garde la clé secrète : ne la montre à personne. Le site ne te la montre souvent qu'une "
                          "seule fois, copie-la tout de suite.", haut=4)
            if f_choisi.get("cle_url"):
                bouton(c3, "Ouvrir le site de " + f_choisi["nom"].split(" (")[0],
                       lambda: webbrowser.open(f_choisi["cle_url"])).pack(anchor="w", pady=(8, 0))

            v_cle = tk.StringVar(value=assistants_etat["cle"])
            v_nom = tk.StringVar(value=assistants_etat["nom"])
            v_adr = tk.StringVar(value=assistants_etat["adresse"] or f_choisi["adresse"])
            v_mod = tk.StringVar(value=assistants_etat["modele"] or f_choisi["modele"])
            for var, cle_etat in ((v_cle, "cle"), (v_nom, "nom"), (v_adr, "adresse"), (v_mod, "modele")):
                var.trace_add("write", lambda *a, v=var, k=cle_etat: assistants_etat.__setitem__(k, v.get()))

            def champ(parent, var, secret=False):
                e = tk.Entry(parent, textvariable=var, bg=BORD, fg=TEXTE, insertbackground=TEXTE, relief="flat",
                             font=POLICE, width=44, show="•" if secret and not assistants_etat["cle_visible"] else "")
                e.pack(anchor="w", pady=(4, 0), ipady=4)
                return e

            if not sans_cle:
                c4 = tk.Frame(ligne(), bg=PANNEAU2)
                c4.pack(fill="x", padx=12, pady=9)
                texte(c4, "C. Colle ta clé ici.", fort=True)
                texte(c4, "Dans ton navigateur, copie la clé (Ctrl+C), puis clique sur « Coller » ci-dessous.", haut=2)
                e_cle = champ(c4, v_cle, secret=True)
                rang = tk.Frame(c4, bg=PANNEAU2)
                rang.pack(anchor="w", pady=(6, 0))

                def coller():
                    try:
                        v_cle.set(racine.clipboard_get().strip())
                    except Exception:
                        assistants_etat["message"] = "Je ne trouve rien à coller : copie d'abord la clé (Ctrl+C)."
                        maj()
                bouton(rang, "Coller", coller, fort=True).pack(side="left", padx=(0, 8))
                bouton(rang, "Masquer" if assistants_etat["cle_visible"] else "Afficher",
                       lambda: (assistants_etat.update(cle_visible=not assistants_etat["cle_visible"]), maj())
                       ).pack(side="left")

            c5 = tk.Frame(ligne(), bg=PANNEAU2)
            c5.pack(fill="x", padx=12, pady=9)
            texte(c5, "Réglages avancés (facultatif)", fort=True)
            texte(c5, "Tu peux ignorer cette partie : Jarvis choisit tout seul le bon modèle.", haut=2)
            if assistants_etat["avance"]:
                texte(c5, "Nom pour t'y retrouver (par exemple « compte perso ») :", haut=6)
                champ(c5, v_nom)
                texte(c5, "Adresse du service :", haut=6)
                champ(c5, v_adr)
                texte(c5, "Modèle (laisse vide pour un choix automatique) :", haut=6)
                champ(c5, v_mod)
                bouton(c5, "Masquer les réglages avancés",
                       lambda: (assistants_etat.update(avance=False), maj())).pack(anchor="w", pady=(8, 0))
            else:
                bouton(c5, "Afficher les réglages avancés",
                       lambda: (assistants_etat.update(avance=True), maj())).pack(anchor="w", pady=(6, 0))

            def ajouter():
                if assistants_etat["occupe"]:
                    return
                ok, msg, cid = ja.ajouter_compte(f_choisi["id"], v_cle.get(), v_mod.get(), v_adr.get(), v_nom.get())
                if not ok:
                    assistants_etat["message"] = msg
                    assistants_etat["aller"] = True
                    return maj()
                assistants_etat.update(occupe=True, message="Je teste ton assistant, quelques secondes…")

                def travail():
                    try:
                        ok2, m2, genre = ja.tester_detail(cid)
                        if ok2:
                            assistants_etat.update(fournisseur=None, cle="", nom="", adresse="", modele="")
                            m2 += " Il est dans ta liste, tout en bas. Tu peux en ajouter un autre juste ci-dessous."
                        elif genre in ("cle", "adresse", "modele", "autre"):
                            ja.supprimer_compte(cid)
                            m2 += " Je n'ai pas gardé ce compte : corrige puis réessaie."
                        else:
                            assistants_etat.update(fournisseur=None, cle="", nom="", adresse="", modele="")
                            m2 += " Je garde le compte : réessaie plus tard avec « Tester »."
                    except Exception as erreur:
                        m2 = f"Le test a échoué ({erreur})."
                    assistants_etat.update(occupe=False, message=m2, aller=True)
                    plus_tard(maj)
                threading.Thread(target=travail, daemon=True).start()
                assistants_etat["aller"] = True
                maj()

            c6 = tk.Frame(ligne(), bg=PANNEAU2)
            c6.pack(fill="x", padx=12, pady=9)
            texte(c6, "D. Ajoute et teste." if not sans_cle else "D. Ajoute et teste Ollama.", fort=True)
            texte(c6, "Jarvis enregistre ta clé (chiffrée par Windows, elle ne quitte pas ce PC) puis fait un petit "
                      "essai pour vérifier que tout fonctionne.", haut=2)
            if not d.get("consentement"):
                texte(c6, "N'oublie pas l'étape 1 : sans ton accord, l'assistant ne sera pas utilisé.", haut=4,
                      couleur="#E8A33D")
            bouton(c6, "Ajouter et tester", ajouter, fort=True).pack(anchor="w", pady=(8, 0))

        # (le message est affiché juste sous le titre de l'étape 2, voir plus haut)

        # --- la liste
        section("Mes assistants (dans l'ordre d'essai)")
        comptes = d.get("comptes", [])
        if not comptes:
            tk.Label(page, text="Aucun assistant ajouté pour l'instant.", bg=PANNEAU, fg=DISCRET, font=POLICE
                     ).pack(anchor="w", padx=22, pady=4)
        for rang_c, c in enumerate(comptes, 1):
            cc = tk.Frame(ligne(), bg=PANNEAU2)
            cc.pack(fill="x", padx=12, pady=9)
            texte(cc, f"{rang_c}. {ja.nom_affiche(c)}", fort=True)
            cle_claire = ja.dechiffrer_cle(c.get("cle", "")) if c.get("cle") else ""
            texte(cc, ("Clé " + ja.masquer(cle_claire) if cle_claire else "Sans clé") + " · modèle : "
                  + (c.get("modele") or "choisi automatiquement"), haut=2)
            if not c.get("actif", True):
                etat_txt, coul = "✖ Mis de côté" + (" : " + c["derniere_erreur"] if c.get("derniere_erreur") else ""), "#E06060"
            elif c.get("pause_jusqua", 0) > _t.time():
                etat_txt, coul = ("⏸ En pause (limite atteinte ou service en panne), reprise vers "
                                  + _t.strftime("%H:%M", _t.localtime(c["pause_jusqua"]))), "#E8A33D"
            else:
                etat_txt, coul = "✓ Prêt", "#5FBF7F"
            texte(cc, etat_txt, haut=2, couleur=coul)

            def tester_c(cid=c["id"]):
                if assistants_etat["occupe"]:
                    return
                assistants_etat.update(occupe=True, message="Je teste cet assistant, quelques secondes…")

                def travail():
                    try:
                        ok2, m2 = ja.tester(cid)
                    except Exception as erreur:
                        m2 = f"Le test a échoué ({erreur})."
                    assistants_etat.update(occupe=False, message=m2)
                    plus_tard(maj)
                threading.Thread(target=travail, daemon=True).start()
                maj()

            def basculer(cid=c["id"], actif_now=c.get("actif", True)):
                ja.modifier_compte(cid, actif=not actif_now, pause_jusqua=0)
                maj()

            def retirer(cid=c["id"], nom=ja.nom_affiche(c)):
                if messagebox.askyesno("Jarvis", f"Retirer {nom} de la liste ? La clé enregistrée sur ce PC sera "
                                                 "effacée. (Tu pourras la rajouter plus tard.)", parent=racine):
                    ja.supprimer_compte(cid)
                    maj()

            def deplacer(cid=c["id"], sens=0):
                ja.deplacer_compte(cid, sens)
                maj()
            r1 = tk.Frame(cc, bg=PANNEAU2)
            r1.pack(anchor="w", pady=(8, 0))
            bouton(r1, "Tester", tester_c).pack(side="left", padx=(0, 8))
            bouton(r1, "Remettre en service" if not c.get("actif", True) else "Mettre de côté", basculer
                   ).pack(side="left", padx=(0, 8))
            bouton(r1, "Retirer", retirer).pack(side="left")
            if len(comptes) > 1:
                r2 = tk.Frame(cc, bg=PANNEAU2)
                r2.pack(anchor="w", pady=(6, 0))
                if rang_c > 1:
                    bouton(r2, "Monter", lambda cid=c["id"]: deplacer(cid, -1)).pack(side="left", padx=(0, 8))
                if rang_c < len(comptes):
                    bouton(r2, "Descendre", lambda cid=c["id"]: deplacer(cid, 1)).pack(side="left")

        # --- l'aide
        section("En cas de problème")
        ch = tk.Frame(ligne(), bg=PANNEAU2)
        ch.pack(fill="x", padx=12, pady=9)
        texte(ch, "« La clé est refusée » : la clé est mal copiée, ou elle a expiré. Retire l'assistant, recrée "
                  "une clé sur le site et recommence. Copie-la en entier, sans espace.")
        texte(ch, "« Limite atteinte » : tu as utilisé tout ton quota (ou ton crédit) chez cet assistant. Jarvis le "
                  "met de côté une heure et passe au suivant.", haut=4)
        texte(ch, "« Impossible de joindre le service » : vérifie ta connexion Internet. Pour Ollama, vérifie qu'il "
                  "est bien ouvert sur ce PC.", haut=4)
        texte(ch, "Tes clés sont chiffrées par Windows et restent sur ce PC : elles ne sont jamais envoyées sur "
                  "GitHub, ni dans les rapports de Jarvis.", haut=4)
        texte(ch, "Les prix et les offres gratuites sont ceux des entreprises : ils peuvent changer. Regarde "
                  "toujours sur leur site avant de donner une carte bancaire.", haut=4)
        tk.Label(page, text="Cet onglet est en test : tes retours m'aident à l'améliorer.", bg=PANNEAU, fg=DISCRET,
                 font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=8)

    # Rangées par famille (un trait fin les sépare dans la liste) :
    #   réacteur et voix | personnes et services | confidentialité | entretien | informations
    pages = [("Apparence", page_apparence), ("Réacteur", page_reacteur), ("Son", page_son),
             ("Profils", page_profils), ("Comptes", page_comptes), ("Assistants", ouvrir_assistants),
             ("Alertes", page_alertes),
             ("Rapports", page_rapports), ("Historique", page_historique),
             ("Système", page_systeme), ("Santé", page_sante),
             ("Aide", page_aide), ("À propos", page_a_propos)]
    DEBUTS_FAMILLE = ("Profils", "Rapports", "Système", "Aide")
    onglets = {}

    # une icône Windows (police Segoe MDL2 Assets) devant chaque rubrique
    icones = {"Apparence": "", "Son": "", "Alertes": "", "Profils": "", "Aide": "",
              "Historique": "", "Santé": "", "Système": "", "À propos": "", "Rapports": "\ue939",
              "Comptes": "\ue715", "Claude": "\ue8bd", "Assistants": "\ue774"}

    icones["Réacteur"] = ""

    courant = {"nom": None, "f": None}

    def dessin_claude(c, fond):
        """Le logo de Claude : une étoile de rayons de longueurs inégales, en orange Anthropic."""
        c.delete("all")
        longueurs = (10.5, 6.5, 9, 7, 10.5, 6, 9.5, 7, 10, 6.5, 9, 7)

        def dessin(sf, k):
            pg = __import__("pygame")
            cx_ = cy_ = px(12) * k
            for i_, lg in enumerate(longueurs):
                ang = i_ * 2 * math.pi / len(longueurs) - math.pi / 2 + 0.12
                a_ = (cx_ + px(2.2) * k * math.cos(ang), cy_ + px(2.2) * k * math.sin(ang))
                b_ = (cx_ + px(lg) * k * math.cos(ang), cy_ + px(lg) * k * math.sin(ang))
                pg.draw.line(sf, (217, 119, 87), a_, b_, int(px(2.6) * k))
                pg.draw.circle(sf, (217, 119, 87), b_, int(px(1.3) * k))
        c.create_image(0, 0, anchor="nw", image=_image_aa(px(24), px(24), fond, dessin, ("claude", fond)))

    def style_ligne(n, actif, survole=False):
        ligne_menu, _, ic, lib = onglets[n]
        w, h = max(ligne_menu.winfo_width(), px(142)), px(40)
        fond = _hex(_melange(_rgb(PANNEAU2), _rgb(accent["c"]), 0.22)) if actif else (PANNEAU2 if survole else FOND)
        ligne_menu.delete("pilule")
        if actif or survole:
            contour_p = _hex(_melange(_rgb(fond), _rgb(accent["c"]), 0.45))

            def dessin(sf, k):
                pg = __import__("pygame")
                pg.draw.rect(sf, _rgb(fond), (px(2) * k, px(2) * k, (w - px(4)) * k, (h - px(4)) * k), border_radius=px(11) * k)
                if actif:
                    pg.draw.rect(sf, _rgb(contour_p), (px(2) * k, px(2) * k, (w - px(4)) * k, (h - px(4)) * k),
                                 width=max(1, k), border_radius=px(11) * k)
                    pg.draw.line(sf, _rgb(accent["c"]), (px(9) * k, px(12) * k), (px(9) * k, (h - px(12)) * k), px(3) * k)
                    pg.draw.circle(sf, _rgb(accent["c"]), (px(9) * k, px(12) * k), px(1.5) * k)
                    pg.draw.circle(sf, _rgb(accent["c"]), (px(9) * k, (h - px(12)) * k), px(1.5) * k)
            img = _image_aa(w, h, FOND, dessin, ("pilule", w, h, actif, fond, FOND, accent["c"]))
            ligne_menu.create_image(0, 0, anchor="nw", image=img, tags="pilule")
            ligne_menu.tag_lower("pilule")
        ic.configure(bg=fond)
        lib.configure(bg=fond, fg=TEXTE if actif else DISCRET)
        if n == "Claude":
            dessin_claude(ic, fond)
        else:
            ic.configure(fg=accent["c"] if actif else DISCRET)

    def voir_onglet(nom):
        """Si la colonne défile, l'onglet choisi est ramené dans la partie visible."""
        try:
            vue = menu_toile.winfo_height()
            total = menu.winfo_reqheight()
            if vue < px(50) or total <= vue:
                return
            ligne = onglets[nom][0]
            y1 = ligne.winfo_y()
            y2 = y1 + ligne.winfo_height()
            haut = menu_toile.canvasy(0)
            if y1 < haut:
                menu_toile.yview_moveto(max(0.0, (y1 - px(4)) / total))
            elif y2 > haut + vue:
                menu_toile.yview_moveto(min(1.0, (y2 - vue + px(4)) / total))
        except Exception:
            pass

    def montrer(nom, fonction):
        courant.update(nom=nom, f=fonction)
        for n in onglets:
            style_ligne(n, n == nom)
        # la page se construit hors de vue, se met à sa taille, puis revient d'un coup (rien ne se déforme à l'écran)
        toile.coords(fenetre_page, -30000, 0)
        try:
            fonction()
            racine.update()
            voir_onglet(nom)
        finally:
            toile.coords(fenetre_page, 0, 0)
    for nom, fonction in pages:
        if nom in DEBUTS_FAMILLE:
            tk.Frame(menu, bg=BORD, height=1).pack(fill="x", padx=px(14), pady=(px(4), px(3)))
        ligne_menu = tk.Canvas(menu, bg=FOND, width=px(142), height=px(40), highlightthickness=0, cursor="hand2")
        if nom == "Claude":
            ic = tk.Canvas(ligne_menu, width=px(24), height=px(24), bg=FOND, highlightthickness=0, cursor="hand2")
        else:
            ic = tk.Label(ligne_menu, text=icones.get(nom, ""), bg=FOND, fg=DISCRET, font=("Segoe MDL2 Assets", 12), width=2)
        lib = tk.Label(ligne_menu, text=nom, anchor="w", bg=FOND, fg=DISCRET, font=("Segoe UI", 11), width=11)
        ligne_menu.create_window(px(30), px(20), window=ic)
        ligne_menu.create_window(px(52), px(20), window=lib, anchor="w", width=px(80), height=px(24))
        for w in (ligne_menu, ic, lib):
            w.bind("<Button-1>", lambda e, n=nom, f=fonction: montrer(n, f))
            w.bind("<Enter>", lambda e, n=nom: courant["nom"] != n and style_ligne(n, False, True))
            w.bind("<Leave>", lambda e, n=nom: courant["nom"] != n and style_ligne(n, False, False))
        ligne_menu.pack(fill="x", pady=px(1))
        onglets[nom] = (ligne_menu, None, ic, lib)

    # --- Le thème du réacteur change : toute la fenêtre prend les nouvelles couleurs ---
    OPTIONS_COULEUR = ("bg", "fg", "highlightbackground", "highlightcolor", "activebackground", "activeforeground",
                       "troughcolor", "insertbackground")

    def recolorer(widget, table):
        for o in OPTIONS_COULEUR:
            try:
                v = str(widget.cget(o)).lower()
            except Exception:
                continue
            if v in table:
                try:
                    widget.configure(**{o: table[v]})
                except Exception:
                    pass
        for enfant in widget.winfo_children():
            recolorer(enfant, table)

    def suivre():
        """Vrai si les couleurs de la fenêtre viennent de changer."""
        nom = _nom_theme()
        if nom == theme_pose["nom"]:
            return False
        avant = _couleurs_ui()
        _poser_theme(nom)
        theme_pose["nom"] = nom
        apres = _couleurs_ui()
        table = {avant[k].lower(): apres[k] for k in NOMS_COULEURS if avant[k].lower() != apres[k].lower()}
        accent["c"] = ACCENT
        racine.configure(bg=FOND)
        recolorer(racine, table)
        if courant["nom"]:
            place = toile.yview()[0]
            montrer(courant["nom"], courant["f"])
            racine.update_idletasks()
            toile.yview_moveto(place)
        return True

    # --- Animation : ligne lumineuse de l'en-tête et aperçu du réacteur ---
    debut = time.time()
    tic = {"n": 0}

    def animer():
        _fenetre["pouls"] = time.time()
        if _fenetre["devant"]:
            _fenetre["devant"] = False
            racine.deiconify()
            racine.lift()
            racine.focus_force()
        tic["n"] += 1
        if racine.state() == "iconic":
            if tic["n"] % 2 == 0:
                suivre()
            racine.after(500, animer)
            return
        if tic["n"] % 12 == 0:                # deux fois par seconde : le thème a-t-il changé ?
            suivre()
        t = time.time() - debut
        palette = survol["p"] or _couleurs_theme()
        m = _module("reacteur")
        cycle = max(1.0, float(getattr(m, "CYCLE_VEILLE", 12) if m else 12))
        couleur = _degrade(palette, t / cycle)
        # en-tête : une ligne fine et un reflet qui la parcourt
        largeur = max(10, entete.winfo_width())
        entete.delete("anim")
        bas = px(70)
        entete.create_line(24, bas, largeur - 24, bas, fill=_hex(_melange(_rgb(FOND), couleur, 0.45)), tags="anim")
        a = _module("jarvis_affichage")
        vitesse = float(getattr(a, "VITESSE_REFLET", 174)) if a else 174.0
        longueur = float(getattr(a, "LONGUEUR_REFLET", 160)) if a else 160.0
        x = 24 + (t * vitesse) % (largeur - 48)
        entete.create_line(max(24, x - longueur), bas, x, bas, fill=_hex(_melange(couleur, (255, 255, 255), 0.4)), width=2, tags="anim")
        # aperçu du réacteur
        apercu.delete("all")
        cx, cy, r = px(115), px(140), px(78)
        apercu.create_text(px(115), px(18), text="APERÇU", fill=DISCRET, font=("Segoe UI Semibold", 9))
        for k in range(36):
            ang = k * math.pi / 18
            niveau = 0.5 + 0.5 * math.sin(t * 1.1 + k * 0.35)
            c = _hex(_melange(_rgb(FOND), _degrade(palette, t / cycle + k / 36 * len(palette)), 0.35 + 0.5 * niveau))
            apercu.create_line(cx + (r + px(14)) * math.cos(ang), cy + (r + px(14)) * math.sin(ang),
                               cx + (r + px(18 + 8 * niveau)) * math.cos(ang), cy + (r + px(18 + 8 * niveau)) * math.sin(ang), fill=c, width=2)
        # le disque sombre, puis des filaments qui ondulent comme sur le vrai réacteur
        apercu.create_oval(cx - r, cy - r, cx + r, cy + r, fill=_hex(_melange(_rgb(FOND), couleur, 0.12)), outline="")
        for i in range(6):
            base = r * (0.72 + 0.045 * i)
            pts = []
            for k in range(49):
                ang = k * math.pi / 24
                rr = base * (1 + 0.035 * math.sin(3 * ang + t * (0.8 + 0.15 * i) + i)
                             + 0.025 * math.sin(5 * ang - t * (0.6 + 0.1 * i) + 2 * i))
                pts += [cx + rr * math.cos(ang), cy + rr * math.sin(ang)]
            c_fil = _degrade(palette, t / cycle + i / 6 * len(palette))
            apercu.create_line(*pts, fill=_hex(_melange(_rgb(FOND), c_fil, 0.45 + 0.08 * i)), width=1)
        for i in range(3):
            rr = r * (0.3 + 0.1 * i) * (1 + 0.03 * math.sin(t * 2 + i))
            apercu.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=_hex(_melange(_rgb(FOND), couleur, 0.25 + 0.1 * i)), width=1)
        apercu.create_oval(cx - r, cy - r, cx + r, cy + r, outline=_hex(_melange(_rgb(FOND), couleur, 0.6)), width=2)
        nb = int(getattr(a, "NB_REFLETS", 2)) if a else 2
        tour = float(getattr(a, "TOUR_REFLET_REACTEUR", 7.0)) if a else 7.0
        if not a or getattr(a, "REFLET_REACTEUR", True):
            for j in range(max(1, nb)):
                depart = (t % tour) / tour * 360 + j * 360 / max(1, nb)
                apercu.create_arc(cx - r, cy - r, cx + r, cy + r, start=-depart, extent=45, style="arc",
                                  outline=_hex(_melange(couleur, (255, 255, 255), 0.55)), width=3)
        apercu.create_oval(cx - px(16), cy - px(16), cx + px(16), cy + px(16), fill=_hex(_melange(_rgb(FOND), couleur, 0.85)), outline="")
        nom_theme = (survol["nom"].title() + " (survol)") if survol["p"] else \
            " · ".join(n.title() for n, p in jarvis_extras.PALETTES.items() if [c.lower() for c in p] == [c.lower() for c in palette])
        apercu.create_text(px(115), px(260), text=nom_theme or "", fill=DISCRET, font=("Segoe UI", 9))
        racine.after(66, animer)

    depart = _fenetre.pop("page", None)                    # (pour ouvrir directement sur un onglet)
    if depart == "Claude":                                 # l'ancien onglet Claude est en haut de l'onglet Assistants
        depart = "Assistants"
    montrer(depart if depart in dict(pages) else "Apparence", dict(pages).get(depart, page_apparence))
    if _fenetre.get("fermer_apres"):                       # (essais automatiques)
        racine.after(int(_fenetre.pop("fermer_apres") * 1000), racine.destroy)
    animer()
    racine.protocol("WM_DELETE_WINDOW", racine.destroy)

    def adapter_largeur(e):
        if e.widget is not racine:
            return
        etroite = e.width < px(940)
        if etroite and apercu.winfo_ismapped():
            apercu.pack_forget()
        elif not etroite and not apercu.winfo_ismapped():
            apercu.pack(side="left", fill="y", padx=(12, 0))
    racine.bind("<Configure>", adapter_largeur, add="+")
    try:                                           # à l'ouverture : devant tout (le réacteur peut être « toujours devant »)
        racine.update_idletasks()
        racine.lift()
        racine.attributes("-topmost", True)
        racine.after(400, lambda: racine.attributes("-topmost", False))
        racine.focus_force()
    except Exception:
        pass
    racine.mainloop()


# ---------- À la voix ----------

_OUVRIR = re.compile(r"\b(?:ouvre|ouvrir|affiche|montre)(?:-moi)?\s+(?:tes |les |mes |la fenêtre des |la fenêtre de )?"
                     r"(?:r[ée]glages|param[eè]tres)(?:\s+de jarvis|\s+du r[ée]acteur)?\b")



_CLAUDE_REGLAGE = re.compile(r"\b(?:accède|accéde|accede|acceder|accéder|accèder|installe|installer|connecte|connecter|ajoute|ajouter|"
                             r"configure|configurer|active|activer|relie|relier|relies|branche|brancher)(?:-moi|-toi)?[\s,]+(?:(?:à |a |au |aux |le |la |mon |ton |l'|de )){0,2}"
                             r"(?:compte )?(?:de )?claude\b")


_CLAUDE_COMPTE = re.compile(r"\b(?:d[ée]conn?ecte|d[ée]conn?ecter|d[ée]branche|d[ée]brancher|d[ée]lie|d[ée]lier)(?:-toi|-moi)?\b"
                            r".{0,25}\bclaude\b|\bchange[rz]?\b.{0,12}\bcompte\b.{0,10}\bclaude\b|"
                            r"\b(?:un )?autre compte claude\b|"
                            # « Claude » mal entendu (cloth, clothes…) ou « déconnecte » coupé en deux (« des connectes toi de »)
                            r"\b(?:d[ée]s?[- ]?)?conn?ect\w*(?:[- ]toi)?\s+(?:de|du)\s+(?:mon |ton |le )?"
                            r"(?:compte(?![- ](?:mail|gmail|google|agenda|outlook|icloud|microsoft|orange|free|yahoo))|claude)\b")


_ASSISTANTS = re.compile(r"\b(?:ouvre|ouvrir|affiche|montre)(?:-moi)?\s+(?:les |tes |mes |l'onglet (?:des )?|la page (?:des )?)?assistants\b|"
                         r"\b(?:branche|brancher|ajoute|ajouter|relie|relier|installe|installer|connecte|connecter)(?:-moi)?\s+"
                         r"(?:un |une )?(?:autre )?(?:assistant|ia|intelligence artificielle)(?: gratuite?)?\s*$")


def commande(t):
    t = t.replace("’", "'")
    if _CLAUDE_COMPTE.search(t):
        # « déconnecte-toi de mon Claude », « change de compte Claude » : jamais fait à la voix, on montre le bouton
        _fenetre["page"] = "Assistants"
        ouvrir()
        return ("J'ouvre mes réglages, onglet Assistants : Claude est tout en haut. Clique sur Changer de compte "
                "pour te déconnecter ou relier un autre compte.")
    if _ASSISTANTS.search(t):
        _fenetre["page"] = "Assistants"
        ouvrir()
        return ("J'ouvre mes réglages, onglet Assistants. Les assistants gratuits sont en haut de la liste : "
                "Gemini et Groq se branchent sans carte bancaire.")
    if _CLAUDE_REGLAGE.search(t):
        # « installe Claude », « connecte Claude » : mes réglages s'ouvrent directement sur l'onglet Assistants (Claude en haut)
        _fenetre["page"] = "Assistants"
        ouvrir()
        return ("J'ouvre mes réglages, onglet Assistants : Claude est tout en haut. Clique sur Installer Claude, "
                "puis sur Connecter mon compte.")
    if not _OUVRIR.search(t):
        return None
    # « ouvre les paramètres » tout court peut viser Windows : seulement « réglages », ou « tes paramètres »
    if re.search(r"\bparam[eè]tres\b", t) and not re.search(r"\btes param|\bparam[eè]tres de jarvis|\bparam[eè]tres du r", t):
        return None
    ouvrir()
    return "J'ouvre mes réglages."
