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
import jarvis_sante
import jarvis_vigilance
import jarvis_extras
import jarvis_accueil
import jarvis_profils
import jarvis_locuteur
import jarvis_famille
import jarvis_foyer
import jarvis_infos
import jarvis_personnalite
import jarvis_taches
import jarvis_motappel
import jarvis_agenda
import jarvis_sources
import jarvis_tablette
from jarvis_commandes import commande_instantanee, sans_whisper  # heure, météo, volume...
try:
    import jarvis_rapports                 # rapports pour améliorer Jarvis (avec l'accord de l'utilisateur)
except Exception as _erreur_rapports:
    jarvis_rapports = None
    print("Rapports indisponibles :", _erreur_rapports)


def rapport(nom, *args, **kwargs):
    """Note un événement pour les rapports, sans jamais gêner Jarvis si quelque chose coince."""
    try:
        if jarvis_rapports is not None:
            getattr(jarvis_rapports, nom)(*args, **kwargs)
    except Exception as erreur_rapport:
        print("(Rapports :", nom, type(erreur_rapport).__name__, ")")

VERSION = "1.65"              # numéro de version de Jarvis (même numéro que sur GitHub)

# ===== Réglages =====
MODEL_PATH = jarvis_config.chemin("vosk-model-small-fr-0.22")
SAMPLE_RATE = 16000
# Économie : dans le silence, la reconnaissance vocale se repose (elle consomme autant sur du
# silence que sur de la parole). Elle repart au premier son, avec les 0,8 s qui le précèdent.
ECONOMIE_SILENCE = True
MICRO_MUET = 10               # secondes sans aucun son du micro avant de relancer Jarvis (micro débranché)
MICRO_MUET_DEMARRAGE = 90     # au lancement, tant qu'aucun son n'est arrivé : Windows peut être occupé, on attend plus longtemps
MICRO_ESSAIS = 3                # essais pour retrouver un micro qui se tait, avant d'afficher « Aucun micro détecté »
MICRO_ESSAI_ATTENTE = 4         # secondes d'attente d'un son à chaque essai
MICRO_MESSAGE_DUREE = 120       # le message « Aucun micro détecté » reste affiché environ 2 minutes
MICRO_MESSAGE = "Aucun micro détecté. Branche-en un, ou écris-moi ici : je réponds quand même."
MICRO_ABANDON = 600             # sans micro depuis 10 minutes (et rien d'écrit depuis 1 minute) : Jarvis se relance
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
SILENCE_FIN_LIAISON = 1.8     # ... quand la phrase s'arrête sur « de », « sur », « les »… : la suite arrive
                              # (vu sur un portable : une recherche YouTube coupée en deux demandes)
_MOT_DE_LIAISON = re.compile(r"(?<!-)\b(?:de|du|des|d|le|la|les|l|un|une|sur|pour|avec|et|à|a|au|aux|en|dans|par|qui|que|"
                             r"mets|cherche|cherches|recherche|recherches|trouve|montre|affiche|ouvre|lance|joue|euh|heu)\W*$")
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
WHISPER_TEMPERATURES = (0.0, 0.4)   # deux essais au plus quand la voix est peu claire
# Mode léger : sur un PC lent, une seule hypothèse et un seul essai. Mesuré le 21/11/2026 sur un petit portable :
# 14 à 17 s par phrase avec les réglages normaux (2 à 4 s sur un PC de bureau récent). Jarvis le décide tout seul
# d'après ses trois dernières retranscriptions, et s'en souvient (mode_leger.json, à effacer pour revenir au normal).
MODE_LEGER_FICHIER = jarvis_config.chemin("mode_leger.json")
WHISPER_LENT = 7.0                  # secondes de calcul (médiane des 3 dernières phrases) au-delà : mode léger
WHISPER_TRES_LENT = 10.0            # deux phrases de suite au-delà : mode léger sans attendre la troisième
_durees_whisper = collections.deque(maxlen=3)


def _appliquer_mode_leger():
    global WHISPER_FAISCEAU, WHISPER_TEMPERATURES
    WHISPER_FAISCEAU, WHISPER_TEMPERATURES = 1, (0.0,)
    jarvis_commandes.MODE_LEGER = True    # les commandes connues sont prises telles que Vosk les a entendues


def etat_mode_leger():
    """Le contenu de mode_leger.json : {"choix": "auto" | "toujours" | "jamais", "actif": ..., "mesures": [...]}."""
    try:
        with open(MODE_LEGER_FICHIER, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire_mode_leger(**changements):
    """Met à jour mode_leger.json sans perdre le reste (le choix fait dans les réglages, en particulier)."""
    d = etat_mode_leger()
    d.update(changements)
    try:
        with open(MODE_LEGER_FICHIER, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def noter_duree_whisper(calcul):
    """Après chaque retranscription sur le PC : si ce PC est nettement lent, Jarvis passe en mode léger
    (sauf si l'utilisateur a choisi « jamais » dans les réglages)."""
    if WHISPER_FAISCEAU == 1 or etat_mode_leger().get("choix") == "jamais":
        return
    _durees_whisper.append(calcul)
    if not pc_lent(list(_durees_whisper)):
        # les mesures sont gardées d'un lancement à l'autre : sur un petit PC, on parle peu à Jarvis à chaque fois
        _ecrire_mode_leger(actif=False, mesures=[round(d, 1) for d in _durees_whisper])
        return
    _appliquer_mode_leger()
    _ecrire_mode_leger(actif=True, depuis=time.strftime("%d/%m/%Y %H:%M"),
                       secondes=[round(d, 1) for d in _durees_whisper])
    print(f"Mode léger activé : ce PC met environ {sorted(_durees_whisper)[len(_durees_whisper) // 2]:.0f} s à "
          "comprendre une phrase. Jarvis compare désormais une seule hypothèse : les réponses seront nettement "
          "plus rapides.")


def pc_lent(mesures):
    """Vrai si les dernières retranscriptions montrent un PC nettement lent : la médiane des trois dernières
    dépasse 7 s, ou les deux dernières dépassent toutes les deux 10 s (inutile d'attendre une troisième)."""
    mesures = [float(m) for m in mesures][-3:]
    if len(mesures) >= 3 and sorted(mesures)[1] > WHISPER_LENT:
        return True
    return len(mesures) >= 2 and min(mesures[-2:]) > WHISPER_TRES_LENT


try:                                    # décidé lors d'un lancement précédent, ou choisi dans les réglages
    _etat_leger = etat_mode_leger()
    _choix_leger = _etat_leger.get("choix", "auto")
    if _choix_leger == "toujours" or (_choix_leger != "jamais" and _etat_leger.get("actif")):
        _appliquer_mode_leger()
        print("Mode léger (PC lent) : Whisper compare une seule hypothèse."
              + (" (choisi dans les réglages)" if _choix_leger == "toujours" else ""))
    elif _choix_leger == "jamais":
        print("Mode léger : désactivé dans les réglages.")
    else:                               # pas encore décidé : les mesures des lancements précédents comptent
        _durees_whisper.extend(float(m) for m in (_etat_leger.get("mesures") or [])[-3:]
                               if isinstance(m, (int, float)) and 0 < m < 600)
except (OSError, ValueError, TypeError):
    pass
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
               + "".join(mot + ", " for mot in jarvis_config.VOCABULAIRE) + "GTA 6, PS5, YouTube Kids, Netflix, Spotify, Chrome, Claude"
               + "".join(", " + nom for nom in jarvis_commandes.noms_applications(10)
                         if nom not in ("Chrome", "Claude")) + ".")


def _vocabulaire():
    """Le vocabulaire donné à Whisper, avec les prénoms des profils du foyer (à la fin : c'est la partie qu'il
    garde toujours) et « apprends ma voix »."""
    try:
        prenoms = [p.get("prenom", "") for p in jarvis_profils._lire().values() if p.get("prenom")]
    except Exception:
        prenoms = []
    if not prenoms:
        return VOCABULAIRE
    return VOCABULAIRE + " " + ", ".join("c'est " + p for p in prenoms) + ", apprends ma voix."


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
PRESQUE_JARVIS = ("j'ai envie", "j'envie", "envie", "je vis", "genre vie", "j'en vie", "gervais", "jervis", "j'arrive", "jarre", "djar",
                  "charlie", "j'ai vis", "jadis", "jarvi")     # (voix d'enfant ou aiguë : « charlie »)
REVEIL_DIRECT = True          # « Jarvis » seul mal transcrit : le détecteur du mot d'appel confirme à la place de Whisper
SEUIL_REVEIL_DIRECT = 0.7     # note minimale du détecteur pour ce réveil direct (plus stricte que son seuil habituel)

# Les dernières demandes sont gardées (son + textes compris) pour pouvoir analyser les erreurs d'écoute
DOSSIER_ENREGISTREMENTS = jarvis_config.chemin("enregistrements")
NB_ENREGISTREMENTS = 1000     # les 1000 dernières demandes (environ 170 Mo) : de quoi réentraîner le mot « Jarvis »
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
    "Ne crée jamais toi-même de tâche planifiée, de service, de règle de démarrage ou de rappel système "
    "(schtasks, msg, Register-ScheduledTask...), et ne touche pas aux réglages de Windows : les rappels, "
    "minuteurs et réveils sont gérés par Jarvis. Si une demande de rappel t'arrive, c'est qu'elle a été mal "
    "entendue : redis-la clairement en proposant la phrase « rappelle-moi à 18 h de … ». "
    "De même, le calendrier familial, les messages, la liste de courses, les notes, les profils et la mémoire "
    "sont tenus par Jarvis : tu ne peux pas les modifier, alors ne dis jamais que tu as ajouté, annulé ou changé "
    "quelque chose dedans ; propose plutôt la bonne phrase (« annule la piscine de Léo », « ajoute du lait à la liste »). "
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
    "Si on te demande une anecdote, un fait étonnant ou « raconte-moi un truc », raconte une anecdote "
    "vraie et vérifiable, surprenante, en deux ou trois phrases, sur un sujet chaque fois différent "
    "(sciences, histoire, animaux, espace, inventions...) ; n'invente jamais. "
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


demandes_ecrites = queue.Queue()     # demandes tapées dans la fenêtre de discussion, au-dessus du réacteur
_demande_ecrite = False              # vrai pendant le traitement d'une demande écrite (personne n'a parlé)


def ecrire(texte):
    """Une demande tapée au clavier dans la fenêtre de discussion : traitée comme une demande dite."""
    texte = " ".join(str(texte or "").split())
    if texte:
        demandes_ecrites.put(texte)


def sous_titre(texte, en_direct=False, reponse=False):
    """Affiche dans la fenêtre de discussion ce que Jarvis a compris (en direct : les mots au fil de
    l'écoute), ou sa réponse (reponse=True), qui remplace la demande."""
    try:
        afficher_texte(texte, en_direct, reponse)
        return
    except TypeError:
        pass
    except Exception:
        return
    try:
        afficher_texte(texte, en_direct)
    except TypeError:
        try:
            afficher_texte(texte)
        except Exception:
            pass
    except Exception:
        pass


derniere_activite = time.time()   # dernier moment où Jarvis n'était pas en veille (mise à jour forcée : 1 min de calme)


def etat(nom):
    global derniere_activite
    if nom != "veille":
        derniere_activite = time.time()
    try:
        afficher_etat(nom)
    except Exception:
        pass


derniere_erreur = False
reveil_par_whisper = False
derniere_reponse = ""         # pour « Jarvis, répète »
niveau_micro = 0.0            # volume du micro à cet instant (0 à 1), lu par le réacteur
micro_coupe = False           # « coupe le micro » : Jarvis n'écoute plus (le réacteur affiche un micro barré)

def regler_micro(coupe):
    """Coupe ou rallume le micro et le retient : après un arrêt ou un redémarrage, il reste comme on l'a laissé."""
    global micro_coupe
    micro_coupe = bool(coupe)
    try:
        import jarvis_reglages_ui
        jarvis_reglages_ui.regler("micro_coupe", micro_coupe)
    except Exception as erreur:
        print("Micro : réglage non enregistré :", erreur)

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
verrou_whisper = threading.Lock()     # Whisper sert aussi à la tablette : une retranscription à la fois


# ---------- Audio ----------

spectre_micro = None     # spectre du micro à cet instant (16 bandes de 0 à 1), lu par le réacteur
_crete_spectre = 4.0     # plus fort niveau vu récemment : le spectre reste lisible même avec un micro faible


sons_perdus = 0         # morceaux de son perdus par le micro (« input overflow ») pendant la demande en cours
duree_whisper = 0.0     # temps pris par Whisper pour la dernière demande


def _ouvrir_micro():
    """Ouvre le micro. Sur un PC lent (mode léger), la réserve de son demandée à Windows est plus grande (une
    demi-seconde) : le micro perd moins de son (« input overflow ») quand le processeur est occupé. Si Windows
    refuse cette réserve, on revient au réglage habituel."""
    essais = ((0.5,) if WHISPER_FAISCEAU == 1 else ()) + ("high",)
    derniere = None
    for latence in essais:
        try:
            return sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOC_AUDIO, latency=latence, device=None,
                                     dtype="int16", channels=1, callback=audio_callback)
        except Exception as erreur:
            derniere = erreur
            if latence != "high":
                print("(Micro : réserve de son agrandie refusée, réglage habituel :", type(erreur).__name__, ")")
    raise derniere


