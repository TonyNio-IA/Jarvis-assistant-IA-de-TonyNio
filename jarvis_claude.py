"""
JARVIS - assistant vocal en français, relié à Claude.

Fonctionnement :
  1. Jarvis écoute en permanence (Vosk, hors ligne) pour repérer son nom.
  2. Quand une phrase COMMENCE par « Jarvis » :
     - si la demande suit directement (« Jarvis quelle heure est-il »), il la prend ;
     - sinon il fait un petit bip et attend ta demande.
     Ta demande est ensuite retranscrite avec Whisper, plus précis
     (noms propres, lieux...), toujours sur ton PC.
  3. Il envoie la demande à Claude Code (ton abonnement Claude Pro),
     puis lit la réponse à voix haute.
  4. Pendant 3 secondes, tu peux enchaîner une autre demande sans redire « Jarvis ».
  5. Il se souvient de la conversation pendant 10 minutes.
     « Jarvis, nouvelle conversation » pour repartir de zéro.
  6. « Jarvis, fais-moi le point du jour » : météo, actualités et tes sujets (réglés dans config.json).
     Il le prépare en arrière-plan et le lit dès qu'il est prêt.
     « Jarvis, annule le point du jour » (ou « arrête le point du jour ») pour l'annuler.
  8. « Stop » ou « Jarvis, stop » pendant qu'il parle : il se tait.
  9. Heure, date, météo, volume, musique, minuteurs et ouverture d'applications :
     réponse immédiate, sans Claude (voir jarvis_commandes.py).
 10. « Jarvis, répète » : il redit sa dernière réponse.
 11. « Jarvis, état du PC » : processeur, mémoire, programme le plus gourmand, disque.
 12. « Jarvis, note que... » et « Jarvis, lis mes notes ».
 13. Rappels à heure fixe, fermer une application, capture d'écran, recherche de fichier,
     extinction / redémarrage / veille après confirmation (voir jarvis_commandes.py).
  7. Il se met en pause tout seul quand Claude lit un message à voix haute (touche F9).

Lancement :  python C:\\Jarvis\\jarvis_reacteur.py   (avec le réacteur)
"""

import collections
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import wave

# Whisper (huggingface_hub) écrit sinon des avertissements en anglais au premier lancement : ils sont sans conséquence
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

import jarvis_systeme
import jarvis_voix
from jarvis_voix import speak, bip, preparer  # voix naturelle Henri (voix Windows en secours)
import jarvis_config
import jarvis_commandes
import jarvis_ecran
import jarvis_fenetres
import jarvis_memoire
import jarvis_maj
import jarvis_enfant
import jarvis_sources
from jarvis_commandes import commande_instantanee, sans_whisper  # heure, météo, volume...

VERSION = "1.22"              # numéro de version de Jarvis (même numéro que sur GitHub)

# ===== Réglages =====
MODEL_PATH = jarvis_config.chemin("vosk-model-small-fr-0.22")
SAMPLE_RATE = 16000
# Économie : dans le silence, la reconnaissance vocale se repose (elle consomme autant sur du
# silence que sur de la parole). Elle repart au premier son, avec les 0,8 s qui le précèdent.
ECONOMIE_SILENCE = True
MICRO_MUET = 10               # secondes sans aucun son du micro avant de relancer Jarvis (micro débranché)
REPOS_APRES = 3.0             # secondes de silence avant le repos
SEUIL_SON_MIN = 0.008         # un son plus fort que ce niveau (0 à 1) relance l'écoute...
                              # (mesuré : la voix dépasse toujours 0,024 ; à 0,003, les petits bruits de la
                              # pièce gardaient la reconnaissance active 82 % du temps, contre 16 % à 0,008)
SEUIL_SON_MAX = 0.012         # ... et même dans une pièce bruyante, ce niveau la relance toujours
BLOC_AUDIO = 1600             # 0,1 s de son à la fois (avant : 0,25 s) : Jarvis réagit plus vite
DOSSIER_JARVIS = jarvis_config.DOSSIER
CLAUDE_EXE = os.path.expanduser(r"~\.local\bin\claude.exe")
DELAI_ECOUTE_DEMANDE = 8      # secondes pour commencer à parler après « Jarvis »
SILENCE_FIN = 1.0             # secondes de silence qui marquent la fin de ta demande
DELAI_SUITE = 3               # secondes pour enchaîner une autre demande sans redire « Jarvis »
MOTS_MINIMUM = 2              # une demande plus courte est considérée comme mal entendue
DELAI_MAX_CLAUDE = 300        # secondes maximum pour une réponse de Claude
DELAI_MAX_POINT_DU_JOUR = 900 # le point du jour demande beaucoup de recherches
MODE_PERMISSIONS = "auto"     # Claude Code vérifie chaque action et bloque les risquées
MODELE = "sonnet"             # modèle pour les demandes courantes : "sonnet" (rapide) ou "opus" (plus puissant)
MODELE_POINT_DU_JOUR = "sonnet"   # "opus" = plus puissant, mais consomme nettement plus de quota

# Économie de quota : Claude Code démarre sans les extensions inutiles à Jarvis et avec
# seulement les outils dont il a besoin (environ 4 fois moins de texte envoyé à chaque question).
OPTIONS_LEGERES = ["--strict-mcp-config", "--disable-slash-commands"]
OUTILS = "PowerShell,WebSearch,WebFetch,Read"        # agir sur le PC, chercher sur le web, lire un fichier
OUTILS_POINT_DU_JOUR = "WebSearch,WebFetch"
POLITESSES = ("merci", "merci jarvis", "merci beaucoup", "non merci", "c est bon merci", "c est bon")
DELAI_AVANT_PATIENCE = 1.5    # si Claude n'a pas répondu après ce délai, Jarvis dit « Je m'en occupe »
AUDIO_DIAGNOSTIC = jarvis_config.chemin("derniere_demande.wav")   # dernière demande enregistrée (pour diagnostic)
# Compliments et remerciements : Jarvis répond lui-même, sans passer par Claude.
MOTS_POLITESSE = set("non oui ok d accord c est bon bien merci beaucoup jarvis tu as fait ton travail du "
                     "félicitations bravo parfait super nickel génial top joué boulot très tout ça "
                     "pour l instant rien autre de plus bonne excellent impeccable".split())
CLES_POLITESSE = re.compile(r"\b(merci|félicitations|bravo|parfait|super|nickel|génial|impeccable|"
                            r"c est bon|bien joué|bon travail|bon boulot|bien fait ton travail)\b")
MEMOIRE_MINUTES = 10          # Jarvis se souvient de la conversation pendant 10 min sans demande

# Reconnaissance précise de la demande (Whisper, sur le PC)
WHISPER_MODELE = "base"
WHISPER_FAISCEAU = 5          # nombre d'hypothèses comparées : 5 comprend mieux que 1, pour 0,5 s de plus
                              # (mesuré sur des enregistrements réels ; le modèle « small » n'apporte rien et est 3 fois plus lent)
WHISPER_DOSSIER = jarvis_config.chemin("whisper")
# Tous les cœurs du processeur (8 au plus) : mesuré 0,4 s plus rapide par demande qu'avec 4, même texte compris
WHISPER_FILS = max(1, min(8, os.cpu_count() or 4))
# Whisper lit cette phrase avant d'écouter : elle lui donne le genre de demandes attendues et les
# noms propres. Mesuré sur des enregistrements réels : avec elle et un court silence ajouté
# devant le son, « mets » n'est plus entendu « mais ».
# Les commandes les plus mal entendues y sont aussi (mesuré le 17/11/2026 sur 40 enregistrements réels :
# « des actives modnues » -> « désactive le mode nuit », « par là, à vitesse normale » -> « parle à vitesse
# normale », « la voie d'un riz » -> « la voix d'Henri » ; questions et dictées inchangées, +0,15 s par demande).
VOCABULAIRE = ("Demandes à l'assistant vocal Jarvis : mets de la musique, mets une chanson sur YouTube, "
               "ouvre une application, monte le son, rappelle-moi demain, fais une recherche. "
               "Active le mode nuit, désactive le mode nuit, parle plus vite, parle à vitesse normale, "
               "prends une voix de femme, reprends la voix d'Henri, active le Bluetooth, ajoute à la liste, "
               "lis-moi la liste, fais défiler, remonte, reviens en arrière, avance de 30 secondes, résume la page, "
               "active le mode enfant, raconte-moi une histoire. "
               "Jarvis, " + (jarvis_config.PRENOM + ", " if jarvis_config.PRENOM else "")
               + jarvis_commandes.VILLE_DEFAUT[0] + ", "
               + (jarvis_commandes.LIEUX_CONNUS + ", " if jarvis_commandes.LIEUX_CONNUS else "")
               + "".join(mot + ", " for mot in jarvis_config.VOCABULAIRE) + "Chrome, Claude"
               + "".join(", " + nom for nom in jarvis_commandes.noms_applications(10)
                         if nom not in ("Chrome", "Claude")) + ".")
WHISPER_SILENCE = 0.5         # secondes de silence ajoutées devant le son (le premier mot est mieux compris)

# Pause automatique quand ces programmes jouent du son (lecture à voix haute F9)
PROGRAMMES_A_IGNORER = ("claude.exe",)
MAINTIEN_PAUSE = 2.5          # secondes de pause gardées après le dernier son de Claude
                              # (les silences entre deux phrases lues ne relancent plus l'écoute)

