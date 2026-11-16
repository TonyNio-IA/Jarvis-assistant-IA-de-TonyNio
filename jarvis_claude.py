"""
JARVIS - l'assistant vocal de TonyNio, relié à Claude.

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
  6. « Jarvis, fais-moi le point du jour » : météo, actualités, SpaceX, GTA 6, PS5, Logic-Sunrise.
     Il le prépare aussi tout seul au premier démarrage du matin (une fois par jour).
  8. « Stop » ou « Jarvis, stop » pendant qu'il parle : il se tait.
  9. Heure, date, volume et ouverture d'applications : réponse immédiate, sans Claude.
  7. Il se met en pause tout seul quand Claude lit un message à voix haute (touche F9).

Lancement :  python C:\\Jarvis\\jarvis_reacteur.py   (avec le réacteur)
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

from jarvis_voix import speak, bip, preparer  # voix naturelle Henri (voix Windows en secours)
from jarvis_commandes import commande_instantanee  # heure, volume, applications...

# ===== Réglages =====
MODEL_PATH = r"C:\Jarvis\vosk-model-small-fr-0.22"
SAMPLE_RATE = 16000
DOSSIER_JARVIS = r"C:\Jarvis"
CLAUDE_EXE = os.path.expanduser(r"~\.local\bin\claude.exe")
DELAI_ECOUTE_DEMANDE = 8      # secondes pour commencer à parler après « Jarvis »
SILENCE_FIN = 1.0             # secondes de silence qui marquent la fin de ta demande
DELAI_SUITE = 3               # secondes pour enchaîner une autre demande sans redire « Jarvis »
MOTS_MINIMUM = 2              # une demande plus courte est considérée comme mal entendue
DELAI_MAX_CLAUDE = 300        # secondes maximum pour une réponse de Claude
DELAI_MAX_POINT_DU_JOUR = 900 # le point du jour demande beaucoup de recherches
MODE_PERMISSIONS = "auto"     # Claude Code vérifie chaque action et bloque les risquées
MODELE = "sonnet"             # modèle pour les demandes courantes : "sonnet" (rapide) ou "opus" (plus puissant)
DELAI_AVANT_PATIENCE = 1.5    # si Claude n'a pas répondu après ce délai, Jarvis dit « Je m'en occupe »
AUDIO_DIAGNOSTIC = r"C:\Jarvis\derniere_demande.wav"   # dernière demande enregistrée (pour diagnostic)
MEMOIRE_MINUTES = 10          # Jarvis se souvient de la conversation pendant 10 min sans demande

# Reconnaissance précise de la demande (Whisper, sur le PC)
WHISPER_MODELE = "base"
WHISPER_DOSSIER = r"C:\Jarvis\whisper"
VOCABULAIRE = ("Jarvis, TonyNio, Paris, "
               "SpaceX, GTA 6, PS5, PlayStation, Logic-Sunrise, Chrome, Claude.")

# Pause automatique quand ces programmes jouent du son (lecture à voix haute F9)
PROGRAMMES_A_IGNORER = ("claude.exe",)

VILLE_METEO = "Paris"

# Point du jour automatique : au premier démarrage de Jarvis entre ces heures, une fois par jour
POINT_DU_JOUR_AUTO = True
POINT_DU_JOUR_HEURES = (5, 12)          # de 5 h à midi
POINT_DU_JOUR_ATTENTE = 20              # secondes d'attente au démarrage (laisser Internet se connecter)
FICHIER_POINT_DU_JOUR = r"C:\Jarvis\point_du_jour.date"

# Mots qui interrompent Jarvis pendant qu'il parle
MOTS_STOP = ["jarvis stop", "stop", "jarvis arrête", "arrête", "tais-toi", "jarvis tais-toi"]

CONSIGNES = (
    "Tu es Jarvis, l'assistant vocal de TonyNio sur son PC Windows 11. "
    "Ta réponse sera lue à voix haute : réponds en français, en une à trois phrases "
    "courtes et naturelles, sans markdown, sans liste, sans emoji, sans lien. "
    "Si la demande est une action sur le PC, fais-la si c'est sans risque, "
    "puis dis brièvement ce que tu as fait. "
    "Ne supprime jamais de fichiers et ne modifie jamais les scripts existants "
    "sans qu'on te le demande explicitement. "
    "La demande vient d'une reconnaissance vocale : si un mot semble mal compris, "
    "devine le sens le plus probable, et en cas de vrai doute, demande de répéter. "
    "Parfois deux retranscriptions de la même phrase te sont données : "
    "déduis-en ensemble ce que TonyNio a voulu dire."
)

CONSIGNES_POINT_DU_JOUR = (
    "Tu es Jarvis, l'assistant vocal de TonyNio. Ta réponse sera lue à voix haute "
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


def etat(nom):
    try:
        afficher_etat(nom)
    except Exception:
        pass


derniere_erreur = False
derniers_textes = []          # les retranscriptions (Whisper, Vosk) de la dernière demande
rec_stop = None               # reconnaissance réduite aux mots « stop »
point_pret = queue.Queue()    # point du jour préparé en arrière-plan, en attente de lecture
point_en_preparation = threading.Event()

# Mémoire de la conversation en cours
session_id = None
dernier_echange = 0.0

whisper = None


# ---------- Audio ----------

def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio :", status, file=sys.stderr)
    audio_queue.put(bytes(indata))


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


def lecture_en_cours():
    """Vrai si un des programmes à ignorer (Claude) est en train de jouer du son."""
    if AudioUtilities is None:
        return False
    try:
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.name().lower() in PROGRAMMES_A_IGNORER:
                compteur = session._ctl.QueryInterface(IAudioMeterInformation)
                if compteur.GetPeakValue() > 0.01:
                    return True
    except Exception:
        pass
    return False


# ---------- Reconnaissance précise (Whisper) ----------

def charger_whisper():
    global whisper
    try:
        from faster_whisper import WhisperModel
        whisper = WhisperModel(WHISPER_MODELE, device="cpu", compute_type="int8",
                               download_root=WHISPER_DOSSIER, cpu_threads=4)
        print("Reconnaissance précise (Whisper) prête.")
    except Exception as erreur:
        whisper = None
        print("Whisper indisponible, Vosk seul sera utilisé :", erreur)


def _enregistrer_diagnostic(octets):
    try:
        with wave.open(AUDIO_DIAGNOSTIC, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(octets)
    except Exception:
        pass


def _normaliser(texte):
    return re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüœ]+", " ", texte.lower()).strip()


def transcrire(octets, texte_vosk):
    """Retranscrit l'audio avec Whisper. En cas de souci, garde le texte de Vosk."""
    if whisper is None or not octets or not texte_vosk:
        return texte_vosk
    _enregistrer_diagnostic(octets)
    try:
        audio = np.frombuffer(octets, dtype=np.int16).astype(np.float32) / 32768.0
        crete = float(np.max(np.abs(audio))) if len(audio) else 0.0
        print("Niveau du micro (crête) : %.2f" % crete)
        if 0.01 < crete < 0.5:
            audio = audio * (0.7 / crete)       # voix trop faible : on l'amplifie
        segments, _ = whisper.transcribe(audio, language="fr", beam_size=1,
                                         initial_prompt=VOCABULAIRE)
        texte = " ".join(s.text for s in segments).strip()
    except Exception as erreur:
        print("Erreur Whisper :", erreur)
        return texte_vosk
    # Hallucinations connues de Whisper sur du bruit
    if not texte or re.search(r"amara|sous-titr", texte, re.I):
        return texte_vosk
    print("Whisper :", texte, "| Vosk :", texte_vosk)
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
    """Enlève « Jarvis » au début de la phrase. Renvoie None s'il n'y est pas."""
    m = re.match(r"\W*jarvis\b\W*(.*)", texte, re.I | re.S)
    return m.group(1).strip() if m else None