def audio_callback(indata, frames, time_info, status):
    global niveau_micro, spectre_micro, _crete_spectre
    global sons_perdus
    if status:
        print("Audio :", status, file=sys.stderr)
        if status.input_overflow:
            sons_perdus += 1
    # Le moins de travail possible ici : si ce rappel tarde (PC occupé au démarrage), le micro perd du son
    # (« input overflow », vu sur un petit portable). Le niveau et le spectre du réacteur sont calculés à côté.
    octets = bytes(indata)
    audio_queue.put(octets)
    _pour_spectre[0] = octets


_pour_spectre = [b""]


def _calculer_spectre():
    """Niveau et spectre du micro pour l'animation du réacteur, dix fois par seconde, hors du rappel du micro."""
    global niveau_micro, spectre_micro, _crete_spectre
    while True:
        time.sleep(0.1)
        octets, _pour_spectre[0] = _pour_spectre[0], b""
        if not octets:
            continue
        try:
            bloc = np.frombuffer(octets, dtype=np.int16).astype(np.float32) / 32768.0
            niveau_micro = float(np.abs(bloc).max())
            bandes = jarvis_voix.bandes_spectre(bloc[None, :], SAMPLE_RATE)[0]
            _crete_spectre = max(_crete_spectre * 0.97, float(bandes.max()), 4.0)
            spectre_micro = np.clip((np.sqrt(bandes / _crete_spectre) - 0.15) / 0.85, 0, 1)
        except Exception:
            pass


threading.Thread(target=_calculer_spectre, daemon=True).start()


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
_volumes_baisses = []        # (réglage de volume, niveau d'origine, nom, processus) des applications baissées
_a_remettre = {}             # nom -> niveau d'origine : application arrêtée pendant qu'elle était baissée.
                             # Windows retient son volume baissé : on le lui rend dès qu'elle rejoue du son.


def _sessions_son():
    """Les applications qui ont une sortie son, sauf Jarvis lui-même et celles mises en pause autrement."""
    sessions = []
    for session in AudioUtilities.GetAllSessions():
        try:
            if (session.Process and session.Process.pid != os.getpid()
                    and session.Process.name().lower() not in PROGRAMMES_A_IGNORER):
                sessions.append(session)
                nom = session.Process.name().lower()
                if nom in _a_remettre and not _volumes_baisses:
                    session.SimpleAudioVolume.SetMasterVolume(float(_a_remettre.pop(nom)), None)
                    print(f"(Son de {nom} remis à son niveau d'avant.)")
                    _noter_a_remettre()
        except Exception:
            pass
    return sessions


def _noter_a_remettre():
    """Garde sur le disque les volumes à rendre (au cas où Jarvis serait arrêté entre-temps)."""
    try:
        if _a_remettre:
            with open(FICHIER_VOLUMES, "w", encoding="utf-8") as f:
                json.dump(_a_remettre, f)
        elif os.path.exists(FICHIER_VOLUMES):
            os.remove(FICHIER_VOLUMES)
    except OSError:
        pass


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
                _volumes_baisses.append((volume, origine, session.Process.name().lower(), session.Process))
                origines[session.Process.name().lower()] = origine
        if origines:
            # noté sur le disque : si Jarvis est arrêté à ce moment-là, le son sera remis au prochain démarrage
            with open(FICHIER_VOLUMES, "w", encoding="utf-8") as f:
                json.dump(dict(_a_remettre, **origines), f)
            print("(Son du PC baissé pendant la conversation :", ", ".join(origines) + ".)")
    except Exception as erreur:
        print("Baisse du son impossible :", erreur)


def remonter_son():
    """Remet le son des applications comme il était."""
    if not _volumes_baisses:
        return
    for volume, origine, nom, processus in _volumes_baisses:
        try:
            volume.SetMasterVolume(origine, None)
        except Exception:
            pass
        try:
            if not processus.is_running():      # arrêtée pendant la conversation : Windows garde le volume baissé
                _a_remettre[nom] = origine
        except Exception:
            pass
    _volumes_baisses.clear()
    _noter_a_remettre()


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
        if isinstance(origines, dict):
            _a_remettre.update({str(n): float(v) for n, v in origines.items()})
        _sessions_son()                          # rend tout de suite le son aux applications ouvertes
        _noter_a_remettre()                      # les autres le retrouveront dès qu'elles rejoueront du son
        print("(Son remis à son niveau après un arrêt de Jarvis en pleine conversation.)")
    except Exception as erreur:
        print("Remise du son impossible :", erreur)


# ---------- Reconnaissance précise (Whisper) ----------

LANCE_A = time.time()          # pour noter dans le journal le temps de démarrage (« prêt en … s »)


def _fichier_bloque(erreur):
    """Fichier (.dll ou .pyd) que Windows a refusé de charger, ou ''. Python le donne pour un module (« path ») ;
    sinon, on le lit là où l'erreur est née (le dernier appel de la trace), jamais plus haut."""
    try:
        chemin = getattr(erreur, "path", None) or getattr(erreur, "filename", None)
        if isinstance(chemin, str) and chemin:
            return chemin
        t = erreur.__traceback__
        while t is not None and t.tb_next is not None:
            t = t.tb_next
        if t is not None:
            for v in list(t.tb_frame.f_locals.values()):
                if isinstance(v, str) and v.lower().endswith((".dll", ".pyd")):
                    return v
    except Exception:
        pass
    return ""