# Réveil : « Jarvis » en début de phrase, ou après une courte pause au milieu d'une phrase
PAUSE_AVANT_JARVIS = 0.3      # secondes de silence avant « Jarvis » pour qu'il compte en milieu de phrase
MOTS_AVANT_JARVIS = 5         # après une phrase plus longue que ça, « Jarvis » est sans doute un mot de la phrase
PAUSE_LONGUE_AVANT_JARVIS = 0.8   # ... et il faut alors une vraie pause pour qu'il réveille Jarvis
# Quand Vosk entend l'un de ces débuts, c'est parfois « Jarvis » mal compris : Whisper vérifie
PRESQUE_JARVIS = ("j'ai envie", "j'envie", "envie", "je vis", "genre vie", "j'en vie", "gervais", "jervis", "j'arrive", "jarre", "djar")

# Les dernières demandes sont gardées (son + textes compris) pour pouvoir analyser les erreurs d'écoute
DOSSIER_ENREGISTREMENTS = jarvis_config.chemin("enregistrements")
NB_ENREGISTREMENTS = 300      # les 300 dernières demandes (environ 50 Mo) : de quoi régler l'écoute
LIGNES_INDEX = 5000           # lignes gardées dans index.txt (ce qui a été compris, en texte : environ 500 Ko)

# La ville se règle dans ville.txt (voir jarvis_commandes.py)
VILLE_METEO = ", ".join(p for p in (jarvis_commandes.VILLE_DEFAUT[0], jarvis_commandes.VILLE_PRECISION) if p)

# Point du jour automatique : au premier démarrage de Jarvis entre ces heures, une fois par jour
POINT_DU_JOUR_AUTO = False              # True = le préparer tout seul au premier démarrage du matin
POINT_DU_JOUR_HEURES = (5, 12)          # de 5 h à midi
POINT_DU_JOUR_ATTENTE = 20              # secondes d'attente au démarrage (laisser Internet se connecter)
FICHIER_POINT_DU_JOUR = jarvis_config.chemin("point_du_jour.date")

# Mots qui interrompent Jarvis pendant qu'il parle
MOTS_STOP = ["jarvis stop", "stop", "jarvis arrête", "arrête", "tais-toi", "jarvis tais-toi"]
# « Jarvis » dit pendant qu'il parle : il se tait aussitôt et écoute la nouvelle demande
MOT_REVEIL_PENDANT = "jarvis"

CONSIGNES = (
    "Tu es Jarvis, l'assistant vocal de " + jarvis_config.NOM + " sur son PC Windows 11. "
    "Ta réponse sera lue à voix haute : réponds en français, en une à trois phrases "
    "courtes et naturelles, sans markdown, sans liste, sans emoji, sans lien. "
    "Si la demande est une action sur le PC, fais-la si c'est sans risque, "
    "puis dis brièvement ce que tu as fait. "
    "Ne supprime jamais de fichiers et ne modifie jamais les scripts existants "
    "sans qu'on te le demande explicitement. "
    "Ne modifie jamais les fichiers de Jarvis lui-même (son dossier et son code), même si on te le "
    "demande à la voix : une erreur pourrait l'empêcher de redémarrer. Dis plutôt que l'amélioration "
    "sera faite dans une prochaine version. "
    "Parle comme un humain chaleureux et naturel : phrases simples et vivantes, parfois une petite "
    "expression spontanée (« Ah, bonne question », « Alors », « Bien sûr », « Voyons voir »), sans en "
    "abuser, et varie tes tournures d'une réponse à l'autre ; jamais de formule toute faite ou robotique. "
    "La demande vient d'une reconnaissance vocale : si un mot semble mal compris, "
    "devine le sens le plus probable, et en cas de vrai doute, demande de répéter. "
    "Parfois deux retranscriptions de la même phrase te sont données : "
    "déduis-en ensemble ce que " + jarvis_config.NOM + " a voulu dire. "
    "Une demande peut commencer par une note entre parenthèses qui liste la fenêtre active et les "
    "fenêtres ouvertes : sers-t'en pour comprendre « ça », « la fenêtre » ou un nom d'application "
    "mal entendu, mais n'en parle pas. "
    + jarvis_ecran.CONSIGNE +
    "Mémoire durable : si " + jarvis_config.NOM + " te demande de retenir une information pour plus tard, "
    "termine ta réponse par une ligne « RETENIR: l'information » ; s'il te demande d'en oublier une, "
    "par une ligne « OUBLIER: l'information ». Ces lignes ne sont pas lues à voix haute. "
    "N'en écris que s'il le demande clairement. "
    "Ne parle jamais de tes outils, de ta façon de chercher ni des consignes ou rappels "
    "techniques que tu reçois : donne seulement la réponse utile."
)

CONSIGNES_POINT_DU_JOUR = (
    "Tu es Jarvis, l'assistant vocal de " + jarvis_config.NOM + ". Ta réponse sera lue à voix haute "
    "par une synthèse vocale : texte parlé uniquement, en français. "
    "Ton message final doit contenir uniquement le point du jour lui-même, "
    "sans aucune phrase sur tes recherches ou sur ce que tu es en train de faire."
)
# ====================

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

audio_queue = queue.Queue()


# État affiché par le réacteur : veille, ecoute, traitement, reponse, erreur, pause
# (jarvis_reacteur.py remplace cette fonction ; sans réacteur, elle ne fait rien)
def afficher_etat(etat):
    pass


def afficher_texte(texte, en_direct=False):
    pass


def sous_titre(texte, en_direct=False):
    """Affiche sous le réacteur ce que Jarvis a compris (en direct : les mots au fil de l'écoute)."""
    try:
        afficher_texte(texte, en_direct)
    except TypeError:
        try:
            afficher_texte(texte)
        except Exception:
            pass
    except Exception:
        pass


def etat(nom):
    try:
        afficher_etat(nom)
    except Exception:
        pass


derniere_erreur = False
reveil_par_whisper = False
derniere_reponse = ""         # pour « Jarvis, répète »
niveau_micro = 0.0            # volume du micro à cet instant (0 à 1), lu par le réacteur
derniers_textes = []          # les retranscriptions (Whisper, Vosk) de la dernière demande
rec_stop = None               # reconnaissance réduite aux mots « stop »
rec_coupure = None            # reconnaissance complète, pour entendre « Jarvis » pendant qu'il parle
point_pret = queue.Queue()    # point du jour préparé en arrière-plan, en attente de lecture
point_en_preparation = threading.Event()
point_annule = threading.Event()
proc_ponctuel = None          # programme Claude lancé pour le point du jour (pour pouvoir l'annuler)

# Mémoire de la conversation en cours
session_id = None
dernier_echange = 0.0

whisper = None


# ---------- Audio ----------

spectre_micro = None     # spectre du micro à cet instant (16 bandes de 0 à 1), lu par le réacteur
_crete_spectre = 4.0     # plus fort niveau vu récemment : le spectre reste lisible même avec un micro faible


sons_perdus = 0         # morceaux de son perdus par le micro (« input overflow ») pendant la demande en cours
duree_whisper = 0.0     # temps pris par Whisper pour la dernière demande


def audio_callback(indata, frames, time_info, status):
    global niveau_micro, spectre_micro, _crete_spectre
    global sons_perdus
    if status:
        print("Audio :", status, file=sys.stderr)
        if status.input_overflow:
            sons_perdus += 1
    octets = bytes(indata)
    try:
        bloc = np.frombuffer(octets, dtype=np.int16).astype(np.float32) / 32768.0
        niveau_micro = float(np.abs(bloc).max())
        bandes = jarvis_voix.bandes_spectre(bloc[None, :], SAMPLE_RATE)[0]
        _crete_spectre = max(_crete_spectre * 0.97, float(bandes.max()), 4.0)
        spectre_micro = np.clip((np.sqrt(bandes / _crete_spectre) - 0.15) / 0.85, 0, 1)
    except Exception:
        pass
    audio_queue.put(octets)


def vider_audio():
    """Oublie le son enregistré pendant que Jarvis parlait ou réfléchissait."""
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break


# ---------- Pause pendant la lecture à voix haute (F9) ----------

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
except Exception as _e:
    print("Pause automatique indisponible :", _e)
    AudioUtilities = None


_compteurs = []          # compteurs de volume des programmes à ignorer
_compteurs_date = 0.0
DELAI_RECHERCHE_PROGRAMMES = 5   # secondes entre deux recherches des programmes (opération coûteuse)


def lecture_en_cours():
    """Vrai si un des programmes à ignorer (Claude) est en train de jouer du son.
    La liste des programmes n'est relue que toutes les 5 secondes : lire leur volume
    est quasi gratuit, alors que les rechercher coûtait près de 20 % d'un cœur."""
    global _compteurs, _compteurs_date
    if AudioUtilities is None:
        return False
    try:
        if time.time() - _compteurs_date > DELAI_RECHERCHE_PROGRAMMES:
            _compteurs_date = time.time()
            _compteurs = [session._ctl.QueryInterface(IAudioMeterInformation)
                          for session in AudioUtilities.GetAllSessions()
                          if session.Process and session.Process.name().lower() in PROGRAMMES_A_IGNORER]
        return any(compteur.GetPeakValue() > 0.01 for compteur in _compteurs)
    except Exception:
        _compteurs = []
        return False


