"""
JARVIS - la fenêtre de réglages, aux couleurs de Jarvis.

Ouverture : clic droit sur le réacteur, puis « Réglages… », ou à la voix : « Jarvis, ouvre les réglages ».
Chaque réglage s'applique tout de suite, sans redémarrer (sauf la taille du réacteur, au prochain démarrage),
et il est gardé dans preferences.json (fichier qui reste sur ce PC).

Onglets : Apparence, Son, Alertes, Profils, Aide, Historique, Système (démarrage avec Windows, sauvegarde et
restauration, paramètres par défaut), À propos. Un petit réacteur en direct montre l'effet des réglages.

« Paramètres par défaut » remet tous les réglages comme à l'installation, après confirmation. Il ne touche
jamais aux profils, aux mémoires, aux voix enregistrées, aux rappels, aux notes ni aux listes.
"""

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

FOND, PANNEAU, PANNEAU2 = "#05090e", "#0b121b", "#111b27"
TEXTE, DISCRET = "#d7e3f4", "#7d8ca3"
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
    ("cycle", "Apparence", "Vitesse du défilement des couleurs (secondes)", "nombre", "reacteur", "CYCLE_VEILLE", (4, 30, 1, "s")),
    ("vitesse_reflet", "Apparence", "Vitesse des reflets de la fenêtre", "nombre", "jarvis_affichage", "VITESSE_REFLET", (40, 400, 2, "")),
    ("longueur_reflet", "Apparence", "Longueur des reflets", "nombre", "jarvis_affichage", "LONGUEUR_REFLET", (20, 320, 5, "")),
    ("nb_reflets", "Apparence", "Nombre de reflets", "nombre", "jarvis_affichage", "NB_REFLETS", (1, 4, 1, "")),
    ("tour_reacteur", "Apparence", "Tour du reflet autour du cercle (secondes)", "nombre", "jarvis_affichage", "TOUR_REFLET_REACTEUR", (2, 20, 0.5, "s")),
    ("reflet_reacteur", "Apparence", "Reflet autour du cercle du réacteur", "bool", "jarvis_affichage", "REFLET_REACTEUR", None),
    ("devant", "Apparence", "Réacteur toujours au premier plan (sinon il reste sur le Bureau)", "bool", "jarvis_affichage", "TOUJOURS_DEVANT", None),
    ("regard", "Apparence", "Le cœur suit la souris", "bool", "jarvis_affichage", "REGARD_SOURIS", None),
    ("force_regard", "Apparence", "Intensité du suivi de la souris", "nombre", "jarvis_affichage", "FORCE_REGARD", (0.05, 0.35, 0.005, "")),
    ("danse", "Apparence", "Le réacteur danse avec la musique", "bool", "jarvis_affichage", "DANSE_MUSIQUE", None),
    ("force_danse", "Apparence", "Intensité de la danse", "nombre", "jarvis_affichage", "FORCE_DANSE", (0.05, 0.5, 0.01, "")),
    ("doux_nuit", "Apparence", "Plus doux la nuit", "bool", "jarvis_affichage", "DOUX_LA_NUIT", None),
    ("douceur_nuit", "Apparence", "Luminosité la nuit", "nombre", "jarvis_affichage", "DOUCEUR_NUIT", (0.3, 1.0, 0.02, "")),
    ("discret", "Apparence", "Mode discret en veille", "bool", "jarvis_affichage", "MODE_DISCRET", None),
    ("delai_discret", "Apparence", "Se réduit après (secondes)", "nombre", "jarvis_affichage", "DELAI_DISCRET", (5, 300, 5, "s")),
    ("taille_discrete", "Apparence", "Taille en mode discret", "nombre", "jarvis_affichage", "TAILLE_DISCRETE", (0.25, 0.8, 0.01, "")),
    ("panneau_compact", "Apparence", "Jauges visibles en mode discret", "bool", "jarvis_affichage", "PANNEAU_COMPACT", None),
    ("icones", "Apparence", "Icônes des jauges", "bool", "jarvis_affichage", "ICONES_JAUGES", None),
    ("halo", "Apparence", "Halo lumineux", "bool", "jarvis_affichage", "HALO", None),
    ("fetes", "Apparence", "Animations de minuit et d'anniversaire", "bool", "jarvis_affichage", "FETES", None),
    ("taille", "Apparence", "Taille du réacteur (au prochain démarrage)", "nombre", "reacteur", "TAILLE", (180, 400, 10, "")),
    ("volume_bip", "Son", "Volume du bip de réveil", "nombre", "jarvis_voix", "VOLUME_BIP", (0.05, 1.0, 0.05, "")),
    ("volume_fin", "Son", "Son de fin d'écoute (part du bip)", "nombre", "jarvis_voix", "VOLUME_FIN_ECOUTE", (0.0, 1.5, 0.05, "")),
    ("deux_voix", "Son", "Histoires à deux voix", "bool", "jarvis_enfant", "DEUX_VOIX", None),
    ("variation", "Son", "Voix légèrement variée d'une phrase à l'autre", "bool", "jarvis_voix", "VARIATION_VOIX", None),
    ("francais", "Son", "Vidéos des enfants : en français seulement", "bool", "jarvis_enfant", "FRANCAIS_SEULEMENT", None),
    ("alertes", "Alertes", "Annoncer les alertes météo", "bool", "jarvis_vigilance", "ACTIVE", None),
    ("niveau_alertes", "Alertes", "À partir de la vigilance", "choix", "jarvis_vigilance", "NIVEAU_MIN", [("jaune", 2), ("orange", 3), ("rouge", 4)]),
]
JAUGES_POSSIBLES = (("CPU", "Processeur"), ("RAM", "Mémoire"), ("GPU", "Carte graphique"), ("NET", "Réseau"), ("TMP", "Température"))

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
        DEFAUTS.update(micro="normale", reveil="normale", nuit_auto="non")
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
    ("Bases", "« qu'est-ce que tu sais faire ? »", "Le résumé des commandes."),
    ("Bases", "« quand tu entends mes mots, c'est mets-moi »", "Jarvis retient la correction pour la suite. « oublie la correction mes mots »."),
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
    ("Musique et vidéo", "« pause », « suivant », « monte le son », « baisse le son de Chrome »", ""),
    ("Musique et vidéo", "« avance de 30 secondes », « recule de 10 secondes »", ""),
    ("Musique et vidéo", "« résume cette vidéo »", "Sur YouTube, avec la transcription de la vidéo."),
    ("Navigateur", "« cherche des recettes de crêpes sur YouTube »", "Aussi Google, Amazon, Wikipédia, Leboncoin..."),
    ("Navigateur", "« clique sur Connexion », « la deuxième vidéo »", "« fais défiler », « reviens en arrière »."),
    ("Navigateur", "« lis-moi cette page », « résume cette page »", ""),
    ("Navigateur", "« où j'en étais ? »", "Rouvre tes onglets de Chrome."),
    ("PC", "« ouvre Chrome », « ferme Chrome », « ferme tout »", "« ferme tout » demande confirmation."),
    ("PC", "« mets Chrome à gauche », « affiche le bureau »", ""),
    ("PC", "« fais une capture d'écran », « qu'est-ce qu'il y a à l'écran ? »", ""),
    ("PC", "« ouvre le dernier téléchargement »", ""),
    ("PC", "« cherche le fichier facture »", ""),
    ("PC", "« état du PC », « pourquoi ça rame ? »", ""),
    ("PC", "« éteins l'ordinateur », « mets l'ordinateur en veille »", "Toujours avec confirmation."),
    ("Textes", "« dicte : je serai là dans dix minutes »", "Tape le texte dans la fenêtre active."),
    ("Textes", "« lis ça », « lis ce que j'ai copié », « traduis le texte copié en anglais »", ""),
    ("Textes", "« note que… », « lis mes notes »", ""),
    ("Textes", "« ajoute du pain à la liste », « lis-moi la liste »", ""),
    ("Cuisine", "« donne-moi la recette des crêpes étape par étape »", "Puis « étape suivante », « répète l'étape »."),
    ("Mémoire", "« retiens que… », « qu'est-ce que tu as retenu ? », « oublie que… »", ""),
    ("Modes", "« active le mode nuit »", "Réponses écrites, sans voix ni bip (les rappels sonnent)."),
    ("Modes", "« active le mode cinéma », « active le mode invité »", ""),
    ("Modes", "« mets le réacteur en bleu »", "Thèmes : Vice City, Iron Man, Océan, Forêt, Aurore, Galaxie, bleu, vert, rouge, violet, orange."),
    ("Voix", "« prends une voix de femme », « parle plus vite »", ""),
    ("Mails", "« est-ce que j'ai des nouveaux mails ? », « lis-moi mes mails »", "Sur le profil principal."),
    ("Mails", "« envoie un mail à Marie pour lui dire que… », « envoie-moi un mail pour me rappeler de… »",
     "Lu et affiché, puis envoyé seulement après « oui ». Destinataire : un contact iCloud avec une adresse mail."),
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