def _bloque_par_windows(erreur):
    """Vrai si Windows (Contrôle intelligent des applications) a refusé un fichier : numéro 4551 ou texte de l'erreur."""
    texte = str(erreur).lower().replace("\u2019", "'")
    return (getattr(erreur, "winerror", None) == 4551 or "4551" in texte
            or "contrôle d'application" in texte or "application control" in texte)


def charger_whisper():
    global whisper
    try:
        from faster_whisper import WhisperModel
        whisper = WhisperModel(WHISPER_MODELE, device="cpu", compute_type="int8",
                               download_root=WHISPER_DOSSIER, cpu_threads=WHISPER_FILS)
        print(f"Reconnaissance précise (Whisper) prête. Jarvis est prêt en {time.time() - LANCE_A:.0f} s "
              f"(processeur : {os.cpu_count()} fils de calcul{', mode léger' if WHISPER_FAISCEAU == 1 else ''}).")
    except Exception as erreur:
        whisper = None
        print("Whisper indisponible, Vosk seul sera utilisé :", erreur)
        fichier = _fichier_bloque(erreur)
        if _bloque_par_windows(erreur):       # Contrôle intelligent des applications : un fichier non reconnu est refusé
            print("(Windows bloque un fichier de la reconnaissance précise" + (" : " + fichier if fichier else "") + ".)")
        elif fichier:
            print("(Fichier en cause : " + fichier + ".)")


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


def _recopie_du_vocabulaire(texte, texte_vosk):
    """Vrai si Whisper a recopié un morceau de son vocabulaire (« c'est Paul, apprends ma voix ») au lieu
    d'écouter : ça arrive sur le son d'une vidéo ou de la musique. Vosk, qui n'a pas ce vocabulaire,
    n'a alors rien entendu de tel."""
    mots = _normaliser(texte).split()
    if len(mots) < 3:
        return False
    vocab = " ".join(_normaliser(_vocabulaire()).split())
    vosk = set(_normaliser(texte_vosk or "").split())
    if len(set(mots) & vosk) / len(set(mots)) >= 0.3:
        return False                              # les deux ont entendu à peu près la même chose
    # un passage de 3 mots du vocabulaire, absent de ce qu'a entendu Vosk
    for i in range(len(mots) - 2):
        bout = " ".join(mots[i:i + 3])
        if bout in vocab and not set(mots[i:i + 3]) <= vosk:
            if re.search(r"\bapprends ma voix\b|\bc est \w+\b", bout):
                return True                       # seulement ce qui change de profil ou apprend une voix
    return False


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


_BAVARDAGE = re.compile(r"^\W*(?:bon|ok|okay|alors|euh|voilà|voila|donc|ah|oh|bah|ben)\b[\s,.]+(?:là\b[\s,.]*)?"
                        r".*\b(?:je suis|j'ai|je vais|je viens|on va|on est|c'était|il faut que je)\b", re.I)


def _bavardage(texte):
    """Une phrase entendue pendant les secondes de « suite » qui ressemble à une conversation entre personnes
    (« Bon, là, je suis repassé sur mon PC… ») plutôt qu'à une demande : Jarvis ne la prend pas."""
    t = (texte or "").replace("’", "'")
    return bool(_BAVARDAGE.search(t)) and "?" not in t


def _preparer_plus_tard(phrases):
    """Les phrases fréquentes sont fabriquées d'avance. Au tout premier lancement (rien encore sur le disque), on
    attend une minute : Whisper se prépare au même moment, et sur un petit PC tout faire ensemble le sature."""
    try:
        deja = len(os.listdir(jarvis_voix.DOSSIER_CACHE))
    except OSError:
        deja = 0
    if deja < len(phrases) // 2:
        time.sleep(60)
    preparer(phrases)


def transcrire(octets, texte_vosk, bip_au_debut=False):
    """Retranscrit l'audio avec Whisper. En cas de souci, garde le texte de Vosk."""
    global duree_whisper, sons_perdus
    if whisper is None or not octets or not texte_vosk:
        return texte_vosk
    _enregistrer_diagnostic(octets)
    try:
        jarvis_locuteur.analyser(octets, texte_vosk)   # qui parle ? (calculé pendant la retranscription)
    except Exception as erreur_voix:
        print("Empreinte de voix :", erreur_voix)
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
        with verrou_whisper:
            # Deux essais au plus quand la voix est peu claire (au lieu de six) : mesuré le 21/11 sur 24 vraies
            # demandes, le plus long passe de 12,7 s à 7,4 s, et 23 retranscriptions sur 24 restent identiques
            debut_calcul = time.time()
            segments, _ = whisper.transcribe(audio, language="fr", beam_size=WHISPER_FAISCEAU,
                                             initial_prompt=_vocabulaire(), temperature=WHISPER_TEMPERATURES)
            texte = " ".join(s.text for s in segments).strip()
            calcul = time.time() - debut_calcul
        duree_whisper = time.time() - debut_whisper
        noter_duree_whisper(calcul)
    except Exception as erreur:
        print("Erreur Whisper :", erreur)
        return texte_vosk
    # Hallucinations connues de Whisper sur du bruit
    if not texte or _HALLUCINATION.search(texte):
        return texte_vosk
    if _repetitif(texte):
        print("Whisper a inventé une phrase en boucle (bruit) : demande ignorée. Vosk :", texte_vosk)
        return None
    if _recopie_du_vocabulaire(texte, texte_vosk):
        print("Whisper a recopié son vocabulaire (bruit) : je garde ce qu'a entendu Vosk :", texte_vosk,
              "| Whisper :", texte)
        return texte_vosk
    print("Whisper :", texte, "| Vosk :", texte_vosk)
    if sons_perdus:
        print(f"(Attention : {sons_perdus} morceau(x) de son perdu(s) par le micro pendant cette demande.)")
        sons_perdus = 0
    garder_enregistrement(octets, texte, texte_vosk)
    return texte


# Phrases que Whisper invente sur du silence ou du bruit (elles viennent des vidéos qui l'ont entraîné) :
# personne ne les dit à Jarvis. Quand il en sort une, on garde ce qu'a entendu la première écoute (Vosk).
_HALLUCINATION = re.compile(
    r"amara|sous-?titr|soustitreur|merci d'avoir (?:regard|suivi|visionn|[ée]cout)|merci (?:à tous )?pour (?:votre|ton) (?:attention|[ée]coute|visionnage)|"
    r"abonnez[- ]vous|abonne[- ]toi|n'oublie(?:z)? pas de (?:vous |t')abonner|(?:à|a) bient[ôo]t (?:pour|dans) une (?:prochaine|nouvelle|autre) vid[ée]o|"
    r"(?:c'est|c'était) la fin de (?:cette|la) vid[ée]o|laissez (?:un|vos) (?:commentaires?|pouce)|pouce bleu|"
    r"activez la cloche|radio-canada|merci d'avoir regard[ée] cette vid[ée]o", re.I)


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
    # Début qui ressemble à « Jarvis » mal compris, ou détecteur du mot d'appel (entraîné exprès, voir
    # jarvis_motappel.py) qui l'a entendu : Whisper confirme avant de réveiller Jarvis
    presque = phrase.startswith(PRESQUE_JARVIS)
    # « Jarvis » dit seul et mal transcrit (« j'ai envie », « j'arrive »...) : si le détecteur du mot d'appel l'a
    # nettement entendu lui aussi, Jarvis se réveille tout de suite, sans attendre Whisper (2 à 3 secondes de gagnées).
    # Mesuré sur 300 enregistrements : 109 « Jarvis » sur 112 reconnus ainsi, aucune fausse alerte ; les autres
    # passent par Whisper comme avant.
    if REVEIL_DIRECT and phrase.strip() in PRESQUE_JARVIS:
        note = jarvis_motappel.note_debut(audio)
        if note >= SEUIL_REVEIL_DIRECT:
            print(f"(Réveil confirmé par le détecteur du mot d'appel : note {note:.2f}, sans attendre Whisper.)")
            return ""
    if whisper is not None and not presque:
        note = jarvis_motappel.note_debut(audio)
        if note >= jarvis_motappel.SEUIL:
            print(f"(Mot d'appel entendu par le détecteur : note {note:.2f}, Vosk a compris « {phrase} ».)")
            presque = True
    if whisper is not None and presque:
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
            en_cours = " ".join(morceaux + ([partiel] if partiel else []))
            if (en_cours and maintenant - dernier_son <= max(silence_fin, SILENCE_FIN_LIAISON)
                    and _MOT_DE_LIAISON.search(en_cours)):
                pass                   # « cherche sur YouTube les… » : on laisse le temps de finir la phrase
            elif morceaux or partiel:
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
    if texte_vosk:
        jarvis_voix.bip_fin_ecoute()           # « je t'ai entendu » : un son léger, différent du bip de réveil
    if texte_vosk and sans_whisper(texte_vosk):
        derniers_textes[:] = [texte_vosk]      # commande simple : pas besoin de Whisper
        try:
            jarvis_locuteur.analyser(bytes(octets), texte_vosk)
        except Exception as erreur_voix:
            print("Empreinte de voix :", erreur_voix)
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
    outils = None             # outils de Claude (None : ceux de Jarvis). La tablette en a moins.
    avec_memoire = True       # la mémoire de Jarvis accompagne les demandes (jamais celles de la tablette)
    nom = ""                  # pour le journal

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
        # tutoiement / vouvoiement : le choix de la personne (jarvis_personnalite) passe avant celui de l'accueil
        accueil = jarvis_accueil.consigne() if jarvis_personnalite.vouvoiement() is None else ""
        return (CONSIGNES + accueil + jarvis_profils.consigne() + jarvis_personnalite.consigne()
                + ("\n\n" + memoire if memoire else ""))

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
             *OPTIONS_LEGERES, "--tools", self.outils or OUTILS],
            cwd=DOSSIER_JARVIS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._lire, args=(self.proc.stdout, self.sorties),
                         daemon=True).start()
        threading.Thread(target=self._lire, args=(self.proc.stderr, None),
                         daemon=True).start()
        self.dernier_usage = time.time()
        self.utilise = False
        print("Claude prêt en continu (modèle", MODELE + (", " + self.nom if self.nom else "") + ").")

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
                return message_sans_claude(), True
            self.utilise = True
            if self.avec_memoire:
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
                        return message_limite(), True
                    return "Claude a rencontré un problème avec cette demande.", True
                return reponse, False