# ---------- Son du PC : baissé pendant que tu parles à Jarvis ----------

BAISSE_SON = 0.03            # niveau des autres applications pendant la conversation (1 = pas de baisse) :
                             # presque coupé, sinon le micro entend la vidéo plus fort que ta voix
# Quand une vidéo ou de la musique joue, il n'y a jamais de silence : Jarvis se réveille alors dès
# qu'il entend son nom au fil de l'eau, sans attendre la fin de la phrase.
REVEIL_PENDANT_SON = True
PAUSE_APRES_FAUX_REVEIL = 15 # secondes sans réveil « au fil de l'eau » après un réveil qui n'a rien donné
                             # (une vidéo qui prononce un mot proche de « Jarvis »)
DUREE_MAX_DEMANDE = 20       # une demande ne dure jamais plus longtemps (secondes)
_compteurs_son = []
_compteurs_son_date = 0.0


def son_pc_rapide():
    """Comme son_pc(), mais très peu coûteux : la liste des applications n'est relue que toutes les 5 s."""
    global _compteurs_son, _compteurs_son_date
    if AudioUtilities is None:
        return False
    try:
        if time.time() - _compteurs_son_date > DELAI_RECHERCHE_PROGRAMMES:
            _compteurs_son_date = time.time()
            _compteurs_son = [s._ctl.QueryInterface(IAudioMeterInformation) for s in _sessions_son()]
        return any(compteur.GetPeakValue() > 0.01 for compteur in _compteurs_son)
    except Exception:
        _compteurs_son = []
        return False
FICHIER_VOLUMES = os.path.join(DOSSIER_JARVIS, "volumes.json")
_volumes_baisses = []        # (réglage de volume, niveau d'origine) des applications baissées


def _sessions_son():
    """Les applications qui ont une sortie son, sauf Jarvis lui-même et celles mises en pause autrement."""
    sessions = []
    for session in AudioUtilities.GetAllSessions():
        try:
            if (session.Process and session.Process.pid != os.getpid()
                    and session.Process.name().lower() not in PROGRAMMES_A_IGNORER):
                sessions.append(session)
        except Exception:
            pass
    return sessions


def son_pc():
    """Vrai si une application (musique, vidéo, jeu) joue du son en ce moment."""
    if AudioUtilities is None:
        return False
    if _volumes_baisses:
        return True
    try:
        return any(s._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue() > 0.01 for s in _sessions_son())
    except Exception:
        return False


def baisser_son(insister=False):
    """Baisse les applications qui jouent du son, pour que le micro t'entende mieux.
    insister : on sait qu'une application joue ; on regarde trois fois de suite, au cas où
    elle serait pile entre deux mots au premier coup d'œil."""
    if AudioUtilities is None or BAISSE_SON >= 1 or _volumes_baisses:
        return
    try:
        origines = {}
        sessions = _sessions_son()
        for essai in range(3 if insister else 1):
            if essai:
                time.sleep(0.07)
            for session in list(sessions):
                if session._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue() < 0.005:
                    continue
                sessions.remove(session)
                volume = session.SimpleAudioVolume
                origine = volume.GetMasterVolume()
                volume.SetMasterVolume(origine * BAISSE_SON, None)
                _volumes_baisses.append((volume, origine))
                origines[session.Process.name().lower()] = origine
        if origines:
            # noté sur le disque : si Jarvis est arrêté à ce moment-là, le son sera remis au prochain démarrage
            with open(FICHIER_VOLUMES, "w", encoding="utf-8") as f:
                json.dump(origines, f)
            print("(Son du PC baissé pendant la conversation :", ", ".join(origines) + ".)")
    except Exception as erreur:
        print("Baisse du son impossible :", erreur)


def remonter_son():
    """Remet le son des applications comme il était."""
    if not _volumes_baisses:
        return
    for volume, origine in _volumes_baisses:
        try:
            volume.SetMasterVolume(origine, None)
        except Exception:
            pass
    _volumes_baisses.clear()
    try:
        os.remove(FICHIER_VOLUMES)
    except OSError:
        pass


def reparer_volumes():
    """Au démarrage : si Jarvis a été arrêté pendant une conversation, remet le son qu'il avait baissé."""
    if AudioUtilities is None:
        return
    try:
        with open(FICHIER_VOLUMES, encoding="utf-8") as f:
            origines = json.load(f)
    except (OSError, ValueError):
        return
    try:
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.name().lower() in origines:
                session.SimpleAudioVolume.SetMasterVolume(float(origines[session.Process.name().lower()]), None)
        os.remove(FICHIER_VOLUMES)
        print("(Son remis à son niveau après un arrêt de Jarvis en pleine conversation.)")
    except Exception as erreur:
        print("Remise du son impossible :", erreur)


# ---------- Reconnaissance précise (Whisper) ----------

def charger_whisper():
    global whisper
    try:
        from faster_whisper import WhisperModel
        whisper = WhisperModel(WHISPER_MODELE, device="cpu", compute_type="int8",
                               download_root=WHISPER_DOSSIER, cpu_threads=WHISPER_FILS)
        print("Reconnaissance précise (Whisper) prête.")
    except Exception as erreur:
        whisper = None
        print("Whisper indisponible, Vosk seul sera utilisé :", erreur)


def _ecrire_wav(chemin, octets):
    with wave.open(chemin, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(octets)


def _enregistrer_diagnostic(octets):
    try:
        _ecrire_wav(AUDIO_DIAGNOSTIC, octets)
    except Exception:
        pass


def garder_enregistrement(octets, texte_whisper, texte_vosk):
    """Garde le son d'une demande et ce qui a été compris (les 300 derniers sons, les 5 000 dernières lignes)."""
    try:
        os.makedirs(DOSSIER_ENREGISTREMENTS, exist_ok=True)
        nom = time.strftime("%Y-%m-%d_%Hh%Mm%S")
        _ecrire_wav(os.path.join(DOSSIER_ENREGISTREMENTS, nom + ".wav"), octets)
        index = os.path.join(DOSSIER_ENREGISTREMENTS, "index.txt")
        with open(index, "a", encoding="utf-8") as f:
            f.write(f"{nom} | Whisper : {texte_whisper} | Vosk : {texte_vosk}\n")
        with open(index, encoding="utf-8", errors="replace") as f:      # quelques centaines de Ko : lu en un instant
            lignes = f.readlines()
        if len(lignes) > LIGNES_INDEX:
            with open(index, "w", encoding="utf-8") as f:
                f.writelines(lignes[-LIGNES_INDEX:])
        sons = sorted(x for x in os.listdir(DOSSIER_ENREGISTREMENTS) if x.endswith(".wav"))
        for ancien in sons[:-NB_ENREGISTREMENTS]:
            os.remove(os.path.join(DOSSIER_ENREGISTREMENTS, ancien))
    except Exception:
        pass


def _normaliser(texte):
    return re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüœ]+", " ", texte.lower()).strip()


def est_politesse(texte):
    """Vrai pour un simple remerciement ou compliment (« c'est bon, bravo », « merci beaucoup »)."""
    propre = _normaliser(texte)
    mots = propre.split()
    if propre in POLITESSES:
        return True
    return (0 < len(mots) <= 14 and all(m in MOTS_POLITESSE for m in mots)
            and bool(CLES_POLITESSE.search(propre)))


def _repetitif(texte):
    """Vrai si Whisper a « inventé » une phrase qui tourne en boucle (sur du bruit)."""
    mots = _normaliser(texte).split()
    return len(mots) >= 6 and len(set(mots)) <= len(mots) / 3


def _retirer_bip(audio, duree=0.45):
    """Efface du début de l'enregistrement les deux notes du bip de réveil (que le micro peut
    capter), sans toucher à la voix : seules leurs fréquences précises sont retirées."""
    n = min(len(audio), int(SAMPLE_RATE * duree))
    if n < 512:
        return audio
    spectre = np.fft.rfft(audio[:n])
    frequences = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    for hz, _ in jarvis_voix.NOTES_BIP:
        for harmonique in (hz, 2 * hz):
            spectre[np.abs(frequences - harmonique) < 70] = 0
    audio = audio.copy()
    audio[:n] = np.fft.irfft(spectre, n)
    return audio