def historique(nombre=60):
    """[(heure, demande, réponse)] : les dernières demandes, d'après le journal de Jarvis."""
    try:
        with open(jarvis_config.chemin("jarvis.log"), encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()[-4000:]
    except OSError:
        return []
    resultat, demande = [], None
    for ligne in lignes:
        ligne = ligne.rstrip("\n")
        if ligne.startswith("Demande :"):
            texte = ligne[len("Demande :"):].strip()
            m = re.match(r"«\s*(.*?)\s*»", texte)
            demande = m.group(1) if m else texte
        elif ligne.startswith("JARVIS :") and demande:
            reponse = ligne[len("JARVIS :"):].strip()
            if reponse in ("Je m'en occupe.", "C'est parti.", "Je regarde ça.", "Une petite seconde.", "Laisse-moi voir."):
                continue
            resultat.append((demande, reponse))
            demande = None
    return resultat[-nombre:][::-1]


# ---------- La fenêtre ----------

_fenetre = {"ouverte": False, "devant": False}


def ouvrir():
    """Ouvre la fenêtre de réglages (ou la ramène devant si elle est déjà ouverte)."""
    if _fenetre["ouverte"]:
        _fenetre["devant"] = True
        return
    _fenetre["ouverte"] = True
    threading.Thread(target=_fenetre_principale, daemon=True).start()


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


def _fenetre_principale():
    try:
        _construire()
    except Exception as erreur:
        print("Fenêtre de réglages :", erreur)
    finally:
        _fenetre["ouverte"] = False


def _construire():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    import jarvis_extras
    import jarvis_profils

    if not _charge:
        charger()
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

    accent = {"c": _couleurs_theme()[0]}
    survol = {"p": None, "nom": ""}       # thème survolé : l'aperçu le montre avant qu'on clique

    # --- En-tête : titre et ligne lumineuse animée ---
    entete = tk.Canvas(racine, height=px(74), bg=FOND, highlightthickness=0)
    entete.pack(fill="x")
    import jarvis_claude
    entete.create_text(px(28), px(28), text="J A R V I S", anchor="w", fill=TEXTE, font=("Segoe UI Light", 20))
    entete.create_text(px(30), px(54), text="Réglages · version " + jarvis_claude.VERSION, anchor="w", fill=DISCRET, font=POLICE)

    corps = tk.Frame(racine, bg=FOND)
    corps.pack(fill="both", expand=True, padx=16, pady=(4, 14))
    menu = tk.Frame(corps, bg=FOND, width=170)
    menu.pack(side="left", fill="y", padx=(0, 12))
    contenu_cadre = tk.Frame(corps, bg=PANNEAU, highlightthickness=1, highlightbackground="#1b2838")
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
            barre.create_rectangle(1, debut * h, px(5), fin * h, fill="#2a3a50", outline="")
    toile.configure(yscrollcommand=position_barre)
    barre.pack(side="right", fill="y", pady=4)
    toile.pack(side="left", fill="both", expand=True)
    page = tk.Frame(toile, bg=PANNEAU)
    fenetre_page = toile.create_window((0, 0), window=page, anchor="nw")
    page.bind("<Configure>", lambda e: toile.configure(scrollregion=toile.bbox("all")))
    toile.bind("<Configure>", lambda e: toile.itemconfigure(fenetre_page, width=e.width))
    racine.bind_all("<MouseWheel>", lambda e: toile.yview_scroll(int(-e.delta / 120), "units"))

    def vider():
        for w in page.winfo_children():
            w.destroy()
        toile.yview_moveto(0)

    def titre(texte, sous=""):
        tk.Label(page, text=texte, bg=PANNEAU, fg=TEXTE, font=("Segoe UI Semibold", 15)).pack(anchor="w", padx=22, pady=(18, 0))
        if sous:
            tk.Label(page, text=sous, bg=PANNEAU, fg=DISCRET, font=POLICE, wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=(2, 8))

    def section(texte):
        tk.Label(page, text=texte.upper(), bg=PANNEAU, fg=accent["c"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=22, pady=(16, 4))

    def ligne():
        # chaque réglage est une petite carte, avec un fin contour
        cadre = tk.Frame(page, bg=PANNEAU2, highlightthickness=1, highlightbackground="#1b2838")
        cadre.pack(fill="x", padx=18, pady=3)
        return cadre

    def bouton(parent, texte, action, fort=False):
        b = tk.Label(parent, text=texte, bg=accent["c"] if fort else "#1b2838", fg="#0b0f14" if fort else TEXTE,
                     font=("Segoe UI Semibold", 10), padx=14, pady=6, cursor="hand2")
        b.bind("<Button-1>", lambda e: action())
        b.bind("<Enter>", lambda e: b.configure(bg=_hex(_melange(_rgb(accent["c"]), (255, 255, 255), 0.25)) if fort else "#25364a"))
        b.bind("<Leave>", lambda e: b.configure(bg=accent["c"] if fort else "#1b2838"))
        return b

    def interrupteur(parent, actif, changer):
        etat = {"v": bool(actif)}
        c = tk.Canvas(parent, width=px(46), height=px(24), bg=PANNEAU2, highlightthickness=0, cursor="hand2")

        def dessiner():
            c.delete("all")
            fond = accent["c"] if etat["v"] else "#2a3647"
            c.create_oval(px(2), px(2), px(22), px(22), fill=fond, outline=fond)
            c.create_oval(px(24), px(2), px(44), px(22), fill=fond, outline=fond)
            c.create_rectangle(px(12), px(2), px(34), px(22), fill=fond, outline=fond)
            x = px(34) if etat["v"] else px(12)
            c.create_oval(x - px(8), px(4), x + px(8), px(20), fill="#f2f6fb", outline="")

        def basculer(_=None):
            etat["v"] = not etat["v"]
            dessiner()
            changer(etat["v"])
        c.bind("<Button-1>", basculer)
        dessiner()
        return c

    def curseur(parent, val, mini, maxi, pas, changer, unite=""):
        cadre = tk.Frame(parent, bg=PANNEAU2)
        affiche = tk.Label(cadre, width=7, bg=PANNEAU2, fg=TEXTE, font=POLICE, anchor="e")
        variable = tk.DoubleVar(value=val)

        def montrer(v):
            v = float(v)
            affiche.configure(text=(f"{v:.0f}" if pas >= 1 else f"{v:.2f}".rstrip("0").rstrip(".")) + (f" {unite}" if unite else ""))

        def bouge(v):
            montrer(v)
            changer(round(float(v) / pas) * pas if pas else float(v))
        echelle = tk.Scale(cadre, from_=mini, to=maxi, resolution=pas, orient="horizontal", showvalue=False, variable=variable,
                           command=bouge, length=px(220), bg=accent["c"], fg=TEXTE, troughcolor="#1f2c3d", highlightthickness=0,
                           bd=0, sliderrelief="flat", activebackground=_hex(_melange(_rgb(accent["c"]), (255, 255, 255), 0.3)),
                           sliderlength=px(14), width=px(10))
        echelle.pack(side="left")
        affiche.pack(side="left", padx=(6, 0))
        montrer(val)
        return cadre

    def choix(parent, actuel, options, changer):
        variable = tk.StringVar(value=actuel)
        o = tk.OptionMenu(parent, variable, *options, command=changer)
        o.configure(bg="#1b2838", fg=TEXTE, activebackground="#25364a", activeforeground=TEXTE, highlightthickness=0,
                    bd=0, relief="flat", font=POLICE, width=16, indicatoron=0, padx=10, pady=4)
        o["menu"].configure(bg="#1b2838", fg=TEXTE, activebackground=accent["c"], activeforeground="#0b0f14", bd=0, font=POLICE)
        return o

    def reglage(cle, libelle, genre, options, onglet_actuel):
        cadre = ligne()
        tk.Label(cadre, text=libelle, bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        val = valeur(cle)
        if genre == "bool":
            interrupteur(cadre, val, lambda v, c=cle: regler(c, bool(v))).pack(side="right", padx=12)
        elif genre == "nombre":
            mini, maxi, pas, unite = options
            curseur(cadre, val if val is not None else mini, mini, maxi, pas, lambda v, c=cle: regler(c, v), unite).pack(side="right", padx=12)
        elif genre == "choix":
            noms = [n for n, _ in options]
            actuel = next((n for n, v in options if v == val), noms[0])
            choix(cadre, actuel, noms, lambda n, c=cle, o=options: regler(c, dict(o)[n])).pack(side="right", padx=12, pady=4)

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
                accent["c"] = _couleurs_theme()[0]
                page_apparence()
            tuile.bind("<Button-1>", choisir)
            # au survol, l'aperçu à droite prend ce thème (sans rien changer tant qu'on ne clique pas)
            tuile.bind("<Enter>", lambda e, p=palette, n=nom: survol.update(p=list(p), nom=n))
            tuile.bind("<Leave>", lambda e: survol.update(p=None))
            tuile.grid(row=i // 4, column=i % 4, padx=4, pady=4)
        for groupe, cles in (("Couleurs", ("cycle",)),
                             ("Reflets lumineux", ("vitesse_reflet", "longueur_reflet", "nb_reflets", "reflet_reacteur", "tour_reacteur")),
                             ("Vie du réacteur", ("regard", "force_regard", "danse", "force_danse", "fetes", "halo")),
                             ("La nuit", ("doux_nuit", "douceur_nuit")),
                             ("Mode discret", ("discret", "delai_discret", "taille_discrete", "panneau_compact")),
                             ("Taille et place", ("taille", "devant"))):
            section(groupe)
            for c, onglet, libelle, genre, _, _, options in REGLAGES:
                if c in cles:
                    reglage(c, libelle, genre, options, "Apparence")
            if groupe == "La nuit":
                cadre = ligne()
                tk.Label(cadre, text="Mode nuit automatique", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
                choix(cadre, choix_actuel("nuit_auto"), list(NUIT_AUTO), lambda n: regler("nuit_auto", n)).pack(side="right", padx=12, pady=4)
        section("Jauges et position")
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
        cadre = ligne()
        tk.Label(cadre, text="Placer le réacteur", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, "choisir…", list(COINS), placer).pack(side="right", padx=12, pady=4)

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
        for c in ("deux_voix", "variation", "francais"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Son")
        section("Écoute")
        cadre = ligne()
        tk.Label(cadre, text="Pièce (sensibilité du micro)", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, choix_actuel("micro"), list(SENSIBILITE_MICRO), lambda n: regler("micro", n)).pack(side="right", padx=12, pady=4)
        cadre = ligne()
        tk.Label(cadre, text="Mot de réveil « Jarvis »", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        choix(cadre, choix_actuel("reveil"), list(SENSIBILITE_REVEIL), lambda n: regler("reveil", n)).pack(side="right", padx=12, pady=4)
        tk.Label(page, text="« prudente » : il se réveille moins souvent par erreur quand on parle de lui ; "
                            "« sensible » : il répond plus facilement.", bg=PANNEAU, fg=DISCRET, font=POLICE,
                 wraplength=px(520), justify="left").pack(anchor="w", padx=22, pady=6)

    def page_alertes():
        vider()
        titre("Alertes météo", "La Vigilance de Météo-France pour ton département, vérifiée toutes les 30 minutes.")
        for c in ("alertes", "niveau_alertes"):
            r = next(x for x in REGLAGES if x[0] == c)
            reglage(c, r[2], r[3], r[6], "Alertes")

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

    def page_aide():
        vider()
        titre("Aide", "Toutes les commandes, rangées par thème. Tape un mot pour chercher.")
        recherche = tk.StringVar()
        champ = tk.Entry(page, textvariable=recherche, bg="#1b2838", fg=TEXTE, insertbackground=TEXTE, relief="flat",
                         font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#25364a", highlightcolor=accent["c"])
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
                cadre = tk.Frame(liste, bg=PANNEAU2)
                cadre.pack(fill="x", padx=18, pady=2)
                tk.Label(cadre, text=commande, bg=PANNEAU2, fg=TEXTE, font=POLICE, wraplength=px(500), justify="left").pack(anchor="w", padx=12, pady=(6, 0 if detail else 6))
                if detail:
                    tk.Label(cadre, text=detail, bg=PANNEAU2, fg=DISCRET, font=("Segoe UI", 9), wraplength=px(500), justify="left").pack(anchor="w", padx=12, pady=(0, 6))
        recherche.trace_add("write", remplir)
        remplir()
        champ.focus_set()

    def page_historique():
        vider()
        titre("Historique", "Les dernières demandes et ce que Jarvis a répondu (journal gardé sur ce PC).")
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
                    l = tk.Frame(zone, bg=PANNEAU2)
                    l.pack(fill="x", padx=18, pady=3)
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

    def page_systeme():
        vider()
        titre("Système", "Démarrage, sauvegarde et remise à zéro des réglages.")
        section("Démarrage")
        cadre = ligne()
        tk.Label(cadre, text="Lancer Jarvis avec Windows", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        interrupteur(cadre, demarrage_actif(), demarrage_windows).pack(side="right", padx=12)
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
                accent["c"] = _couleurs_theme()[0]
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
        cadre = ligne()
        tk.Label(cadre, text="Rapport une fois par jour (technique : sans les conversations ; complet : avec)",
                 wraplength=px(330), justify="left", bg=PANNEAU2, fg=TEXTE, font=POLICE).pack(side="left", padx=12, pady=9)
        noms = list(jarvis_rapports.NIVEAUX.values())
        cles = list(jarvis_rapports.NIVEAUX)
        choix(cadre, jarvis_rapports.NIVEAUX[jarvis_rapports.niveau()], noms,
              lambda n: jarvis_rapports.choisir_niveau(cles[noms.index(n)])).pack(side="right", padx=12, pady=4)
        cadre = ligne()
        tk.Label(cadre, text="Compteur anonyme (combien de personnes utilisent Jarvis)", bg=PANNEAU2, fg=TEXTE,
                 font=POLICE).pack(side="left", padx=12, pady=9)
        interrupteur(cadre, jarvis_rapports.valeur("compteur", True),
                     lambda v: jarvis_rapports.regler("compteur", bool(v))).pack(side="right", padx=12)
        cadre = ligne()
        tk.Label(cadre, text="Je veux tester les nouvelles versions en avance", bg=PANNEAU2, fg=TEXTE,
                 font=POLICE).pack(side="left", padx=12, pady=9)
        interrupteur(cadre, jarvis_rapports.valeur("testeur", False),
                     lambda v: jarvis_rapports.regler("testeur", bool(v))).pack(side="right", padx=12)
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

    pages = [("Apparence", page_apparence), ("Son", page_son), ("Alertes", page_alertes), ("Profils", page_profils),
             ("Aide", page_aide), ("Historique", page_historique), ("Santé", page_sante), ("Système", page_systeme), ("Rapports", page_rapports),
             ("À propos", page_a_propos)]
    onglets = {}

    # une icône Windows (police Segoe MDL2 Assets) devant chaque rubrique
    icones = {"Apparence": "", "Son": "", "Alertes": "", "Profils": "", "Aide": "",
              "Historique": "", "Santé": "", "Système": "", "À propos": "", "Rapports": "\ue939"}

    def montrer(nom, fonction):
        for n, (ligne_menu, trait, ic, lib) in onglets.items():
            actif = n == nom
            fond = PANNEAU2 if actif else FOND
            for w in (ligne_menu, ic, lib):
                w.configure(bg=fond)
            trait.configure(bg=accent["c"] if actif else FOND)
            ic.configure(fg=accent["c"] if actif else DISCRET)
            lib.configure(fg=TEXTE if actif else DISCRET)
        fonction()
    for nom, fonction in pages:
        ligne_menu = tk.Frame(menu, bg=FOND, cursor="hand2")
        trait = tk.Frame(ligne_menu, bg=FOND, width=px(3))
        trait.pack(side="left", fill="y")
        ic = tk.Label(ligne_menu, text=icones.get(nom, ""), bg=FOND, fg=DISCRET, font=("Segoe MDL2 Assets", 12), width=2, pady=8)
        ic.pack(side="left", padx=(10, 4))
        lib = tk.Label(ligne_menu, text=nom, anchor="w", bg=FOND, fg=DISCRET, font=("Segoe UI", 11), width=11, pady=8)
        lib.pack(side="left", fill="x", expand=True)
        for w in (ligne_menu, ic, lib):
            w.bind("<Button-1>", lambda e, n=nom, f=fonction: montrer(n, f))
        ligne_menu.pack(fill="x", pady=1)
        onglets[nom] = (ligne_menu, trait, ic, lib)

    # --- Animation : ligne lumineuse de l'en-tête et aperçu du réacteur ---
    debut = time.time()

    def animer():
        if _fenetre["devant"]:
            _fenetre["devant"] = False
            racine.deiconify()
            racine.lift()
            racine.focus_force()
        t = time.time() - debut
        palette = survol["p"] or _couleurs_theme()
        m = _module("reacteur")
        cycle = max(1.0, float(getattr(m, "CYCLE_VEILLE", 12) if m else 12))
        couleur = _degrade(palette, t / cycle)
        # en-tête : une ligne fine et un reflet qui la parcourt
        largeur = max(10, entete.winfo_width())
        entete.delete("anim")
        bas = px(70)
        entete.create_line(24, bas, largeur - 24, bas, fill=_hex(_melange((5, 9, 14), couleur, 0.45)), tags="anim")
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
            c = _hex(_melange((5, 9, 14), _degrade(palette, t / cycle + k / 36 * len(palette)), 0.35 + 0.5 * niveau))
            apercu.create_line(cx + (r + px(14)) * math.cos(ang), cy + (r + px(14)) * math.sin(ang),
                               cx + (r + px(18 + 8 * niveau)) * math.cos(ang), cy + (r + px(18 + 8 * niveau)) * math.sin(ang), fill=c, width=2)
        # le disque sombre, puis des filaments qui ondulent comme sur le vrai réacteur
        apercu.create_oval(cx - r, cy - r, cx + r, cy + r, fill=_hex(_melange((5, 9, 14), couleur, 0.12)), outline="")
        for i in range(6):
            base = r * (0.72 + 0.045 * i)
            pts = []
            for k in range(73):
                ang = k * math.pi / 36
                rr = base * (1 + 0.035 * math.sin(3 * ang + t * (0.8 + 0.15 * i) + i)
                             + 0.025 * math.sin(5 * ang - t * (0.6 + 0.1 * i) + 2 * i))
                pts += [cx + rr * math.cos(ang), cy + rr * math.sin(ang)]
            c_fil = _degrade(palette, t / cycle + i / 6 * len(palette))
            apercu.create_line(*pts, fill=_hex(_melange((5, 9, 14), c_fil, 0.45 + 0.08 * i)), width=1, smooth=True)
        for i in range(3):
            rr = r * (0.3 + 0.1 * i) * (1 + 0.03 * math.sin(t * 2 + i))
            apercu.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=_hex(_melange((5, 9, 14), couleur, 0.25 + 0.1 * i)), width=1)
        apercu.create_oval(cx - r, cy - r, cx + r, cy + r, outline=_hex(_melange((5, 9, 14), couleur, 0.6)), width=2)
        nb = int(getattr(a, "NB_REFLETS", 2)) if a else 2
        tour = float(getattr(a, "TOUR_REFLET_REACTEUR", 7.0)) if a else 7.0
        if not a or getattr(a, "REFLET_REACTEUR", True):
            for j in range(max(1, nb)):
                depart = (t % tour) / tour * 360 + j * 360 / max(1, nb)
                apercu.create_arc(cx - r, cy - r, cx + r, cy + r, start=-depart, extent=45, style="arc",
                                  outline=_hex(_melange(couleur, (255, 255, 255), 0.55)), width=3)
        apercu.create_oval(cx - px(16), cy - px(16), cx + px(16), cy + px(16), fill=_hex(_melange((5, 9, 14), couleur, 0.85)), outline="")
        nom_theme = (survol["nom"].title() + " (survol)") if survol["p"] else \
            " · ".join(n.title() for n, p in jarvis_extras.PALETTES.items() if [c.lower() for c in p] == [c.lower() for c in palette])
        apercu.create_text(px(115), px(260), text=nom_theme or "", fill=DISCRET, font=("Segoe UI", 9))
        racine.after(40, animer)

    montrer("Apparence", page_apparence)
    animer()
    racine.protocol("WM_DELETE_WINDOW", racine.destroy)
    racine.mainloop()


# ---------- À la voix ----------

_OUVRIR = re.compile(r"\b(?:ouvre|ouvrir|affiche|montre)(?:-moi)?\s+(?:tes |les |mes |la fenêtre des |la fenêtre de )?"
                     r"(?:r[ée]glages|param[eè]tres)(?:\s+de jarvis|\s+du r[ée]acteur)?\b")


def commande(t):
    t = t.replace("’", "'")
    if not _OUVRIR.search(t):
        return None
    # « ouvre les paramètres » tout court peut viser Windows : seulement « réglages », ou « tes paramètres »
    if re.search(r"\bparam[eè]tres\b", t) and not re.search(r"\btes param|\bparam[eè]tres de jarvis|\bparam[eè]tres du r", t):
        return None
    ouvrir()
    return "J'ouvre mes réglages."