SANS_CLAUDE = ("Pour cette demande, j'ai besoin de Claude, qui n'est pas installé sur ce PC. "
               "Je réponds quand même aux commandes immédiates : l'heure, la météo, les minuteurs, les fenêtres, l'ouverture des applications. "
               "Pour ajouter Claude, ouvre mes Réglages, onglet Claude, et clique sur Installer Claude, puis sur Connecter mon compte. "
               "Tu peux aussi utiliser un autre assistant, comme Gemini, Mistral ou ChatGPT : onglet Assistants, c'est expliqué pas à pas.")
_derniers_messages = {}


def _une_fois_par_heure(cle):
    """True si ce message complet n'a pas été dit depuis une heure (sinon on donne la version courte)."""
    maintenant = time.time()
    if maintenant - _derniers_messages.get(cle, 0) > 3600:
        _derniers_messages[cle] = maintenant
        return True
    return False


def message_limite():
    """Limite d'utilisation de Claude atteinte : message complet une fois par heure, ensuite court."""
    if _une_fois_par_heure("limite"):
        return ("La limite d'utilisation de Claude est atteinte pour le moment. Je réponds quand "
                "même tout de suite à l'heure, la météo, les minuteurs, la musique, les fenêtres et l'ouverture des "
                "applications.")
    return "Claude est toujours à sa limite d'utilisation, je ne peux pas répondre à cette demande."


def message_sans_claude():
    """Claude absent : explication complète une fois par heure, ensuite court."""
    if _une_fois_par_heure("sans_claude"):
        return SANS_CLAUDE
    return "Cette demande a besoin de Claude, que je n'ai pas sur ce PC."


# --- Secours (BÊTA) : un autre assistant, seulement si Claude est absent, déconnecté ou à sa limite -------------
_CLAUDE_INDISPONIBLE = ("Claude a rencontré un problème avec cette demande.", "Je n'arrive pas à joindre Claude.",
                        "Cette demande a besoin de Claude, que je n'ai pas sur ce PC.",
                        "Claude est toujours à sa limite d'utilisation, je ne peux pas répondre à cette demande.")


def claude_indisponible(reponse):
    """Vrai si la réponse est l'un des messages « Claude n'est pas là / pas relié / à sa limite »."""
    r = str(reponse or "")
    return r in _CLAUDE_INDISPONIBLE or r == SANS_CLAUDE or r.startswith("La limite d'utilisation de Claude est atteinte")


def demander_avec_secours(message, demande, longue=False):
    """Claude d'abord, toujours. Si Claude est indisponible (absent, pas relié, à sa limite) ET que l'utilisateur a
    branché un autre assistant (onglet « Assistants », avec son accord), la question seule (sans les notes internes de
    Jarvis) part vers cet assistant : il sert aussi d'assistant unique pour ceux qui n'ont pas Claude du tout.
    Jamais en mode enfant ni en mode invité. Renvoie (réponse, erreur), comme claude.demander."""
    try:                                   # essai oral : on fait comme si Claude était à sa limite (voir jarvis_assistants)
        import jarvis_assistants as _essai
        if _essai.essai_actif() and not longue:
            locale = _essai.reponse_action(demande, os.path.exists(CLAUDE_EXE))
            if locale:                                 # ouvrir une application : jamais pour l'assistant de secours
                return locale, False
            dit = _essai.tour_de_essai(demande)
            if dit:
                return dit, False
    except Exception as erreur_essai:
        print("Essai assistants :", erreur_essai)
    reponse, erreur = claude.demander(message)
    if not erreur or not claude_indisponible(reponse):
        return reponse, erreur
    try:
        import jarvis_assistants
        if not jarvis_assistants.utilisable_maintenant():
            return reponse, erreur
        if not longue:                                 # ouvrir une application : l'assistant de secours n'a pas accès au PC
            locale = jarvis_assistants.reponse_action(demande, os.path.exists(CLAUDE_EXE))
            if locale:
                print("Secours : réponse locale (ouverture d'application non trouvée)")
                return locale, False
        texte, nom, _ = (jarvis_assistants.demander(demande, True) if longue
                         else jarvis_assistants.demander(demande))
        if texte:
            print("Secours :", nom)
            if os.path.exists(CLAUDE_EXE):         # Claude est là mais indisponible : on le dit ; sinon, pas de bavardage
                return f"Claude n'est pas disponible, j'ai demandé à {nom}. {texte}", False
            return texte, False
    except Exception as erreur_secours:
        print("Secours :", erreur_secours)
    return reponse, erreur


claude = ClaudeContinu()


def oublier_conversation():
    """Repart de zéro : Claude est relancé (en arrière-plan)."""
    try:
        import jarvis_assistants
        jarvis_assistants.oublier()
    except Exception:
        pass
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
            return message_limite(), True
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
# Pendant une longue attente, Jarvis occupe l'utilisateur : une première phrase (adaptée au sujet), puis de temps en temps
# une autre tant que Claude n'a pas fini. Rien n'est dit si la réponse arrive vite.
PATIENCE_PAR_SUJET = [
    (r"\b(?:écran|ecran|ce que tu vois|copié|copie|presse[- ]papiers?)\b",
     ["Je regarde ton écran.", "Je jette un œil à l'écran.", "Je regarde ce qu'il y a à l'écran."]),
    (r"\b(?:cherche|recherche|trouve|actualités?|infos?|nouvelles|internet|prix|combien (?:coûte|vaut))\b",
     ["Je cherche sur Internet.", "Je regarde ce que je trouve.", "Je fais une petite recherche."]),
    (r"\b(?:traduis|traduire|corrige|corriger|résume|résumer|rédige|rédiger|écris|écrire)\b",
     ["Je m'y mets.", "Je rédige ça.", "Je m'en occupe, ça arrive."]),
]
PATIENCE_SUITE = ["Ça prend un peu plus de temps que d'habitude.", "Je suis toujours dessus, merci de patienter.",
                  "Encore un petit instant, j'y suis presque."]
DELAI_ENTRE_PATIENCES = 10    # secondes entre deux phrases d'attente (trois au plus après la première)
DUREE_TACHE_LONGUE = 8        # secondes : au-delà, un petit son signale que la réponse est prête
FICHIER_SALUTATION = jarvis_config.chemin("salutation.date")
fete_demandee = None          # (moment, "anniversaire") : le réacteur joue une petite animation
_derniere_phrase = {}


def phrase_patience(minuscules):
    """La première phrase d'attente : adaptée au sujet si on le reconnaît, sinon une phrase générale."""
    for motif, phrases in PATIENCE_PAR_SUJET:
        if re.search(motif, minuscules):
            return phrase_variee(phrases)
    return phrase_variee(PATIENCE)


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
    # la date de config.json est celle du profil principal ; les autres profils ont la leur dans leur mémoire
    texte = str(jarvis_config._lu.get("anniversaire") or "") if jarvis_profils.actif() is None else ""
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
_MOT_STOP_LIBRE = re.compile(r"\b(?:stop|stoppe|arr[êe]te|tais[- ]toi|tait toi|tais toi|chut)\b")
_stop_libre = [0.0]           # dernier moment où la reconnaissance complète a entendu un mot d'arrêt


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
        entendu = ""
        if rec_coupure is not None:
            if rec_coupure.AcceptWaveform(data):
                entendu = json.loads(rec_coupure.Result()).get("text", "")
            else:
                entendu = json.loads(rec_coupure.PartialResult()).get("partial", "")
            if _MOT_STOP_LIBRE.search(entendu):
                _stop_libre[0] = time.time()
            if not _jarvis_dans_texte and re.search(r"\bjarvis\b", entendu):
                print("Interruption : « Jarvis » (nouvelle demande)")
                coupe_par_jarvis = True
                return True
        if rec_stop.AcceptWaveform(data):
            texte = json.loads(rec_stop.Result()).get("text", "")
            if texte and texte in MOTS_STOP:
                # Avec sa liste réduite, Vosk ramène presque n'importe quel bruit à « stop » ou « tais-toi »
                # (essais du 18/11/2026 : Jarvis coupé en pleine réponse sans que personne ne le dise).
                # Le mot doit aussi être entendu par la reconnaissance complète, dans les 3 dernières secondes.
                if rec_coupure is None or time.time() - _stop_libre[0] < 3:
                    print("Interruption :", texte)
                    return True
                print("(« " + texte + " » cru entendu, non confirmé : je continue.)")