def transcrire(octets, texte_vosk, bip_au_debut=False):
    """Retranscrit l'audio avec Whisper. En cas de souci, garde le texte de Vosk."""
    global duree_whisper, sons_perdus
    if whisper is None or not octets or not texte_vosk:
        return texte_vosk
    _enregistrer_diagnostic(octets)
    try:
        audio = np.frombuffer(octets, dtype=np.int16).astype(np.float32) / 32768.0
        if bip_au_debut:
            audio = _retirer_bip(audio)
        crete = float(np.max(np.abs(audio))) if len(audio) else 0.0
        print("Niveau du micro (crête) : %.2f" % crete)
        if 0.01 < crete < 0.5:
            audio = audio * (0.7 / crete)       # voix trop faible : on l'amplifie
        if WHISPER_SILENCE:
            audio = np.concatenate((np.zeros(int(SAMPLE_RATE * WHISPER_SILENCE), dtype=np.float32), audio))
        debut_whisper = time.time()
        segments, _ = whisper.transcribe(audio, language="fr", beam_size=WHISPER_FAISCEAU,
                                         initial_prompt=VOCABULAIRE)
        texte = " ".join(s.text for s in segments).strip()
        duree_whisper = time.time() - debut_whisper
    except Exception as erreur:
        print("Erreur Whisper :", erreur)
        return texte_vosk
    # Hallucinations connues de Whisper sur du bruit
    if not texte or re.search(r"amara|sous-titr", texte, re.I):
        return texte_vosk
    if _repetitif(texte):
        print("Whisper a inventé une phrase en boucle (bruit) : demande ignorée. Vosk :", texte_vosk)
        return None
    print("Whisper :", texte, "| Vosk :", texte_vosk)
    if sons_perdus:
        print(f"(Attention : {sons_perdus} morceau(x) de son perdu(s) par le micro pendant cette demande.)")
        sons_perdus = 0
    garder_enregistrement(octets, texte, texte_vosk)
    return texte


def combiner(texte_whisper, texte_vosk):
    """Texte envoyé à Claude : une version si elles concordent, sinon les deux."""
    global derniers_textes
    derniers_textes = [t for t in (texte_whisper, texte_vosk) if t]
    if not texte_vosk or _normaliser(texte_whisper) == _normaliser(texte_vosk):
        return texte_whisper or texte_vosk
    if not texte_whisper:
        return texte_vosk
    return (f"« {texte_whisper} » (autre retranscription possible de la même phrase : "
            f"« {texte_vosk} »)")


def retirer_nom(texte):
    """Renvoie ce qui suit le premier « Jarvis » de la phrase, ou None s'il n'y est pas."""
    m = re.search(r"\bjarvis\b\W*(.*)", texte, re.I | re.S)
    return m.group(1).strip() if m else None


def chercher_reveil(resultat, audio):
    """
    Décide si la phrase entendue réveille Jarvis. Renvoie la demande qui suit son nom
    (« » s'il n'a dit que « Jarvis »), ou None si la phrase ne lui est pas adressée.
      1. la phrase commence par « Jarvis » ;
      2. « Jarvis » est au milieu, mais après une courte pause (nouvelle phrase) ;
      3. le début ressemble à « Jarvis » mal compris, et Whisper confirme que c'en est un.
    """
    global reveil_par_whisper
    reveil_par_whisper = False
    phrase = resultat.get("text", "").lower()
    m = re.match(r"\s*jarvis\b(.*)", phrase)
    if m:
        return m.group(1).strip()
    mots = resultat.get("result") or []
    for i in range(1, len(mots)):
        # « ...avant de lancer la démonstration Jarvis affiche... » : on parle de lui, pas à lui
        pause_voulue = PAUSE_AVANT_JARVIS if i <= MOTS_AVANT_JARVIS else PAUSE_LONGUE_AVANT_JARVIS
        if mots[i]["word"] == "jarvis" and mots[i]["start"] - mots[i - 1]["end"] >= pause_voulue:
            return " ".join(x["word"] for x in mots[i + 1:])
    if whisper is not None and phrase.startswith(PRESQUE_JARVIS):
        precise = transcrire(audio, phrase)
        if precise and re.match(r"\W*jarvis\b", precise, re.I):
            print("(Réveil confirmé par Whisper.)")
            reveil_par_whisper = True          # la demande est déjà la version précise
            return retirer_nom(precise) or ""
    return None


def ecouter_demande(recognizer, delai_debut, silence_fin=SILENCE_FIN, bip_au_debut=False):
    """
    Écoute une demande complète, même si elle contient de petites pauses.
    - attend au plus « delai_debut » secondes que tu commences à parler ;
    - ensuite, s'arrête quand tu te tais pendant « silence_fin » secondes.
    """
    global sons_perdus
    sons_perdus = 0
    morceaux = []
    octets = bytearray()
    debut = time.time()
    dernier_son = None
    partiel = affiche = ""
    while True:
        maintenant = time.time()
        if dernier_son is None and maintenant - debut > delai_debut:
            break
        if maintenant - debut > DUREE_MAX_DEMANDE:
            break
        if dernier_son is not None and maintenant - dernier_son > silence_fin:
            if morceaux or partiel:
                break
            dernier_son = None         # ce n'était qu'un bruit (le bip, un claquement) : on attend encore
        try:
            data = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        octets.extend(data)
        if recognizer.AcceptWaveform(data):
            texte = json.loads(recognizer.Result()).get("text", "").strip()
            partiel = ""
            if texte:
                morceaux.append(texte)
                dernier_son = time.time()
        else:
            partiel = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            if partiel:
                dernier_son = time.time()
        en_cours = " ".join(morceaux + ([partiel] if partiel else []))
        if en_cours and en_cours != affiche:
            affiche = en_cours
            sous_titre(en_cours, en_direct=True)
    fin = json.loads(recognizer.FinalResult()).get("text", "").strip()
    if fin:
        morceaux.append(fin)
    texte_vosk = " ".join(morceaux).strip()
    if texte_vosk and sans_whisper(texte_vosk):
        derniers_textes[:] = [texte_vosk]      # commande simple : pas besoin de Whisper
        return texte_vosk
    precise = transcrire(bytes(octets), texte_vosk, bip_au_debut)
    if precise is None:
        return ""                      # ce n'était que du bruit
    return combiner(precise, texte_vosk)


# ---------- Claude ----------