def ecouter_demande(recognizer, delai_debut, silence_fin=SILENCE_FIN):
    """
    Écoute une demande complète, même si elle contient de petites pauses.
    - attend au plus « delai_debut » secondes que tu commences à parler ;
    - ensuite, s'arrête quand tu te tais pendant « silence_fin » secondes.
    """
    morceaux = []
    octets = bytearray()
    debut = time.time()
    dernier_son = None
    while True:
        maintenant = time.time()
        if dernier_son is None and maintenant - debut > delai_debut:
            break
        if dernier_son is not None and maintenant - dernier_son > silence_fin:
            break
        try:
            data = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        octets.extend(data)
        if recognizer.AcceptWaveform(data):
            texte = json.loads(recognizer.Result()).get("text", "").strip()
            if texte:
                morceaux.append(texte)
                dernier_son = time.time()
        else:
            partiel = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            if partiel:
                dernier_son = time.time()
    fin = json.loads(recognizer.FinalResult()).get("text", "").strip()
    if fin:
        morceaux.append(fin)
    texte_vosk = " ".join(morceaux).strip()
    return combiner(transcrire(bytes(octets), texte_vosk), texte_vosk)


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
        self.verrou = threading.Lock()

    def _lire(self, flux, file_sortie):
        for ligne in flux:
            if file_sortie is not None:
                file_sortie.put(ligne)
        if file_sortie is not None:
            file_sortie.put(None)          # fin du programme

    def demarrer(self):
        self.arreter()
        self.sorties = queue.Queue()
        self.proc = subprocess.Popen(
            [CLAUDE_EXE, "-p", "--input-format", "stream-json",
             "--output-format", "stream-json", "--verbose",
             "--append-system-prompt", CONSIGNES,
             "--permission-mode", MODE_PERMISSIONS, "--model", MODELE],
            cwd=DOSSIER_JARVIS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._lire, args=(self.proc.stdout, self.sorties),
                         daemon=True).start()
        threading.Thread(target=self._lire, args=(self.proc.stderr, None),
                         daemon=True).start()
        self.dernier_usage = time.time()
        print("Claude prêt en continu (modèle", MODELE + ").")

    def arreter(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def demander(self, texte, delai=DELAI_MAX_CLAUDE):
        """Renvoie (réponse, erreur)."""
        with self.verrou:
            if (self.proc is None or self.proc.poll() is not None
                    or time.time() - self.dernier_usage > MEMOIRE_MINUTES * 60):
                self.demarrer()        # nouvelle conversation
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
                if donnees.get("type") != "result":
                    continue
                self.dernier_usage = time.time()
                reponse = str(donnees.get("result") or "").strip()
                if donnees.get("is_error") or not reponse:
                    print("Claude (erreur) :", ligne[:500])
                    if "limit" in ligne.lower():
                        return "La limite d'utilisation de Claude est atteinte pour le moment.", True
                    return "Claude a rencontré un problème avec cette demande.", True
                return re.sub(r"[*_#`>]", "", reponse), False


claude = ClaudeContinu()


def oublier_conversation():
    """Repart de zéro : Claude est relancé (en arrière-plan)."""
    threading.Thread(target=claude.demarrer, daemon=True).start()


def demander_a_claude(demande, consignes=CONSIGNES, delai=DELAI_MAX_CLAUDE):
    """Demande ponctuelle (programme lancé pour une seule question), utilisée pour
    le point du jour, qui a ses propres consignes et le modèle le plus puissant.
    Renvoie (réponse, erreur)."""
    if not os.path.exists(CLAUDE_EXE):
        return "Je ne trouve pas Claude Code sur cet ordinateur.", True
    commande = [
        CLAUDE_EXE,
        "-p", demande,
        "--append-system-prompt", consignes,
        "--permission-mode", MODE_PERMISSIONS,
        "--output-format", "json",
    ]
    try:
        resultat = subprocess.run(
            commande,
            cwd=DOSSIER_JARVIS,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=delai,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "Claude met trop de temps à répondre, j'abandonne cette demande.", True
    except Exception as erreur:
        print("Erreur Claude :", erreur)
        return "Je n'arrive pas à joindre Claude.", True

    sortie = (resultat.stdout or "").strip()
    try:
        donnees = json.loads(sortie)
    except Exception:
        donnees = None
    if not donnees:
        print("Claude (erreurs) :", (resultat.stderr or "").strip() or sortie)
        if "limit" in ((resultat.stderr or "") + sortie).lower():
            return "La limite d'utilisation de Claude est atteinte pour le moment.", True
        return "Claude ne m'a pas répondu.", True
    reponse = str(donnees.get("result") or "").strip()
    if donnees.get("is_error") or not reponse:
        print("Claude (erreur) :", sortie[:500])
        return "Claude a rencontré un problème avec cette demande.", True
    return re.sub(r"[*_#`>]", "", reponse), False


def question_point_du_jour():
    t = time.localtime()
    date = f"{JOURS[t.tm_wday]} {t.tm_mday} {MOIS[t.tm_mon - 1]} {t.tm_year}"
    return (
        f"Nous sommes le {date}, c'est la date exacte. "
        "Fais-moi le point du jour, dans cet ordre : "
        f"la météo du jour à {VILLE_METEO}, et pas celle d'une autre position ; "
        "les principales actualités en France et dans le monde ; SpaceX ; GTA 6 ; "
        "la PlayStation 5 ; et enfin les articles sur la PlayStation 5 publiés aujourd'hui "
        "sur le site logic-sunrise.com, que tu consultes directement. "
        "Fais une vraie recherche web pour chaque rubrique, y compris une recherche dédiée "
        "pour SpaceX, pour GTA 6 et pour la PlayStation 5. "
        "Vérifie que chaque information date bien d'aujourd'hui ou d'hier, qu'elle vient "
        "d'un média sérieux et qu'elle contient un nom, un lieu ou un chiffre précis. "
        "Si tu n'es pas sûr d'une information, ne la donne pas. "
        "Si tu trouves moins d'actualités que demandé, ou rien du tout pour une rubrique, "
        "dis-le simplement. N'invente jamais rien. "
        "Si Logic-Sunrise ne peut pas être consulté ou n'a rien publié sur la PS5 aujourd'hui, "
        "dis-le en une phrase. "
        "Environ 650 mots, et plus si c'est nécessaire pour ne rien oublier d'important. "
        "TRÈS IMPORTANT, ta réponse sera lue à voix haute : écris uniquement un texte parlé "
        "et fluide, comme un présentateur radio. Commence directement par la date, sans "
        "aucune phrase pour annoncer ce que tu vas faire. Aucun titre, aucun gras, aucune "
        "liste, aucun numéro devant les actualités. Passe d'un sujet à l'autre avec des "
        "transitions parlées. Ne cite jamais tes sources ni le nom des médias, et ne mets "
        "rien entre parenthèses. Aucune remarque, réserve ou explication sur tes recherches "
        "à la fin. Termine par une seule courte phrase."
    )


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
    try:
        time.sleep(attente)
        print("Préparation du point du jour...")
        texte, erreur = demander_a_claude(question_point_du_jour(),
                                          consignes=CONSIGNES_POINT_DU_JOUR,
                                          delai=DELAI_MAX_POINT_DU_JOUR)
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


# ---------- Interruption ----------

def interruption():
    """Vrai si TonyNio a dit « stop » pendant que Jarvis parle."""
    if rec_stop is None:
        return False
    while True:
        try:
            data = audio_queue.get_nowait()
        except queue.Empty:
            return False
        if rec_stop.AcceptWaveform(data):
            texte = json.loads(rec_stop.Result()).get("text", "")
            if texte and texte in MOTS_STOP:
                print("Interruption :", texte)
                return True


def parler(texte):
    """Parle en restant à l'écoute du mot « stop ». Renvoie True si interrompu."""
    if rec_stop is not None:
        rec_stop.Reset()
    vider_audio()
    return bool(speak(texte, interruption=interruption))


# ---------- Déroulement ----------

def preparer_ecoute(recognizer):
    recognizer.Reset()
    time.sleep(0.3)
    vider_audio()


def traiter(demande, recognizer):
    """Traite une demande. Renvoie True si Jarvis a été interrompu."""
    print("Demande :", demande)
    minuscules = demande.lower()
    if re.search(r"nouvelle conversation|oublie tout", minuscules):
        oublier_conversation()
        etat("reponse")
        speak("D'accord, on repart de zéro.")
        preparer_ecoute(recognizer)
        return False

    # Commandes instantanées : réponse immédiate, sans Claude
    reponse = commande_instantanee(derniers_textes or [demande])
    if reponse:
        print("Commande instantanée :", reponse)
        etat("reponse")
        interrompu = parler(reponse)
        preparer_ecoute(recognizer)
        return interrompu

    etat("traitement")
    if re.search(r"point du jour", minuscules):
        if point_en_preparation.is_set():
            speak("Ton point du jour est déjà en préparation, je te le lis dès qu'il est prêt.")
            preparer_ecoute(recognizer)
            return False
        speak("Je prépare ton point du jour, ça peut prendre quelques minutes.")
        point_en_preparation.set()
        try:
            reponse, erreur = demander_a_claude(question_point_du_jour(),
                                                consignes=CONSIGNES_POINT_DU_JOUR,
                                                delai=DELAI_MAX_POINT_DU_JOUR)
        finally:
            point_en_preparation.clear()
    else:
        # Claude travaille pendant que Jarvis parle : on ne perd pas de temps
        resultat = {}

        def travail():
            resultat["r"] = claude.demander(demande)

        fil = threading.Thread(target=travail, daemon=True)
        fil.start()
        fil.join(DELAI_AVANT_PATIENCE)
        if fil.is_alive():
            speak("Je m'en occupe.")
        fil.join()
        reponse, erreur = resultat.get("r", ("Claude ne m'a pas répondu.", True))
    print("Claude :", reponse)
    etat("erreur" if erreur else "reponse")
    interrompu = parler(reponse)
    preparer_ecoute(recognizer)
    return interrompu


def conversation(demande, recognizer):
    """Traite la demande, puis accepte des suites sans redire « Jarvis »."""
    essais_courts = 0
    while demande:
        if len(demande.split()) < MOTS_MINIMUM:
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
            break                      # interrompu : retour en veille
        print("(J'écoute une éventuelle suite pendant", DELAI_SUITE, "secondes...)")
        etat("ecoute")
        demande = ecouter_demande(recognizer, DELAI_SUITE)
    print("(Retour en veille : dis « Jarvis » pour me réveiller.)")
    etat("veille")


def main():
    global rec_stop
    if AudioUtilities is not None:
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

    print("Chargement du modèle français...")
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    rec_stop = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(MOTS_STOP + ["[unk]"], ensure_ascii=False))
    charger_whisper()
    preparer(["Je m'en occupe.", "Je n'ai rien entendu.", "Je n'ai pas bien compris, tu peux répéter ?",
              "Je n'ai pas compris, redis Jarvis quand tu veux.", "D'accord, on repart de zéro.",
              "Je prépare ton point du jour, ça peut prendre quelques minutes.",
              "Ton point du jour est déjà en préparation, je te le lis dès qu'il est prêt."])
    threading.Thread(target=claude.demarrer, daemon=True).start()   # Claude prêt d'avance

    heure = time.localtime().tm_hour
    if (POINT_DU_JOUR_AUTO and POINT_DU_JOUR_HEURES[0] <= heure < POINT_DU_JOUR_HEURES[1]
            and not point_du_jour_deja_fait()):
        threading.Thread(target=preparer_point_du_jour, args=(POINT_DU_JOUR_ATTENTE,),
                         daemon=True).start()

    etat("veille")
    print("\nJARVIS EST EN ÉCOUTE PERMANENTE (relié à Claude).")
    print("Dis : « Jarvis », puis ta demande.\n")

    tampon = bytearray()             # audio de la phrase en cours
    MAX_TAMPON = SAMPLE_RATE * 2 * 30  # 30 secondes au plus
    derniere_verif = 0.0
    fin_pause = 0.0
    en_pause = False

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=4000,
            device=None,
            dtype="int16",
            channels=1,
            callback=audio_callback,
        ):
            while True:
                data = audio_queue.get()

                # Point du jour préparé en arrière-plan : on le lit maintenant
                if not point_pret.empty():
                    texte, erreur = point_pret.get()
                    etat("erreur" if erreur else "reponse")
                    parler(texte)
                    preparer_ecoute(recognizer)
                    tampon.clear()
                    etat("veille")
                    continue

                # Pause pendant que Claude lit un message à voix haute
                maintenant = time.time()
                if maintenant - derniere_verif > 0.3:
                    derniere_verif = maintenant
                    if lecture_en_cours():
                        fin_pause = maintenant + 1.0
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

                tampon.extend(data)
                if len(tampon) > MAX_TAMPON:
                    del tampon[:len(tampon) - MAX_TAMPON]
                if not recognizer.AcceptWaveform(data):
                    continue

                phrase = json.loads(recognizer.Result()).get("text", "").lower()
                audio_phrase = bytes(tampon)
                tampon.clear()
                if not phrase:
                    continue
                print("Entendu :", phrase)

                m = re.match(r"\s*jarvis\b(.*)", phrase)  # la phrase doit COMMENCER par « Jarvis »
                if not m:
                    continue

                demande = m.group(1).strip()
                etat("ecoute")
                if demande:
                    derniers_textes[:] = [demande]
                    # Retranscription précise de toute la phrase, sans le mot « Jarvis »
                    precise = retirer_nom(transcrire(audio_phrase, phrase))
                    demande = combiner(precise, demande) if precise else demande
                else:
                    bip()                      # signal court : tu peux parler tout de suite
                    recognizer.Reset()
                    vider_audio()
                    demande = ecouter_demande(recognizer, DELAI_ECOUTE_DEMANDE)

                if demande:
                    conversation(demande, recognizer)
                else:
                    speak("Je n'ai rien entendu.")
                    preparer_ecoute(recognizer)
                    etat("veille")
                tampon.clear()

    except KeyboardInterrupt:
        print("\nArrêt de Jarvis.")

    except Exception as error:
        etat("erreur")
        print("\nErreur :", error)


if __name__ == "__main__":
    main()