def parler(texte, toujours=False):
    """Parle en restant à l'écoute du mot « stop ». Renvoie True si interrompu.
    toujours=True : même en mode nuit (rappels et réveil)."""
    global coupe_par_jarvis, _jarvis_dans_texte
    if rec_stop is not None:
        rec_stop.Reset()
    if rec_coupure is not None:
        rec_coupure.Reset()
    _stop_libre[0] = 0.0
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
    rapport("demande", demande)                    # demandes refaites ou annulées juste après
    whisper_ici, duree_whisper = duree_whisper, 0.0
    mesure = (f"Whisper {whisper_ici:.1f} s, " if whisper_ici else "")
    minuscules = demande.lower()
    sous_titre(derniers_textes[0] if derniers_textes else demande)
    # Qui parle ? Si la voix d'un autre profil est reconnue, Jarvis passe dessus avant de répondre
    bonjour_profil = ""
    try:
        # « apprends ma voix » (voix pas encore connue) ou « c'est Marie » (la personne dit qui elle est) :
        # la voix ne fait pas changer de profil
        # (une demande écrite au clavier n'a pas de voix : on reste sur le profil en cours)
        if (not _demande_ecrite
                and not jarvis_extras.invite() and not re.search(r"\bappren\w*\b.{0,15}\b(?:voix|voie|envoie)\b", minuscules)
                and not any(jarvis_profils._CEST.match(jarvis_commandes._propre(x)) for x in (derniers_textes or [demande]))):
            bonjour_profil = jarvis_locuteur.appliquer()
        if bonjour_profil and jarvis_extras.redemarrer_claude:
            jarvis_extras.redemarrer_claude = False
            with claude.verrou:
                claude.demarrer()                  # conversation neuve, avec la mémoire de cette personne
    except Exception as erreur_voix:
        print("Reconnaissance de la voix :", erreur_voix)
    try:                                           # un message laissé par quelqu'un du foyer ?
        bonjour_profil += jarvis_foyer.messages_en_attente()
    except Exception as erreur_message:
        print("Messages :", erreur_message)
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

    # Tâches de fond confiées à Claude Code (jarvis_taches.py) : avant les commandes instantanées,
    # sinon « en tâche de fond, cherche … » partirait en simple recherche dans le navigateur
    try:
        reponse_tache = jarvis_taches.commande([demande], enfant=jarvis_enfant.actif())
    except Exception as erreur_tache:
        print("Tâche de fond :", erreur_tache)
        reponse_tache = None
    if reponse_tache:
        derniere_reponse = reponse_tache
        etat("reponse")
        interrompu = parler(avec_salutation(bonjour_profil + reponse_tache))
        preparer_ecoute(recognizer)
        return interrompu

    # Commandes instantanées : réponse immédiate, sans Claude
    reponse = commande_instantanee(derniers_textes or [demande],
                                   annoncer=lambda texte: point_pret.put((texte, "rappel")))
    if jarvis_extras.redemarrer_claude:            # mode invité activé ou désactivé : conversation neuve
        jarvis_extras.redemarrer_claude = False
        threading.Thread(target=claude.demarrer, daemon=True).start()
    if reponse:
        derniere_reponse = reponse
        print("Commande instantanée :", reponse)
        print(f"(Durées : {mesure}commande {time.time() - debut_traitement:.2f} s)")
        rapport("reponse", demande, "local", time.time() - debut_traitement + whisper_ici,
                etape=f"whisper {whisper_ici:.1f} s" if whisper_ici else "")
        jarvis_memoire.noter_echange(derniers_textes[0] if derniers_textes else demande, reponse, "local", demande)
        etat("reponse")
        interrompu = parler(avec_salutation(bonjour_profil + reponse))
        interrompu = _poser_question_accueil(reponse, interrompu)
        if not interrompu and jarvis_locuteur.guide_demande():     # « apprends ma voix » : phrase par phrase
            interrompu = apprendre_voix_guidee(recognizer)
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

    note = jarvis_extras.note_recette(demande) + note
    try:                                         # « c'est quand la piscine ? » cherché en vain dans l'agenda iCloud
        if not jarvis_extras.invite():           # jamais l'agenda de la famille en mode invité
            note = jarvis_agenda.note_claude(" ".join(derniers_textes or [demande])) + note
    except Exception as erreur_agenda:
        print("Agenda :", erreur_agenda)
    if re.search(r"\b(?:télé|tele|tv|télévision|chaîne|chaine|apple|player)\b", minuscules):
        note = ("(Note : Jarvis pilote lui-même la télé (Freebox Player) et l'Apple TV, par des commandes directes. "
                "Si cette demande en parlait, c'est qu'il ne l'a pas comprise : ne dis pas que tu ne peux pas piloter "
                "la télé et ne parle pas d'une panne ; propose la phrase exacte à redire, par exemple « mets France 2 "
                "sur la télé », « allume l'Apple TV » ou « lance YouTube sur l'Apple TV ».) ") + note
    try:                                         # devoirs, résumé de la journée (voir jarvis_famille)
        note = jarvis_famille.note_devoirs(demande) + note
        if jarvis_famille.resume_demande(minuscules):
            note = jarvis_famille.note_resume(jarvis_commandes._rappels_du_jour(1)) + note
        note = jarvis_foyer.note_defi(demande) + note
        note = jarvis_foyer.note_quiz(demande, jarvis_locuteur.dernier_identifie) + note
    except Exception as erreur_famille:
        print("Famille :", erreur_famille)
    if jarvis_extras.invite():
        note = ("(Mode invité : une autre personne que " + jarvis_config.NOM + " utilise Jarvis. Ne donne aucune "
                "information personnelle de " + jarvis_config.NOM + " et n'écris jamais de ligne RETENIR ou OUBLIER.) ") + note

    if jarvis_famille.dodo_demande(demande):       # profil enfant : histoire du soir, puis Jarvis s'endort
        interrompu = raconter(jarvis_famille.note_dodo() + note + demande, demande, recognizer)
        jarvis_famille.entrer_dodo()
        return interrompu

    if histoire:
        return raconter(note + demande, demande, recognizer)

    def travail():
        resultat["r"] = demander_avec_secours(note + demande, demande)

    fil = threading.Thread(target=travail, daemon=True)
    fil.start()
    fil.join(DELAI_AVANT_PATIENCE)
    if fil.is_alive() and not histoire:
        speak(phrase_patience(minuscules))
        for suite in PATIENCE_SUITE:
            fil.join(DELAI_ENTRE_PATIENCES)
            if not fil.is_alive():
                break
            speak(suite)
    fil.join()
    reponse, erreur = resultat.get("r", ("Claude ne m'a pas répondu.", True))
    print("Claude :", reponse)
    print(f"(Durées : {mesure}Claude {time.time() - debut_traitement:.1f} s)")
    rapport("reponse", demande, "claude", time.time() - debut_traitement + whisper_ici, erreur=bool(erreur),
            etape=f"whisper {whisper_ici:.1f} s, claude {time.time() - debut_traitement:.1f} s")
    if erreur:
        rapport("erreur", "claude", texte=str(reponse))
    if not erreur:
        reponse = jarvis_enfant.appliquer(reponse)              # résumé de l'histoire gardé pour la suite
        reponse = jarvis_extras.appliquer_recette(reponse)     # étapes de la recette gardées pour « étape suivante »
        reponse = jarvis_foyer.appliquer_defi(reponse)         # étoile gagnée au défi du jour
        reponse = jarvis_foyer.appliquer_quiz(reponse)         # points du quiz en famille
        reponse = jarvis_ecran.appliquer_copie(reponse)        # texte corrigé ou traduit -> presse-papiers
        reponse = re.sub(r"[*_#`>]", "", reponse)
        reponse = jarvis_memoire.appliquer_balises(reponse) or "C'est noté."
        jarvis_memoire.noter_echange(derniers_textes[0] if derniers_textes else demande, reponse, "claude", demande)
    derniere_reponse = reponse
    etat("erreur" if erreur else "reponse")
    if not erreur:
        if time.time() - debut_traitement > DUREE_TACHE_LONGUE:
            jarvis_voix.son_fini()                 # une longue tâche est finie : petit son avant la réponse
        reponse_seule = reponse
        reponse = avec_salutation(bonjour_profil + reponse)
    interrompu = parler(reponse)
    if not erreur:
        interrompu = _poser_question_accueil(reponse_seule, interrompu)
    preparer_ecoute(recognizer)
    return interrompu