class ClaudeContinu:
    """
    Garde Claude Code ouvert en permanence : plus de démarrage à chaque question
    (environ 1 à 2 secondes par réponse au lieu de 8 à 15), et la mémoire de la
    conversation est conservée tant que le programme tourne.
    """

    def __init__(self):
        self.proc = None
        self.sorties = queue.Queue()
        self.dernier_usage = 0.0
        self.utilise = False              # la conversation en cours contient-elle des échanges ?
        self.verrou = threading.Lock()
        self.absent = False               # vrai quand Claude Code n'est pas installé sur ce PC

    def _lire(self, flux, file_sortie):
        for ligne in flux:
            if file_sortie is not None:
                file_sortie.put(ligne)
        if file_sortie is not None:
            file_sortie.put(None)          # fin du programme

    @staticmethod
    def _consignes():
        """Consignes de Jarvis, suivies de sa mémoire (faits retenus, derniers échanges)."""
        try:
            memoire = jarvis_memoire.contexte()
        except Exception as erreur:
            print("Mémoire illisible :", erreur)
            memoire = ""
        return CONSIGNES + ("\n\n" + memoire if memoire else "")

    def demarrer(self):
        self.arreter()
        if not os.path.exists(CLAUDE_EXE):       # Jarvis installé sans Claude : commandes immédiates seulement
            if not self.absent:
                self.absent = True
                print("Claude Code n'est pas installé : seules les commandes immédiates fonctionnent.")
            return
        self.absent = False
        self.sorties = queue.Queue()
        self.proc = subprocess.Popen(
            [CLAUDE_EXE, "-p", "--input-format", "stream-json",
             "--output-format", "stream-json", "--verbose", "--include-partial-messages",
             "--append-system-prompt", self._consignes(),
             "--permission-mode", MODE_PERMISSIONS, "--model", MODELE,
             *OPTIONS_LEGERES, "--tools", OUTILS],
            cwd=DOSSIER_JARVIS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._lire, args=(self.proc.stdout, self.sorties),
                         daemon=True).start()
        threading.Thread(target=self._lire, args=(self.proc.stderr, None),
                         daemon=True).start()
        self.dernier_usage = time.time()
        self.utilise = False
        print("Claude prêt en continu (modèle", MODELE + ").")

    def entretenir(self):
        """Quand la mémoire de la conversation a expiré, relance Claude à l'avance
        (en arrière-plan) : la question suivante n'attend plus son démarrage."""
        if (self.utilise and time.time() - self.dernier_usage > MEMOIRE_MINUTES * 60
                and self.verrou.acquire(blocking=False)):
            try:
                self.demarrer()
            finally:
                self.verrou.release()

    def arreter(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def demander(self, texte, delai=DELAI_MAX_CLAUDE, morceau=None):
        """Renvoie (réponse, erreur). morceau : fonction appelée avec chaque bout de texte dès que Claude
        l'écrit (longues histoires : Jarvis commence à lire sans attendre la fin)."""
        with self.verrou:
            if (self.proc is None or self.proc.poll() is not None
                    or (self.utilise and time.time() - self.dernier_usage > MEMOIRE_MINUTES * 60)):
                self.demarrer()        # nouvelle conversation
            if self.proc is None:
                return SANS_CLAUDE, True
            self.utilise = True
            texte = jarvis_memoire.nouveautes() + texte
            message = {"type": "user", "message": {"role": "user", "content": texte}}
            try:
                self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
            except Exception as erreur:
                print("Erreur d'envoi à Claude :", erreur)
                self.arreter()
                return "Je n'arrive pas à joindre Claude.", True
            fin = time.time() + delai
            while True:
                try:
                    ligne = self.sorties.get(timeout=max(0.1, fin - time.time()))
                except queue.Empty:
                    self.arreter()
                    return "Claude met trop de temps à répondre, j'abandonne cette demande.", True
                if ligne is None:
                    self.arreter()
                    return "Claude s'est arrêté, je le relance pour la prochaine demande.", True
                try:
                    donnees = json.loads(ligne)
                except Exception:
                    continue
                if donnees.get("type") == "stream_event" and morceau is not None:
                    evenement = donnees.get("event") or {}
                    delta = evenement.get("delta") or {}
                    if evenement.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        try:
                            morceau(delta.get("text") or "")
                        except Exception:
                            pass
                    continue
                if donnees.get("type") != "result":
                    continue
                self.dernier_usage = time.time()
                reponse = str(donnees.get("result") or "").strip()
                if donnees.get("is_error") or not reponse:
                    print("Claude (erreur) :", ligne[:500])
                    if "limit" in ligne.lower():
                        return ("La limite d'utilisation de Claude est atteinte pour le moment. Je réponds quand "
                                "même tout de suite à l'heure, la météo, les minuteurs, la musique et les fenêtres."), True
                    return "Claude a rencontré un problème avec cette demande.", True
                return reponse, False


SANS_CLAUDE = ("Pour cette demande, j'ai besoin de Claude, qui n'est pas installé sur ce PC. "
               "Je réponds quand même aux commandes immédiates : l'heure, la météo, les minuteurs, les fenêtres. "
               "Pour ajouter Claude, relance le fichier Installer Jarvis, rangé dans mon dossier, et choisis Ajouter Claude.")
claude = ClaudeContinu()


def oublier_conversation():
    """Repart de zéro : Claude est relancé (en arrière-plan)."""
    threading.Thread(target=claude.demarrer, daemon=True).start()


def _tuer(proc):
    """Arrête un programme et ceux qu'il a lancés."""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def demander_a_claude(demande, consignes=CONSIGNES, delai=DELAI_MAX_CLAUDE):
    """Demande ponctuelle (programme lancé pour une seule question), utilisée pour
    le point du jour, qui a ses propres consignes et le modèle le plus puissant.
    Renvoie (réponse, erreur)."""
    global proc_ponctuel
    if not os.path.exists(CLAUDE_EXE):
        return "Je ne trouve pas Claude Code sur cet ordinateur.", True
    commande = [
        CLAUDE_EXE,
        "-p", demande,
        "--append-system-prompt", consignes,
        "--permission-mode", MODE_PERMISSIONS,
        "--output-format", "json",
        "--model", MODELE_POINT_DU_JOUR,
        *OPTIONS_LEGERES, "--tools", OUTILS_POINT_DU_JOUR,
    ]
    proc = None
    try:
        proc = proc_ponctuel = subprocess.Popen(
            commande,
            cwd=DOSSIER_JARVIS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        sortie, erreurs = proc.communicate(timeout=delai)
    except subprocess.TimeoutExpired:
        _tuer(proc)
        return "Claude met trop de temps à répondre, j'abandonne cette demande.", True
    except Exception as erreur:
        print("Erreur Claude :", erreur)
        return "Je n'arrive pas à joindre Claude.", True
    finally:
        proc_ponctuel = None

    sortie = (sortie or "").strip()
    try:
        donnees = json.loads(sortie)
    except Exception:
        donnees = None
    if not donnees:
        print("Claude (erreurs) :", (erreurs or "").strip() or sortie)
        if "limit" in ((erreurs or "") + sortie).lower():
            return "La limite d'utilisation de Claude est atteinte pour le moment.", True
        return "Claude ne m'a pas répondu.", True
    reponse = str(donnees.get("result") or "").strip()
    if donnees.get("is_error") or not reponse:
        print("Claude (erreur) :", sortie[:500])
        return "Claude a rencontré un problème avec cette demande.", True
    return re.sub(r"[*_#`>]", "", reponse), False


def _enumerer(elements):
    """« a, b et c »"""
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " et " + elements[-1]


def question_point_du_jour():
    sujets, site = jarvis_config.SUJETS, jarvis_config.SITE
    t = time.localtime()
    date = f"{JOURS[t.tm_wday]} {t.tm_mday} {MOIS[t.tm_mon - 1]} {t.tm_year}"
    # La météo est relevée directement (Open-Meteo) : fiable, et autant de recherches en moins
    meteo = commande_instantanee(["quelle est la météo"])
    # Titres du jour et page du site suivi, lus directement depuis le PC (voir jarvis_sources.py)
    actus = jarvis_sources.actualites()
    page = jarvis_sources.page_du_site(site["adresse"]) if site else ""
    nom_site = (site.get("nom") or site["adresse"]) if site else ""
    if meteo:
        meteo = (" Pour la météo, n'effectue aucune recherche : voici le relevé vérifié, "
                 f"à reformuler naturellement : « {meteo} »")
    return (
        f"Nous sommes le {date}, c'est la date exacte. "
        "Fais-moi le point du jour, dans cet ordre : "
        f"la météo du jour à {VILLE_METEO}, et pas celle d'une autre position ; "
        "les principales actualités en France et dans le monde"
        + (", choisies parmi les titres de grands médias relevés à l'instant, donnés à la fin de ce message "
           "(garde les cinq à sept plus importantes, et fais une recherche web si tu as besoin d'un détail)"
           if actus else "")
        + "".join(" ; " + sujet for sujet in sujets)
        + ((f" ; et enfin les articles sur {site.get('sujet') or 'tes sujets'} publiés aujourd'hui "
            f"sur {nom_site}, d'après sa page d'accueil relevée à l'instant et donnée à la fin de ce message "
            f"(n'essaie pas d'ouvrir ce site toi-même ; la date d'aujourd'hui s'y écrit "
            f"{t.tm_mday:02d}-{t.tm_mon:02d})") if site and page else
           (f" ; et enfin les articles sur {site.get('sujet') or 'tes sujets'} publiés aujourd'hui "
            f"sur le site {site['adresse']}, que tu consultes directement") if site else "")
        + ". Fais une vraie recherche web pour chaque autre rubrique"
        + (", y compris une recherche dédiée " + _enumerer(["pour " + sujet for sujet in sujets])
           if sujets else "") + ". "
        "Vérifie que chaque information date bien d'aujourd'hui ou d'hier, qu'elle vient "
        "d'un média sérieux et qu'elle contient un nom, un lieu ou un chiffre précis. "
        "Si tu n'es pas sûr d'une information, ne la donne pas. "
        "Si tu trouves moins d'actualités que demandé, ou rien du tout pour une rubrique, "
        "dis-le simplement. N'invente jamais rien. "
        + (f"Si {site.get('nom') or site['adresse']} ne peut pas être consulté ou n'a rien publié "
           "sur ce sujet aujourd'hui, dis-le en une phrase. " if site else "") +
        "Environ 650 mots, et plus si c'est nécessaire pour ne rien oublier d'important. "
        "TRÈS IMPORTANT, ta réponse sera lue à voix haute : écris uniquement un texte parlé "
        "et fluide, comme un présentateur radio. Commence directement par la date, sans "
        "aucune phrase pour annoncer ce que tu vas faire. Aucun titre, aucun gras, aucune "
        "liste, aucun numéro devant les actualités. Passe d'un sujet à l'autre avec des "
        "transitions parlées. Ne cite jamais tes sources ni le nom des médias, et ne mets "
        "rien entre parenthèses. Aucune remarque, réserve ou explication sur tes recherches "
        "à la fin. Termine par une seule courte phrase."
        + (meteo or "")
        + (f"\n\nTITRES DU JOUR (relevés à l'instant, déjà datés) :\n{actus}" if actus else "")
        + (f"\n\nPAGE D'ACCUEIL DE {nom_site.upper()} (relevée à l'instant) :\n{page}" if page else "")
    )[:24000]                    # la demande passe par la ligne de commande, limitée à 32 000 caractères


def point_du_jour_deja_fait():
    try:
        with open(FICHIER_POINT_DU_JOUR, encoding="utf-8") as f:
            return f.read().strip() == time.strftime("%Y-%m-%d")
    except OSError:
        return False


def preparer_point_du_jour(attente=0):
    """Prépare le point du jour en arrière-plan ; il sera lu dès qu'il est prêt."""
    if point_en_preparation.is_set():
        return
    point_en_preparation.set()
    point_annule.clear()
    try:
        fin_attente = time.time() + attente
        while time.time() < fin_attente and not point_annule.is_set():
            time.sleep(0.2)
        if point_annule.is_set():
            return
        print("Préparation du point du jour...")
        texte, erreur = demander_a_claude(question_point_du_jour(),
                                          consignes=CONSIGNES_POINT_DU_JOUR,
                                          delai=DELAI_MAX_POINT_DU_JOUR)
        if point_annule.is_set():
            print("Point du jour annulé.")
            return
        if erreur:
            print("Point du jour impossible :", texte)
            point_pret.put(("Je n'ai pas réussi à préparer ton point du jour. " + texte, True))
            return
        try:
            with open(FICHIER_POINT_DU_JOUR, "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d"))
        except OSError:
            pass
        point_pret.put((texte, False))
    finally:
        point_en_preparation.clear()


def annuler_point_du_jour():
    """Arrête la préparation en cours. Renvoie False s'il n'y en avait pas."""
    if not point_en_preparation.is_set():
        return False
    point_annule.set()
    proc = proc_ponctuel
    if proc is not None:
        _tuer(proc)
    return True


# ---------- Phrases variées, salutations, petites attentions ----------

PATIENCE = ["Je m'en occupe.", "C'est parti.", "Je regarde ça.", "Une petite seconde.", "Laisse-moi voir."]
REMERCIEMENTS = ["Avec plaisir.", "De rien, c'est un plaisir.", "À ton service !", "Toujours là pour toi.",
                 "Pas de quoi, c'est mon métier !", "Quand tu veux. Je ne dors jamais vraiment, de toute façon.",
                 "Avec plaisir. Et je n'envoie même pas de facture !"]
DUREE_TACHE_LONGUE = 8        # secondes : au-delà, un petit son signale que la réponse est prête
FICHIER_SALUTATION = jarvis_config.chemin("salutation.date")
fete_demandee = None          # (moment, "anniversaire") : le réacteur joue une petite animation
_derniere_phrase = {}


def phrase_variee(liste):
    """Une phrase de la liste, jamais deux fois de suite la même."""
    cle = id(liste)
    choix = [p for p in liste if p != _derniere_phrase.get(cle)] or liste
    _derniere_phrase[cle] = random.choice(choix)
    return _derniere_phrase[cle]


def anniversaire_aujourdhui():
    """Vrai si c'est l'anniversaire de l'utilisateur : config.json ("anniversaire": "3/03"),
    sinon ce qu'il a demandé à Jarvis de retenir (« je suis né le 3 mars... »)."""
    jour = time.localtime()
    texte = str(jarvis_config._lu.get("anniversaire") or "")
    m = re.match(r"\s*(\d{1,2})[/.-](\d{1,2})", texte)
    if m:
        return (int(m.group(1)), int(m.group(2))) == (jour.tm_mday, jour.tm_mon)
    try:
        faits = " ".join(str(f) for f in jarvis_memoire.faits()).lower()
    except Exception:
        return False
    m = re.search(r"\bn[ée]e? le (\d{1,2}|premier|1er) (\w+)", faits)
    if not m:
        return False
    j = 1 if m.group(1) in ("premier", "1er") else int(m.group(1))
    return m.group(2) in MOIS and (j, MOIS.index(m.group(2)) + 1) == (jour.tm_mday, jour.tm_mon)


def salutation_du_jour():
    """À la première réponse de la journée : « Bonjour Tony ! » (ou bon après-midi, bonsoir),
    et « joyeux anniversaire » le bon jour. Renvoie « » les autres fois."""
    global fete_demandee
    aujourdhui = time.strftime("%Y-%m-%d")
    try:
        with open(FICHIER_SALUTATION, encoding="utf-8") as f:
            if f.read().strip() == aujourdhui:
                return ""
    except OSError:
        pass
    try:
        with open(FICHIER_SALUTATION, "w", encoding="utf-8") as f:
            f.write(aujourdhui)
    except OSError:
        pass
    h = time.localtime().tm_hour
    debut = "Bonjour" if 5 <= h < 12 else "Bon après-midi" if 12 <= h < 18 else "Bonsoir"
    if anniversaire_aujourdhui():
        fete_demandee = (time.time(), "anniversaire")
        return f"{debut}{jarvis_config.SALUT}, et joyeux anniversaire ! "
    return f"{debut}{jarvis_config.SALUT} ! "


def avec_salutation(reponse):
    """Ajoute la salutation du jour devant une réponse, sauf si elle salue déjà."""
    if re.match(r"\W*(bonjour|bonsoir|bon après-midi|salut|bonne nuit)\b", reponse or "", re.I):
        salutation_du_jour()                     # la journée est quand même marquée comme saluée
        return reponse
    return salutation_du_jour() + reponse


# ---------- La musique fait danser le réacteur ----------

niveau_musique = 0.0          # niveau du son des autres applications (0 à 1), relevé 25 fois par seconde


def suivre_musique():
    global niveau_musique
    if AudioUtilities is None:
        return
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    compteurs, depuis = [], 0.0
    while True:
        try:
            if time.time() - depuis > 3:
                depuis = time.time()
                compteurs = [x._ctl.QueryInterface(IAudioMeterInformation) for x in _sessions_son()]
            niveau_musique = max([c.GetPeakValue() for c in compteurs] or [0.0])
            time.sleep(0.04)
        except Exception:
            compteurs, niveau_musique = [], 0.0
            time.sleep(1)


# ---------- Interruption ----------

coupe_par_jarvis = False      # vrai si Jarvis vient d'être coupé par « Jarvis » (et non par « stop »)
_jarvis_dans_texte = False    # Jarvis prononce lui-même son nom : on ignore alors « jarvis » (écho du haut-parleur)


def interruption():
    """Vrai si l'on a dit « stop », ou « Jarvis » pour enchaîner sur une autre demande, pendant que Jarvis parle."""
    global coupe_par_jarvis
    if rec_stop is None:
        return False
    while True:
        try:
            data = audio_queue.get_nowait()
        except queue.Empty:
            return False
        # « Jarvis » : reconnaissance au vocabulaire complet, comme pour le réveil. Avec une liste réduite
        # de mots, Vosk croyait entendre « jarvis » dans presque toutes les phrases (essai du 17/11/2026 :
        # des dizaines de faux départs sur la voix de Jarvis ; aucun avec le vocabulaire complet).
        if rec_coupure is not None and not _jarvis_dans_texte:
            if rec_coupure.AcceptWaveform(data):
                entendu = json.loads(rec_coupure.Result()).get("text", "")
            else:
                entendu = json.loads(rec_coupure.PartialResult()).get("partial", "")
            if re.search(r"\bjarvis\b", entendu):
                print("Interruption : « Jarvis » (nouvelle demande)")
                coupe_par_jarvis = True
                return True
        if rec_stop.AcceptWaveform(data):
            texte = json.loads(rec_stop.Result()).get("text", "")
            if texte and texte in MOTS_STOP:
                print("Interruption :", texte)
                return True


def parler(texte, toujours=False):
    """Parle en restant à l'écoute du mot « stop ». Renvoie True si interrompu.
    toujours=True : même en mode nuit (rappels et réveil)."""
    global coupe_par_jarvis, _jarvis_dans_texte
    if rec_stop is not None:
        rec_stop.Reset()
    if rec_coupure is not None:
        rec_coupure.Reset()
    vider_audio()
    coupe_par_jarvis = False
    _jarvis_dans_texte = "jarvis" in (texte or "").lower()
    return bool(speak(texte, interruption=interruption, toujours=toujours))


# ---------- Déroulement ----------

def preparer_ecoute(recognizer):
    recognizer.Reset()
    time.sleep(0.3)
    vider_audio()


def traiter(demande, recognizer):
    """Traite une demande. Renvoie True si Jarvis a été interrompu."""
    global derniere_reponse, duree_whisper
    print("Demande :", demande)
    debut_traitement = time.time()
    whisper_ici, duree_whisper = duree_whisper, 0.0
    mesure = (f"Whisper {whisper_ici:.1f} s, " if whisper_ici else "")
    minuscules = demande.lower()
    sous_titre(derniers_textes[0] if derniers_textes else demande)
    if derniere_reponse and re.match(r"\W*(répète|repete|tu peux répéter|redis)", minuscules):
        etat("reponse")
        interrompu = parler(derniere_reponse)
        preparer_ecoute(recognizer)
        return interrompu
    if re.search(r"nouvelle conversation|oublie tout(?! ce que)", minuscules):
        oublier_conversation()
        etat("reponse")
        speak("D'accord, on repart de zéro.")
        preparer_ecoute(recognizer)
        return False

    if DEMANDE_REDEMARRAGE.search(minuscules) or any(DEMANDE_REDEMARRAGE.search(x.lower()) for x in derniers_textes):
        etat("reponse")
        speak("Je redémarre.")
        redemarrer()

    # Commandes instantanées : réponse immédiate, sans Claude
    reponse = commande_instantanee(derniers_textes or [demande],
                                   annoncer=lambda texte: point_pret.put((texte, "rappel")))
    if reponse:
        derniere_reponse = reponse
        print("Commande instantanée :", reponse)
        print(f"(Durées : {mesure}commande {time.time() - debut_traitement:.2f} s)")
        jarvis_memoire.noter_echange(derniers_textes[0] if derniers_textes else demande, reponse)
        etat("reponse")
        interrompu = parler(avec_salutation(reponse))
        preparer_ecoute(recognizer)
        return interrompu

    if re.search(r"point du jour", minuscules):
        etat("reponse")
        if re.search(r"\b(annule\w*|arr[êe]te\w*|stop|laisse tomber)\b", minuscules):
            if annuler_point_du_jour():
                speak("D'accord, j'annule le point du jour.")
            else:
                speak("Aucun point du jour n'est en préparation.")
        elif point_en_preparation.is_set():
            speak("Ton point du jour est déjà en préparation, je te le lis dès qu'il est prêt.")
        else:
            # Préparé en arrière-plan : tu peux continuer à me parler, ou l'annuler
            threading.Thread(target=preparer_point_du_jour, daemon=True).start()
            speak("Je prépare ton point du jour, je te le lis dès qu'il est prêt.")
        preparer_ecoute(recognizer)
        return False

    etat("traitement")
    # Claude travaille pendant que Jarvis parle : on ne perd pas de temps
    resultat = {}

    # Claude sait ce qui est ouvert à l'écran : il comprend « ferme ça » ou un nom mal entendu
    try:
        note = jarvis_fenetres.contexte()
    except Exception:
        note = ""
    # « qu'est-ce qu'il y a à l'écran ? », « résume ce que j'ai copié » : Claude reçoit l'image ou le texte
    try:
        note += jarvis_ecran.complement(minuscules)
    except Exception as erreur_ecran:
        print("Écran ou presse-papiers illisible :", erreur_ecran)

    # Mode enfant : réponses adaptées, quiz, longues histoires (avec la suite plus tard)
    try:
        note = jarvis_enfant.note(demande) + note
        histoire = jarvis_enfant.histoire_demandee(demande)
    except Exception as erreur_enfant:
        print("Mode enfant :", erreur_enfant)
        histoire = False

    if histoire:
        return raconter(note + demande, demande, recognizer)

    def travail():
        resultat["r"] = claude.demander(note + demande)

    fil = threading.Thread(target=travail, daemon=True)
    fil.start()
    fil.join(DELAI_AVANT_PATIENCE)
    if fil.is_alive() and not histoire:
        speak(phrase_variee(PATIENCE))
    fil.join()
    reponse, erreur = resultat.get("r", ("Claude ne m'a pas répondu.", True))
    print("Claude :", reponse)
    print(f"(Durées : {mesure}Claude {time.time() - debut_traitement:.1f} s)")
    if not erreur:
        reponse = jarvis_enfant.appliquer(reponse)              # résumé de l'histoire gardé pour la suite
        reponse = jarvis_ecran.appliquer_copie(reponse)        # texte corrigé ou traduit -> presse-papiers
        reponse = re.sub(r"[*_#`>]", "", reponse)
        reponse = jarvis_memoire.appliquer_balises(reponse) or "C'est noté."
        jarvis_memoire.noter_echange(derniers_textes[0] if derniers_textes else demande, reponse)
    derniere_reponse = reponse
    etat("erreur" if erreur else "reponse")
    if not erreur:
        if time.time() - debut_traitement > DUREE_TACHE_LONGUE:
            jarvis_voix.son_fini()                 # une longue tâche est finie : petit son avant la réponse
        reponse = avec_salutation(reponse)
    interrompu = parler(reponse)
    preparer_ecoute(recognizer)
    return interrompu


_FIN_DE_PHRASE = re.compile(r"[.!?…][»\")]?\s")
_DEBUT_BALISE = re.compile(r"\n\s*H(?:I(?:S(?:T(?:O(?:I(?:R(?:E)?)?)?)?)?)?)?\s*:?\s*$|^\s*HISTOIRE\s*:", re.M)


def raconter(message, demande, recognizer):
    """Longue histoire (mode enfant) : Jarvis lit l'histoire au fur et à mesure que Claude l'écrit,
    au lieu d'attendre la fin (environ 30 secondes). Renvoie True si interrompu."""
    global derniere_reponse
    morceaux, verrou, fini, resultat = [], threading.Lock(), threading.Event(), {}

    def recevoir(texte):
        with verrou:
            morceaux.append(texte)

    def travail():
        try:
            reponse, erreur = claude.demander(message, morceau=recevoir)
            if not erreur:
                reponse = jarvis_enfant.appliquer(reponse)       # résumé gardé pour « la suite »
                jarvis_memoire.noter_echange(demande, reponse)
            resultat["r"] = (reponse, erreur)
        finally:
            fini.set()

    threading.Thread(target=travail, daemon=True).start()
    etat("reponse")
    speak("Je prépare ton histoire.")
    lu, interrompu, tout = 0, False, ""
    while True:
        termine = fini.is_set()
        with verrou:
            tout = "".join(morceaux)
        balise = _DEBUT_BALISE.search(tout)
        lisible = tout[:balise.start()] if balise else tout
        reste = lisible[lu:]
        if termine:
            bout = reste
        else:
            fins = list(_FIN_DE_PHRASE.finditer(reste))
            bout = reste[:fins[-1].end()] if fins else ""
            if lu == 0 and len(bout) < 250:          # le premier morceau : quelques phrases, pour bien démarrer
                bout = ""
        if bout.strip():
            lu += len(bout)
            interrompu = parler(re.sub(r"[*_#`>]", "", bout))
            if interrompu:
                break
            continue
        if termine:
            break
        time.sleep(0.2)
    reponse, erreur = resultat.get("r", ("", False))
    if erreur and not lu:
        print("Claude :", reponse)
        etat("erreur")
        interrompu = parler(reponse)
    print("Claude (histoire lue au fur et à mesure) :", len(tout.split()), "mots")
    derniere_reponse = re.sub(r"[*_#`>]", "", (tout[:_DEBUT_BALISE.search(tout).start()]
                                                if _DEBUT_BALISE.search(tout) else tout)).strip() or derniere_reponse
    preparer_ecoute(recognizer)
    return interrompu


# « redémarre-toi », y compris mal entendu (« redémarte-toi », « redémarre temps »)
DEMANDE_REDEMARRAGE = re.compile(r"\b(red[ée]mar\w*|relance\w*)[- ]+(toi|toit|temps|toa)\b|\b(red[ée]mar\w*|relance) jarvis\b")


def redemarrer():
    """Relance Jarvis : par le gardien s'il est là, sinon par le raccourci."""
    remonter_son()
    try:
        claude.arreter()
    except Exception:
        pass
    print("(Redémarrage demandé.)")
    etat("arret")                      # le réacteur se referme
    time.sleep(0.8)
    if os.environ.get("JARVIS_GARDIEN"):
        os._exit(3)
    subprocess.Popen('cmd /c "timeout /t 2 >nul & start "" "' + os.path.join(DOSSIER_JARVIS, "Jarvis.lnk") + '""',
                     shell=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os._exit(0)


def conversation(demande, recognizer):
    """Traite la demande, puis accepte des suites sans redire « Jarvis »."""
    essais_courts = 0
    while demande:
        # « Jarvis » redit pendant la conversation : on écoute la suite, sans déranger Claude
        if re.fullmatch(r"\W*jarvis\W*", demande, re.I) or (
                derniers_textes and re.fullmatch(r"\W*jarvis\W*", derniers_textes[0], re.I)):
            bip(attendre=False)
            etat("ecoute")
            demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True)
            continue
        if re.fullmatch(r"\W*(?:jarvis\W+)?(?:stop|arr[eê]te|tais[- ]toi)\W*", demande, re.I):
            preparer_ecoute(recognizer)          # « Jarvis... stop » : il se tait simplement
            break
        if est_politesse(demande) and not jarvis_commandes.confirmation_en_attente():
            speak(phrase_variee(REMERCIEMENTS))
            preparer_ecoute(recognizer)
            break
        if (len(demande.split()) < MOTS_MINIMUM and not jarvis_commandes.confirmation_en_attente()
                and not re.match(r"\W*(bonjour|bonsoir|salut)\W*$", demande, re.I)
                and not jarvis_commandes.mot_court(demande)
                and not DEMANDE_REDEMARRAGE.search(demande.lower())):
            print("Demande trop courte :", demande)
            essais_courts += 1
            if essais_courts > 1:
                speak("Je n'ai pas compris, redis Jarvis quand tu veux.")
                preparer_ecoute(recognizer)
                etat("veille")
                return
            speak("Je n'ai pas bien compris, tu peux répéter ?")
            preparer_ecoute(recognizer)
            etat("ecoute")
            demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE)
            continue
        essais_courts = 0
        if traiter(demande, recognizer):
            if coupe_par_jarvis:       # coupé par « Jarvis » : on abandonne la réponse et on écoute la suivante
                bip(attendre=False)
                etat("ecoute")
                demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True)
                continue
            break                      # interrompu par « stop » : retour en veille
        # Une nouvelle version trouvée sur GitHub au démarrage : annoncée une fois, après une réponse
        if not jarvis_commandes.confirmation_en_attente() and jarvis_maj.a_annoncer():
            jarvis_commandes.demander_confirmation("maj")
            if parler(jarvis_maj.annonce()):
                break
        # Après une question (éteindre le PC ? une question de quiz ?), Jarvis attend plus longtemps la réponse
        delai = (DELAI_ECOUTE_DEMANDE if jarvis_commandes.confirmation_en_attente()
                 or (derniere_reponse or "").rstrip().endswith("?") else DELAI_SUITE)
        # Si le PC joue du son (vidéo, musique), Jarvis ne guette pas de suite : il prendrait ce son
        # pour une demande. Il écoute quand même s'il vient de poser une question.
        attend_reponse = (jarvis_commandes.confirmation_en_attente()
                          or (derniere_reponse or "").rstrip().endswith("?"))
        if not attend_reponse and son_pc():
            print("(Le PC joue du son : pas d'écoute de suite, redis « Jarvis ».)")
            break
        print("(J'écoute une éventuelle suite pendant", delai, "secondes...)")
        etat("ecoute")
        demande = ecouter_demande(recognizer, delai)
        if demande and not attend_reponse and son_pc():
            print("(Suite ignorée : le PC s'est mis à jouer du son. Entendu :", demande[:80], ")")
            break
    print("(Retour en veille : dis « Jarvis » pour me réveiller.)")
    etat("veille")


def attendre_micro():
    """Sans micro, Jarvis attend qu'on en branche un, au lieu de s'arrêter et d'être relancé toutes les minutes."""
    annonce = False
    while True:
        try:
            nom = sd.query_devices(kind="input")["name"]
            if annonce:
                print("Micro trouvé :", nom)
                sous_titre("")
            return
        except Exception:
            pass
        if not annonce:
            annonce = True
            print("Aucun micro trouvé : branche un micro, Jarvis démarrera tout seul (vérification toutes les 5 secondes).")
            etat("erreur")
            sous_titre("Aucun micro : branche un micro")
        time.sleep(5)
        try:                    # PortAudio ne voit un micro branché après coup qu'après avoir été relancé
            sd._terminate()
            sd._initialize()
        except Exception:
            pass


def main():
    global rec_stop, rec_coupure
    if AudioUtilities is not None:
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

    reparer_volumes()
    jarvis_voix.afficher = sous_titre          # en mode nuit, les réponses s'affichent sous le réacteur
    print("Chargement du modèle français...")
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    recognizer.SetWords(True)          # heure de chaque mot : sert à repérer la pause avant « Jarvis »
    rec_stop = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(MOTS_STOP + ["[unk]"], ensure_ascii=False))
    rec_coupure = KaldiRecognizer(model, SAMPLE_RATE)
    # Tout le reste se charge en arrière-plan : Jarvis écoute dès que Vosk est prêt
    jarvis_systeme.demarrer()
    jarvis_commandes.demarrer_rappels(lambda texte: point_pret.put((texte, "rappel")))
    threading.Thread(target=charger_whisper, daemon=True).start()
    threading.Thread(target=suivre_musique, daemon=True).start()
    threading.Thread(target=preparer, args=(PATIENCE + REMERCIEMENTS + ["Je n'ai rien entendu.", "Je n'ai pas bien compris, tu peux répéter ?",
              "Je n'ai pas compris, redis Jarvis quand tu veux.", "D'accord, on repart de zéro.",
              "Je prépare ton point du jour, je te le lis dès qu'il est prêt.",
              "D'accord, j'annule le point du jour.", "Aucun point du jour n'est en préparation.",
              "Avec plaisir.", "C'est fait.", "C'est retenu.", "C'est noté.",
              "Ton point du jour est déjà en préparation, je te le lis dès qu'il est prêt."],), daemon=True).start()
    threading.Thread(target=claude.demarrer, daemon=True).start()   # Claude prêt d'avance
    bilan = jarvis_maj.bilan_au_demarrage()       # après une mise à jour lancée par Jarvis : a-t-elle réussi ?
    if bilan:
        point_pret.put((bilan, None))
    jarvis_maj.verifier_en_arriere_plan()        # une version plus récente est-elle publiée sur GitHub ?

    heure = time.localtime().tm_hour
    if (POINT_DU_JOUR_AUTO and POINT_DU_JOUR_HEURES[0] <= heure < POINT_DU_JOUR_HEURES[1]
            and not point_du_jour_deja_fait()):
        threading.Thread(target=preparer_point_du_jour, args=(POINT_DU_JOUR_ATTENTE,),
                         daemon=True).start()

    attendre_micro()
    etat("veille")
    print(f"\nJARVIS version {VERSION} EST EN ÉCOUTE PERMANENTE (relié à Claude).")
    print("Dis : « Jarvis », puis ta demande.\n")

    tampon = bytearray()             # audio de la phrase en cours
    MAX_TAMPON = SAMPLE_RATE * 2 * 30  # 30 secondes au plus
    derniere_verif = 0.0
    fin_pause = 0.0
    en_pause = False
    cretes = collections.deque(maxlen=300)    # niveau du micro sur les 30 dernières secondes
    avance = collections.deque(maxlen=10)     # la seconde de son qui précède le réveil de l'écoute
    seuil_son = SEUIL_SON_MIN
    dernier_son = time.time()
    au_repos = False
    reveil_son_bloque = 0.0

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOC_AUDIO,
            latency="high",            # réserve de son plus grande : plus de « input overflow » quand le PC est occupé
            device=None,
            dtype="int16",
            channels=1,
            callback=audio_callback,
        ):
            while True:
                try:
                    data = audio_queue.get(timeout=MICRO_MUET)
                except queue.Empty:
                    raise RuntimeError("le micro n'envoie plus de son (débranché ?)")
                claude.entretenir()

                # Point du jour préparé en arrière-plan : on le lit maintenant
                if not point_pret.empty():
                    texte, erreur = point_pret.get()
                    if erreur == "rappel":         # un minuteur ou un rappel : alerte visuelle sur le réacteur
                        etat("rappel")
                        sous_titre(re.sub(r"^Rappel : |\.$", "", texte))
                    else:
                        etat("erreur" if erreur else "reponse")
                    baisser_son()
                    try:
                        bip(toujours=erreur == "rappel")        # un rappel sonne même en mode nuit
                        parler(texte, toujours=erreur == "rappel")
                    finally:
                        remonter_son()
                    preparer_ecoute(recognizer)
                    tampon.clear()
                    etat("veille")
                    continue

                # Pause pendant que Claude lit un message à voix haute
                maintenant = time.time()
                if maintenant - derniere_verif > 0.3:
                    derniere_verif = maintenant
                    if lecture_en_cours():
                        fin_pause = maintenant + MAINTIEN_PAUSE
                if maintenant < fin_pause:
                    if not en_pause:
                        en_pause = True
                        print("(Lecture à voix haute détectée : pause de l'écoute.)")
                        etat("pause")
                    recognizer.Reset()
                    tampon.clear()
                    continue
                if en_pause:
                    en_pause = False
                    print("(Fin de la lecture : reprise de l'écoute.)")
                    etat("veille")

                # Dans le silence, la reconnaissance vocale se repose
                if ECONOMIE_SILENCE:
                    crete = float(np.abs(np.frombuffer(data, dtype=np.int16)).max()) / 32768.0
                    cretes.append(crete)
                    if len(cretes) % 10 == 0:      # le seuil suit le bruit de fond de la pièce
                        seuil_son = min(SEUIL_SON_MAX, max(SEUIL_SON_MIN, 2 * float(np.percentile(cretes, 20))))
                    if crete >= seuil_son:
                        dernier_son = maintenant
                    if maintenant - dernier_son > REPOS_APRES:
                        if not au_repos:
                            au_repos = True
                            recognizer.Reset()
                            tampon.clear()
                        avance.append(data)
                        continue
                    if au_repos:
                        au_repos = False
                        data = b"".join(avance) + data
                        avance.clear()

                tampon.extend(data)
                if len(tampon) > MAX_TAMPON:
                    del tampon[:len(tampon) - MAX_TAMPON]
                if not recognizer.AcceptWaveform(data):
                    # Une vidéo ou de la musique joue : pas de silence à attendre, on guette « Jarvis »
                    # dans ce qui est entendu au fil de l'eau
                    if (REVEIL_PENDANT_SON and maintenant > reveil_son_bloque and son_pc_rapide()
                            and re.search(r"\bjarvis(\s+\S+)?$",
                                          json.loads(recognizer.PartialResult()).get("partial", ""))):
                        print("(« Jarvis » entendu pendant que le PC joue du son.)")
                        etat("ecoute")
                        baisser_son(insister=True)
                        try:
                            recognizer.Reset()
                            tampon.clear()
                            time.sleep(0.25)           # le temps que le son baisse vraiment
                            vider_audio()
                            bip(attendre=False)
                            demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True)
                            if demande:
                                conversation(demande, recognizer)
                            else:                      # rien de clair : sans doute la vidéo, on ne dit rien
                                print("(Rien d'entendu ensuite : retour en veille sans rien dire.)")
                                reveil_son_bloque = time.time() + PAUSE_APRES_FAUX_REVEIL
                                preparer_ecoute(recognizer)
                                etat("veille")
                        finally:
                            remonter_son()
                        tampon.clear()
                    continue

                resultat = json.loads(recognizer.Result())
                phrase = resultat.get("text", "").lower()
                audio_phrase = bytes(tampon)
                tampon.clear()
                if not phrase:
                    continue
                print("Entendu :", phrase)

                demande = chercher_reveil(resultat, audio_phrase)
                if demande is None:
                    continue
                etat("ecoute")
                baisser_son()
                if demande:
                    derniers_textes[:] = [demande]
                    # Retranscription précise de toute la phrase, sans le mot « Jarvis »
                    if not reveil_par_whisper and not sans_whisper(demande):
                        brut = transcrire(audio_phrase, phrase)
                        precise = retirer_nom(brut) if brut else None
                        demande = combiner(precise, demande) if precise else demande
                else:
                    # Le bip est joué sans attendre et l'écoute démarre tout de suite : si tu
                    # enchaînes juste après « Jarvis », le début de ta demande n'est plus perdu.
                    recognizer.Reset()
                    vider_audio()
                    bip(attendre=False)
                    demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True)

                try:
                    if demande:
                        conversation(demande, recognizer)
                    else:
                        speak("Je n'ai rien entendu.")
                        preparer_ecoute(recognizer)
                        etat("veille")
                finally:
                    remonter_son()
                tampon.clear()

    except KeyboardInterrupt:
        print("\nArrêt de Jarvis.")

    except Exception as error:
        etat("erreur")
        print("\nErreur :", error)


if __name__ == "__main__":
    main()