def traiter_ecrit(demande, recognizer):
    """Une demande tapée dans la fenêtre de discussion. Même traitement qu'une demande dite, et Jarvis répond
    aussi à voix haute (sauf en mode nuit, comme toujours) ; il ne guette pas de suite à la voix ensuite."""
    global _demande_ecrite
    print("Demande écrite :", demande)
    derniers_textes[:] = [demande]
    baisser_son()
    try:
        if re.fullmatch(r"\W*(?:jarvis\W+)?(?:stop|arr[eê]te|tais[- ]toi|tait toi|silence|chut|ça suffit|ca suffit|tu peux te taire|mets[- ]toi en veille|met[- ]toi en veille|retourne en veille)\W*", demande, re.I):
            sous_titre("")
        elif est_politesse(demande) and not jarvis_commandes.confirmation_en_attente():
            etat("reponse")
            speak(phrase_variee(REMERCIEMENTS))
        else:
            _demande_ecrite = True
            try:
                traiter(demande, recognizer)
            finally:
                _demande_ecrite = False
    finally:
        remonter_son()
    preparer_ecoute(recognizer)
    etat("veille")


def apprendre_voix_guidee(recognizer):
    """Jarvis dit une phrase, attend qu'on la répète, puis passe à la suivante (empreinte de la voix)."""
    prenom = jarvis_profils.prenom_actif()
    bravo = ["Super !", "Très bien !", "Bravo !", "Parfait !", "Génial !"]
    debut = "Écoute bien, et répète chaque phrase après le bip. "
    silences = 0                                  # réponses vides d'affilée : personne n'est là
    for i, phrase in enumerate(jarvis_locuteur.phrases_guide(prenom)):
        for essai in range(3):
            etat("reponse")
            consigne = (f"{debut}Répète : {phrase}" if essai == 0
                        else f"Pas grave ! Écoute bien, et répète après le bip : {phrase}")
            speak(consigne)             # dit en entier : un mot entendu pendant la consigne ne coupe rien
            preparer_ecoute(recognizer)
            bip(attendre=False)
            etat("ecoute")
            entendu = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True) or ""
            print(f"(Voix : phrase {i + 1}, entendu : {entendu!r})")
            silences = 0 if entendu.strip() else silences + 1
            if silences >= 4:
                etat("reponse")
                jarvis_locuteur.annuler_guide()
                parler("Je n'entends personne, alors on arrête. Tu pourras recommencer quand tu veux.")
                return False
            if re.search(r"\b(stop|arr[eê]te|annule|j'arr[eê]te|on arr[eê]te)\b", entendu.lower()):
                etat("reponse")
                if len(jarvis_locuteur._guide["vecteurs"]) >= 4:          # assez de phrases : on garde
                    return parler("D'accord, on arrête là. " + jarvis_locuteur.terminer_guide(prenom))
                jarvis_locuteur.annuler_guide()
                parler("D'accord, on arrête. Tu pourras recommencer quand tu veux.")
                return False
            if entendu and jarvis_locuteur.apprendre_phrase(entendu, phrase):
                print(f"(Voix : phrase {i + 1} retenue.)")
                debut = random.choice(bravo) + " "
                break
            jarvis_locuteur._resultat(delai=0)        # empreinte de cette réponse : oubliée
            debut = ""
        else:
            debut = "On passe à la suivante. "
    etat("reponse")
    return parler(jarvis_locuteur.terminer_guide(prenom))


_REPONSE_RATEE = re.compile(r"^\W*(?:Je ne (?:trouve|sais|vois|peux|comprends)|Je n'(?:ai|arrive)|Désolé|Impossible|"
                            r"Il faut d'abord|Ce n'est pas|Rien ne |.{0,60}n'est pas install)", re.I)


def _question_accueil(reponse=""):
    """Ajouté après la réponse : une question de premiers pas (nouvel utilisateur), sinon, sur un profil enfant,
    le bilan des étoiles du dimanche ou la proposition du défi du jour (une fois par jour au plus)."""
    if getattr(jarvis_maj, "lancee", False):     # « je lance la mise à jour » : Jarvis s'arrête, la réponse serait perdue
        return ""
    if reponse and _REPONSE_RATEE.match(str(reponse)):   # après un « je ne trouve pas… », pas de question ni de visite :
        return ""                                        # elle attendra la prochaine réponse
    try:
        question = jarvis_accueil.question()
        if question:
            return " " + question
        return jarvis_foyer.a_ajouter_apres(True)
    except Exception as erreur:
        print("Accueil :", erreur)
        return ""


PAUSE_AVANT_QUESTION = 0.7     # secondes entre la réponse et la question de premiers pas


def _poser_question_accueil(reponse, interrompu):
    """La question de premiers pas (ou le mot du profil enfant) est dite À PART, après une courte pause : collée à la
    réponse (« Il est 13 heures 27. Au fait, tu préfères… »), on ne comprenait pas qu'une question était posée.
    Rien n'est demandé si la réponse vient d'être interrompue. Renvoie True si Jarvis a été interrompu."""
    if interrompu:
        return True
    question = (_question_accueil(reponse) or "").strip()
    if not question:
        return False
    time.sleep(PAUSE_AVANT_QUESTION)
    return parler(question)


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
            if erreur and claude_indisponible(reponse):              # pas de Claude : un autre assistant raconte
                try:
                    import jarvis_assistants
                    if jarvis_assistants.utilisable_maintenant():
                        texte_autre, _nom, _e = jarvis_assistants.demander(demande, True)
                        if texte_autre:
                            reponse, erreur = texte_autre, False
                            recevoir(reponse)
                except Exception as e_autre:
                    print("Secours histoire :", e_autre)
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
    replique_ouverte = False
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
            # Deux voix : une réplique coupée entre deux morceaux garde sa voix dans le morceau suivant
            texte_bout = (jarvis_voix.OUVRE_AUTRE_VOIX if replique_ouverte else "") + bout
            replique_ouverte = texte_bout.count(jarvis_voix.OUVRE_AUTRE_VOIX) > texte_bout.count(jarvis_voix.FERME_AUTRE_VOIX)
            if replique_ouverte:
                texte_bout += jarvis_voix.FERME_AUTRE_VOIX
            interrompu = parler(re.sub(r"[*_#`>]", "", texte_bout))
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
    derniere_reponse = jarvis_voix.sans_balises_voix(re.sub(r"[*_#`>]", "", (tout[:_DEBUT_BALISE.search(tout).start()]
                                                if _DEBUT_BALISE.search(tout) else tout))).strip() or derniere_reponse
    preparer_ecoute(recognizer)
    return interrompu


# « redémarre-toi », y compris mal entendu (« redémarte-toi », « redémarre temps »)
DEMANDE_REDEMARRAGE = re.compile(r"\b(red[ée]mar\w*|relance\w*)[- ]+(toi|toit|temps|toa)\b|\b(red[ée]mar\w*|relance) jarvis\b"
                                 r"|^\W*(?:jarvis\W+)?red[ée]mar(?:re|res|rer|é)\W*$")   # « Jarvis, redémarre » tout court


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
        try:                                    # journal local seulement : ce que Jarvis a compris, pour améliorer la compréhension
            autres = [x for x in (derniers_textes or []) if x and x != demande]
            print("Demande comprise :", repr(demande) + (" | autre version : " + repr(autres[0]) if autres else ""))
        except Exception:
            pass
        # « Jarvis » redit pendant la conversation : on écoute la suite, sans déranger Claude
        if re.fullmatch(r"\W*jarvis\W*", demande, re.I) or (
                derniers_textes and re.fullmatch(r"\W*jarvis\W*", derniers_textes[0], re.I)):
            bip(attendre=False)
            etat("ecoute")
            demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE, bip_au_debut=True)
            continue
        if re.fullmatch(r"\W*(?:jarvis\W+)?(?:stop|arr[eê]te|tais[- ]toi|tait toi|silence|chut|ça suffit|ca suffit|tu peux te taire|mets[- ]toi en veille|met[- ]toi en veille|retourne en veille)\W*", demande, re.I):
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
            try:
                video = son_pc_rapide()
            except Exception:
                video = False
            if video:              # une vidéo qui dit « Jarvis » : on ne répond rien, plutôt que « tu peux répéter ? »
                print("(Le PC joue du son : sans doute une vidéo, retour en veille sans rien dire.)")
                rapport("faux_reveil", "son du PC", demande)
                preparer_ecoute(recognizer)
                etat("veille")
                return
            essais_courts += 1
            rapport("incompris", demande, "demande trop courte")
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
        # (pas juste après une question d'accueil : une seule question à la fois)
        if (not jarvis_commandes.confirmation_en_attente() and not jarvis_accueil.en_attente_de_reponse()
                and jarvis_maj.a_annoncer()):
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
        if demande and not attend_reponse and _bavardage(demande):
            print("(Suite ignorée : quelqu'un parle à côté, pas à Jarvis. Entendu :", demande[:80], ")")
            break
        if demande and not attend_reponse and son_pc():
            print("(Suite ignorée : le PC s'est mis à jouer du son. Entendu :", demande[:80], ")")
            break
    print("(Retour en veille : dis « Jarvis » pour me réveiller.)")
    etat("veille")


def _prochain_bloc(file_audio, debut, deja_recu):
    """Attend le prochain bloc de son du micro. Renvoie (bloc, True), ou (None, False) si le micro n'a encore rien envoyé
    depuis le lancement (Windows peut être occupé : on attend jusqu'à MICRO_MUET_DEMARRAGE secondes).
    Lève RuntimeError si le micro se tait en cours de route (débranché), ou si rien n'est jamais arrivé dans ce délai."""
    try:
        return file_audio.get(timeout=MICRO_MUET), True
    except queue.Empty:
        if not deja_recu and time.time() - debut < MICRO_MUET_DEMARRAGE:
            if not _prochain_bloc.attente_dite:
                _prochain_bloc.attente_dite = True
                print("(Le micro n'a encore rien envoyé : j'attends encore un peu, Windows est peut-être occupé.)")
            return None, False
        bloc = _retablir_micro()                       # 3 essais pour le retrouver, puis le message
        if bloc is not None:
            return bloc, True
        raise RuntimeError("le micro n'envoie plus de son (débranché ?)")


_prochain_bloc.attente_dite = False


_micro_actif = None


class _MicroRobuste:
    """Le micro ouvert, qu'on peut rouvrir sans arrêter Jarvis quand il se tait."""

    def __init__(self):
        self.flux = None

    def __enter__(self):
        global _micro_actif
        self.flux = _ouvrir_micro()
        self.flux.start()
        _micro_actif = self
        return self

    def __exit__(self, *args):
        global _micro_actif
        _micro_actif = None
        self.fermer()
        return False

    def fermer(self):
        flux, self.flux = self.flux, None
        if flux is not None:
            for action in (flux.stop, flux.close):
                try:
                    action()
                except Exception:
                    pass

    def rouvrir(self, reinitialiser, attente):
        """Ferme et rouvre le micro (en réinitialisant PortAudio si demandé). Renvoie un bloc de son, ou None."""
        self.fermer()
        if reinitialiser:
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        while True:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self.flux = _ouvrir_micro()
            self.flux.start()
            return audio_queue.get(timeout=attente)
        except queue.Empty:
            return None
        except Exception as erreur:
            print("(Micro : réouverture impossible :", erreur, ")")
            return None


_sans_micro_traiter = None      # fonction de main() : traite la fenêtre de discussion, les rappels et les alertes


def _patienter(secondes):
    """Attend sans rien bloquer : pendant ce temps la fenêtre de discussion, les rappels et les alertes sont traités,
    pour que Jarvis reste utilisable même quand aucun micro n'est branché."""
    for _ in range(max(1, int(secondes / 0.3))):
        if _sans_micro_traiter is not None:
            try:
                _sans_micro_traiter()
            except Exception as erreur:
                print("(Sans micro, traitement ignoré :", erreur, ")")
        time.sleep(0.3)


def _retablir_micro():
    """Le micro ne répond plus : 3 essais pour le retrouver. Sans succès, « Aucun micro détecté » reste affiché environ
    2 minutes au-dessus du réacteur (en continuant d'essayer). Renvoie un bloc de son, ou None si le micro reste muet
    (Jarvis s'arrête alors et le gardien le relance, comme avant)."""
    micro = _micro_actif
    if micro is None:
        return None
    for essai in range(1, MICRO_ESSAIS + 1):
        print(f"(Le micro ne répond plus : essai {essai} sur {MICRO_ESSAIS} pour le retrouver.)")
        bloc = micro.rouvrir(essai > 1, MICRO_ESSAI_ATTENTE)
        if bloc is not None:
            print("(Micro retrouvé.)")
            return bloc
    print(f"Aucun micro détecté après {MICRO_ESSAIS} essais : message affiché {MICRO_MESSAGE_DUREE} secondes ; "
          "la fenêtre de discussion reste utilisable.")
    etat("erreur")
    sous_titre(MICRO_MESSAGE)
    debut = time.time()
    message = True
    while True:
        _patienter(6)
        bloc = micro.rouvrir(True, 2)
        if bloc is not None:
            print("(Micro retrouvé.)")
            sous_titre("")
            etat("veille")
            return bloc
        duree = time.time() - debut
        if message and duree >= MICRO_MESSAGE_DUREE:
            sous_titre("")
            message = False
        if duree >= MICRO_ABANDON and time.time() - derniere_activite >= 60:
            sous_titre("")
            return None             # Jarvis s'arrête, le gardien le relance : PortAudio repart de zéro


def attendre_micro(entre_temps=None):
    """Sans micro, Jarvis attend qu'on en branche un, au lieu de s'arrêter et d'être relancé toutes les minutes.
    Après 3 essais sans micro, « Aucun micro détecté » s'affiche environ 2 minutes au-dessus du réacteur."""
    echecs = 0
    message_a = None
    while True:
        try:
            nom = sd.query_devices(kind="input")["name"]
            if os.environ.get("JARVIS_TEST_SANS_MICRO"):      # essais : fait comme s'il n'y avait pas de micro
                raise RuntimeError("micro simulé absent")
            if echecs:
                print("Micro trouvé :", nom)
                sous_titre("")
            return
        except Exception:
            pass
        echecs += 1
        if echecs == MICRO_ESSAIS:
            print("Aucun micro trouvé : branche un micro, Jarvis démarrera tout seul (vérification toutes les 5 secondes).")
            etat("erreur")
            sous_titre(MICRO_MESSAGE)
            message_a = time.time()
        elif message_a and time.time() - message_a >= MICRO_MESSAGE_DUREE:
            sous_titre("")                      # le message a duré 2 minutes ; Jarvis continue d'attendre en silence
            message_a = None
        if entre_temps is None:
            time.sleep(5)
        else:                   # pendant l'attente : la fenêtre de discussion, les rappels et les alertes fonctionnent
            for _ in range(17):
                try:
                    entre_temps()
                except Exception as erreur:
                    print("(Sans micro, traitement ignoré :", erreur, ")")
                time.sleep(0.3)
        try:                    # PortAudio ne voit un micro branché après coup qu'après avoir été relancé
            sd._terminate()
            sd._initialize()
        except Exception:
            pass


_RALLUMER_MICRO = re.compile(r"\bjarvis\b.*\b(?:rallume|allume|réactive|reactive|remets|active)\b.*\bmicro\b"
                             r"|\bjarvis\b.*\b(?:écoute|ecoute)[- ]moi\b"
                             r"|\bjarvis\b.*\b(?:recommence|reprends) (?:à|a) (?:écouter|ecouter)\b")


def main():
    global rec_stop, rec_coupure, micro_coupe, _sans_micro_traiter
    if AudioUtilities is not None:
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

    reparer_volumes()
    # Tout ce que Jarvis dit s'écrit aussi dans la fenêtre de discussion (en mode nuit, il l'écrit sans le dire)
    jarvis_voix.afficher = lambda texte: sous_titre(texte, reponse=True)
    print("Chargement du modèle français...")
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    recognizer.SetWords(True)          # heure de chaque mot : sert à repérer la pause avant « Jarvis »
    rec_stop = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(MOTS_STOP + ["[unk]"], ensure_ascii=False))
    rec_coupure = KaldiRecognizer(model, SAMPLE_RATE)
    jarvis_locuteur.preparer(model)              # reconnaissance de la voix de chaque profil (si le modèle est là)
    # Tout le reste se charge en arrière-plan : Jarvis écoute dès que Vosk est prêt
    jarvis_systeme.demarrer()
    rapport("demarrer")                          # rapports (compteur anonyme ; le reste avec l'accord de l'utilisateur)
    try:                                         # la question de l'accord (une fois), puis le questionnaire à 7 jours
        import jarvis_rapports_ui
        jarvis_rapports_ui.au_demarrage()
    except Exception as erreur_fenetres:
        print("Rapports (fenêtres) :", erreur_fenetres)
    try:                                         # nouvel utilisateur : la fenêtre « Premiers pas », une seule fois
        import jarvis_premiers_pas
        jarvis_premiers_pas.au_demarrage()
    except Exception as erreur_fenetres:
        print("Premiers pas :", erreur_fenetres)
    jarvis_commandes.demarrer_rappels(lambda texte: point_pret.put((texte, "rappel")))
    try:                                         # Wikipédia tarde (sans Claude) : « Je regarde sur Wikipédia. »
        import jarvis_wikipedia
        jarvis_wikipedia.patienter = lambda phrase: speak(phrase)
    except Exception as erreur_wiki:
        print("Wikipédia :", erreur_wiki)
    try:                                         # Ctrl + Alt + J : écrire à Jarvis depuis n'importe quelle fenêtre
        import jarvis_raccourci
        jarvis_raccourci.demarrer(jarvis_raccourci.ouvrir_saisie)
    except Exception as erreur_raccourci:
        print("Raccourci clavier :", erreur_raccourci)
    jarvis_commandes.precharger_applications()
    jarvis_vigilance.surveiller(lambda texte: point_pret.put((texte, "alerte")))   # vigilance Météo-France
    jarvis_extras.appliquer_couleur()            # couleurs du réacteur choisies par l'utilisateur
    jarvis_extras.surveiller_anniversaires(lambda texte: point_pret.put((texte, "rappel")))
    jarvis_foyer.surveiller_calendrier(lambda texte: point_pret.put((texte, "rappel")))   # calendrier familial
    jarvis_infos.surveiller_poubelles(lambda texte: point_pret.put((texte, "rappel")))   # bacs à sortir, la veille
    jarvis_agenda.surveiller(lambda texte: point_pret.put((texte, "rappel")),
                             jarvis_config.chemin("agenda_veille.date"))                  # agenda iCloud, la veille
    jarvis_taches.configurer(CLAUDE_EXE, MODELE_POINT_DU_JOUR, OUTILS_POINT_DU_JOUR, MODE_PERMISSIONS,
                             OPTIONS_LEGERES, DOSSIER_JARVIS,
                             lambda texte, erreur: point_pret.put((texte, erreur)))      # tâches de fond
    try:                                         # la tablette de la maison, si son accès est activé
        jarvis_tablette.configurer(sys.modules[__name__])
        jarvis_tablette.demarrer()
    except Exception as erreur_tablette:
        print("Tablette :", erreur_tablette)
    jarvis_enfant.annoncer = lambda texte: point_pret.put((texte, False))     # Jarvis parle de lui-même (YouTube Kids)
    threading.Thread(target=charger_whisper, daemon=True).start()
    threading.Thread(target=jarvis_motappel.detecteur, daemon=True).start()   # détecteur « Jarvis » prêt d'avance
    try:                                           # télé et Apple TV : connexion prête d'avance (ordres plus rapides)
        jarvis_commandes.jarvis_tele.prechauffer()
        jarvis_commandes.jarvis_appletv.prechauffer()
    except Exception as erreur_tele:
        print("Télé (préparation) :", erreur_tele)
    threading.Thread(target=suivre_musique, daemon=True).start()
    threading.Thread(target=_preparer_plus_tard, args=(PATIENCE + PATIENCE_SUITE + [p for _m, l in PATIENCE_PAR_SUJET for p in l] + REMERCIEMENTS + ["Je n'ai rien entendu.", "Je n'ai pas bien compris, tu peux répéter ?",
              "Je n'ai pas compris, redis Jarvis quand tu veux.", "D'accord, on repart de zéro.",
              "Je prépare ton point du jour, je te le lis dès qu'il est prêt.",
              "D'accord, j'annule le point du jour.", "Aucun point du jour n'est en préparation.",
              "Avec plaisir.", "C'est fait.", "C'est retenu.", "C'est noté.",
              "Ton point du jour est déjà en préparation, je te le lis dès qu'il est prêt.",
              "Je regarde sur Wikipédia.", "Dans le doute, je ne fais rien. Redemande-le-moi, puis réponds juste oui.",
              "Je règle mon micro sur le bruit de la pièce. Ne parle pas pendant une dizaine de secondes, "
              "je te dis quand c'est fini."],), daemon=True).start()
    threading.Thread(target=claude.demarrer, daemon=True).start()   # Claude prêt d'avance
    bilan = jarvis_maj.bilan_au_demarrage()       # après une mise à jour lancée par Jarvis : a-t-elle réussi ?
    if bilan:
        point_pret.put((bilan, None))
    # Relancé après un plantage, une perte du micro ou un redémarrage forcé ? Jarvis ne le dit plus à voix haute :
    # il écrit seulement « Je redémarre. » dans la fenêtre de discussion (la cause reste dans le journal)
    reprise = jarvis_sante.phrase_reprise()
    if reprise:
        print(f"(Relance : {reprise})")
    jarvis_maj.verifier_en_arriere_plan()        # une version plus récente est-elle publiée sur GitHub ?

    heure = time.localtime().tm_hour
    if (POINT_DU_JOUR_AUTO and POINT_DU_JOUR_HEURES[0] <= heure < POINT_DU_JOUR_HEURES[1]
            and not point_du_jour_deja_fait()):
        threading.Thread(target=preparer_point_du_jour, args=(POINT_DU_JOUR_ATTENTE,),
                         daemon=True).start()

    def _dire_forcee(texte):
        """La mise à jour forcée est annoncée à voix haute au premier essai seulement, pas à chaque nouvel essai."""
        if jarvis_maj.premier_essai_forcee():
            parler(texte)

    def hors_micro():
        """Sans micro : les demandes écrites, les rappels, les alertes et les mises à jour forcées sont traités."""
        if (jarvis_maj.forcee_en_attente() and time.time() - derniere_activite >= jarvis_maj.calme_requis()
                and demandes_ecrites.empty() and point_pret.empty() and jarvis_maj.forcee_a_installer()):
            etat("reponse")
            sous_titre("Mise à jour importante : je m'installe.", reponse=True)
            _dire_forcee("Une mise à jour importante de Jarvis vient d'arriver : je l'installe maintenant. "
                   "Je m'arrête quelques minutes, puis je redémarre tout seul." + jarvis_maj.avertissement_windows())
            print("Mise à jour forcée :", jarvis_maj.installer())
            etat("erreur")
        if not point_pret.empty():
            texte, erreur = point_pret.get()
            if erreur == "rappel":
                etat("rappel")
                sous_titre(re.sub(r"^Rappel : |\.$", "", texte))
            else:
                etat("erreur" if erreur is True else "reponse")
            baisser_son()
            try:
                urgent = erreur in ("rappel", "alerte")
                bip(toujours=urgent)
                parler(texte, toujours=urgent)
            finally:
                remonter_son()
            etat("erreur")
        if not demandes_ecrites.empty():
            traiter_ecrit(demandes_ecrites.get(), recognizer)
            etat("erreur")                  # le réacteur reste en erreur tant qu'il n'y a pas de micro

    _sans_micro_traiter = hors_micro
    attendre_micro(hors_micro)
    etat("veille")
    if reprise:
        sous_titre("Je redémarre.", reponse=True)
    avec_claude = os.path.exists(CLAUDE_EXE)       # Jarvis installé sans Claude : commandes immédiates seulement
    print(f"\nJARVIS version {VERSION} EST EN ÉCOUTE PERMANENTE "
          f"({'relié à Claude' if avec_claude else 'sans Claude : commandes immédiates, et un autre assistant si tu en as branché un'}).")
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
        with _MicroRobuste():
            debut_ecoute = time.time()
            premier_son_recu = False
            while True:
                data, premier_son_recu = _prochain_bloc(audio_queue, debut_ecoute, premier_son_recu)
                if data is None:               # le micro n'a encore rien envoyé : on attend encore, sans relancer Jarvis
                    continue
                claude.entretenir()

                # Mise à jour forcée publiée sur GitHub : installée sans question, dès le démarrage de Jarvis,
                # sinon après vingt secondes de veille
                # (personne ne parle à Jarvis, aucune demande en cours)
                if (jarvis_maj.forcee_en_attente() and time.time() - derniere_activite >= jarvis_maj.calme_requis()
                        and demandes_ecrites.empty() and point_pret.empty() and jarvis_maj.forcee_a_installer()):
                    etat("reponse")
                    sous_titre("Mise à jour importante : je m'installe.", reponse=True)
                    _dire_forcee("Une mise à jour importante de Jarvis vient d'arriver : je l'installe maintenant. "
                           "Je m'arrête quelques minutes, puis je redémarre tout seul." + jarvis_maj.avertissement_windows())
                    print("Mise à jour forcée :", jarvis_maj.installer())
                    tampon.clear()
                    etat("veille")
                    continue

                # Windows a refusé de lancer l'installateur de la mise à jour : on le dit, au lieu de se taire
                phrase_echec = jarvis_maj.echec_a_dire()
                if phrase_echec:
                    etat("reponse")
                    sous_titre(phrase_echec, reponse=True)
                    parler(phrase_echec)
                    etat("veille")
                    continue

                # Point du jour préparé en arrière-plan : on le lit maintenant
                if not point_pret.empty():
                    texte, erreur = point_pret.get()
                    if erreur == "rappel":         # un minuteur ou un rappel : alerte visuelle sur le réacteur
                        etat("rappel")
                        sous_titre(re.sub(r"^Rappel : |\.$", "", texte))
                    else:
                        etat("erreur" if erreur is True else "reponse")
                    baisser_son()
                    try:
                        urgent = erreur in ("rappel", "alerte")    # un rappel ou une alerte météo sonne même en mode nuit
                        bip(toujours=urgent)
                        parler(texte, toujours=urgent)
                    finally:
                        remonter_son()
                    preparer_ecoute(recognizer)
                    tampon.clear()
                    etat("veille")
                    continue

                # Une demande écrite au clavier, dans la fenêtre de discussion
                if not demandes_ecrites.empty():
                    traiter_ecrit(demandes_ecrites.get(), recognizer)
                    tampon.clear()
                    continue

                # Micro coupé (« coupe le micro », ou le menu du réacteur) : rien n'est écouté ; les demandes écrites,
                # les rappels et les alertes passent toujours
                if micro_coupe:
                    # Le micro n'est coupé que pour Jarvis : il ne répond plus à rien, sauf à la phrase qui le
                    # rallume (« Jarvis, rallume ton micro »), reconnue sur ce PC et oubliée aussitôt
                    tampon.clear()
                    if recognizer.AcceptWaveform(data):
                        dite = json.loads(recognizer.Result()).get("text", "").lower()
                        if _RALLUMER_MICRO.search(dite):
                            regler_micro(False)
                            print("(Micro rallumé à la voix.)")
                            etat("reponse")
                            parler("C'est fait, je t'écoute de nouveau.")
                            preparer_ecoute(recognizer)
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
                                rapport("faux_reveil", "réveil pendant un son du PC, rien ensuite")
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
