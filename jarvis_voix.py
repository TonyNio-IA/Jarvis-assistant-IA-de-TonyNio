"""
JARVIS - voix naturelle.

Utilise la voix « Henri » de Microsoft (edge-tts, gratuite, nécessite Internet).
Le son est joué directement par Python. Les phrases fréquentes sont préparées à
l'avance. Les longues réponses sont préparées phrase par phrase : Jarvis commence
à parler dès que le premier morceau est prêt, sans attendre tout le texte.
Si la voix en ligne ne répond pas, Jarvis reprend automatiquement l'ancienne
voix de Windows (jarvis_tts.speak), pour ne jamais rester muet.
"""

import asyncio
import hashlib
import random
import json
import os
import queue
import re
import tempfile
import threading
import time

import edge_tts
import numpy as np

from jarvis_tts import speak as voix_windows

try:
    import av
    import sounddevice as sd
except Exception:
    av = sd = None

VOIXS = {"henri": "fr-FR-HenriNeural", "denise": "fr-FR-DeniseNeural"}   # voix d'homme, voix de femme
VITESSE_NORMALE = 12   # en pour cent : 0 = vitesse d'origine du service, 10 = un peu plus rapide
VOIX = VOIXS["henri"]
VITESSE = f"+{VITESSE_NORMALE}%"
FICHIER_REGLAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reglages_voix.json")   # reste sur ce PC
try:
    with open(FICHIER_REGLAGES, encoding="utf-8-sig") as _f:
        _r = json.load(_f)
    VOIX = VOIXS.get(_r.get("voix"), VOIX)
    VITESSE = f"{int(_r.get('vitesse', VITESSE_NORMALE)):+d}%"
    _nuit_lue = _r.get("nuit")
except (OSError, ValueError, TypeError, AttributeError):
    _nuit_lue = None


def _enregistrer_reglages():
    """Garde la voix, la vitesse et le mode nuit pour la prochaine fois (fichier qui reste sur ce PC)."""
    try:
        nom = next(n for n, v in VOIXS.items() if v == VOIX)
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as f:
            json.dump({"voix": nom, "vitesse": int(VITESSE.rstrip("%")), "nuit": _nuit_forcee}, f)
    except OSError as erreur:
        print("Réglages de la voix non enregistrés :", erreur)


def regler_voix(voix=None, vitesse=None):
    """Change la voix (« henri » ou « denise ») et/ou la vitesse (en pour cent), et les garde pour la prochaine fois."""
    global VOIX, VITESSE
    if voix:
        VOIX = VOIXS[voix]
    if vitesse is not None:
        VITESSE = f"{max(-30, min(50, int(vitesse))):+d}%"
    _cache.clear()                      # les phrases déjà prêtes avaient l'ancienne voix
    _enregistrer_reglages()


# ----- Mode nuit : Jarvis répond par écrit au-dessus du réacteur, sans parler ni biper (sauf rappels) -----
# Par défaut, il ne s'active QUE quand on le demande (« active le mode nuit ») et reste actif, même après
# un redémarrage, jusqu'à « désactive le mode nuit ». Des horaires automatiques restent possibles
# si on les met dans config.json ("mode_nuit": {"debut": 22, "fin": 7}).
import jarvis_config
afficher = None          # fonction qui écrit un texte dans la fenêtre de discussion (donnée par jarvis_claude)
_garde_affichage = 0.0   # jusqu'à ce moment, ce que Jarvis dit ne remplace pas le texte affiché


def montrer(texte, garder=20):
    """Affiche un texte sans le dire (un code du Wi-Fi invité, par exemple) et le garde à l'écran « garder »
    secondes : la phrase que Jarvis dit ensuite ne le remplace pas. Renvoie True si le texte est affiché."""
    global _garde_affichage
    if not afficher:
        return False
    afficher(texte)
    _garde_affichage = time.time() + garder
    return True


_nuit_forcee = _nuit_lue if isinstance(_nuit_lue, bool) else None   # choix dit à la voix (gardé dans reglages_voix.json)


def _nuit_horaire():
    heures = jarvis_config.HEURES_NUIT
    if not heures:
        return False
    debut, fin = heures
    h = time.localtime().tm_hour
    return (debut <= h or h < fin) if debut > fin else (debut <= h < fin)


def mode_nuit():
    """Vrai si Jarvis doit rester silencieux en ce moment."""
    global _nuit_forcee
    if not jarvis_config.HEURES_NUIT:
        return bool(_nuit_forcee)       # sans horaires : seulement sur demande
    horaire = _nuit_horaire()
    if _nuit_forcee is not None and _nuit_forcee == horaire:
        _nuit_forcee = None             # l'horaire a rejoint le choix dit à la voix : on revient à l'horaire
        _enregistrer_reglages()
    return horaire if _nuit_forcee is None else _nuit_forcee


def forcer_nuit(actif):
    global _nuit_forcee
    if not jarvis_config.HEURES_NUIT:
        _nuit_forcee = bool(actif)
    else:
        _nuit_forcee = None if actif == _nuit_horaire() else bool(actif)
    _enregistrer_reglages()


FREQ = 24000        # fréquence du son fourni par edge-tts
DOSSIER_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_voix")
TAILLE_MORCEAU = 220   # longueur (en caractères) des morceaux d'une longue réponse

niveau = 0.0        # volume de la voix à cet instant (0 à 1), lu par le réacteur
spectre = None      # spectre de la voix à cet instant (16 bandes de 0 à 1, graves d'abord), lu par le réacteur
NB_BANDES = 16


def bandes_spectre(blocs, freq, nb=NB_BANDES):
    """Spectre de chaque bloc de son (une ligne par bloc), réparti en « nb » bandes du grave à l'aigu."""
    taille = blocs.shape[1]
    amplitudes = np.abs(np.fft.rfft(blocs * np.hanning(taille), axis=1))
    limites = np.geomspace(90.0, min(7000.0, freq / 2 - 1), nb + 1) * taille / freq
    limites = np.maximum(np.arange(1, nb + 2), limites.astype(int))     # au moins une case par bande
    limites = np.minimum(limites, amplitudes.shape[1] - 1)
    return np.stack([amplitudes[:, limites[i]:max(limites[i] + 1, limites[i + 1])].max(axis=1)
                     for i in range(nb)], axis=1)

_cache = {}         # phrase -> son déjà prêt
# Le morceau en train d'être dit : l'écoute de « Jarvis » pendant la parole ignore le mot seulement quand Jarvis
# le prononce lui-même (écho du haut-parleur), pas pendant toute une longue réponse.
morceau_en_cours = ""
numero_morceau = 0
debut_morceau = 0.0


VARIATION_VOIX = True    # chaque phrase prend un ton et un rythme très légèrement différents : plus naturel


# En mode enfant, Jarvis parle avec une voix d'enfant : Eloise, une petite fille (hauteur mesurée vers 314 Hz,
# contre 205 Hz pour Denise et 130 Hz pour Henri). Il n'y a pas de voix de petit garçon en français.
VOIX_ENFANT = "fr-FR-EloiseNeural"
VOIX_ENFANT_ACTIVE = True       # False : le mode enfant garde la voix habituelle


def voix_enfant_active():
    """Vrai quand le mode enfant est en marche sur le PC (et que la voix d'enfant n'a pas été coupée)."""
    if not VOIX_ENFANT_ACTIVE:
        return False
    try:
        import jarvis_enfant
        return jarvis_enfant.actif()
    except Exception:
        return False


def voix_du_moment():
    return VOIX_ENFANT if voix_enfant_active() else VOIX


async def _generer(texte, fichier, varier=False, voix=None):
    vitesse, hauteur = VITESSE, "+0Hz"
    if varier and VARIATION_VOIX:
        vitesse = f"{int(VITESSE.rstrip('%')) + random.choice((-3, 0, 0, 3)):+d}%"
        hauteur = random.choice(("-2Hz", "+0Hz", "+0Hz", "+2Hz"))
    await edge_tts.Communicate(texte, voix or voix_du_moment(), rate=vitesse, pitch=hauteur).save(fichier)


# ----- Histoires à deux voix : les répliques écrites entre ⟨ et ⟩ sont dites avec l'autre voix -----
OUVRE_AUTRE_VOIX, FERME_AUTRE_VOIX = "⟨", "⟩"


def autre_voix(enfant=None):
    """La voix de l'autre personnage : Denise si Jarvis parle avec Henri, Henri sinon (et Henri face à la voix d'enfant)."""
    if voix_enfant_active() if enfant is None else enfant:
        return VOIXS["henri"]
    return VOIXS["denise"] if VOIX == VOIXS["henri"] else VOIXS["henri"]


def sans_balises_voix(texte):
    return texte.replace(OUVRE_AUTRE_VOIX, "").replace(FERME_AUTRE_VOIX, "")


def _morceaux_et_voix(texte):
    """[(morceau, voix)] : le texte découpé en phrases, avec la voix de chaque passage."""
    if OUVRE_AUTRE_VOIX not in texte:
        return [(m, None) for m in (_decouper(texte) or [texte])]
    resultat = []
    for i, passage in enumerate(re.split(r"[⟨⟩]", texte)):
        if passage.strip():
            voix = autre_voix() if i % 2 == 1 else None
            resultat += [(m, voix) for m in (_decouper(passage) or [passage.strip()])]
    return resultat


def _decoder(fichier):
    """Transforme le MP3 en échantillons prêts à jouer."""
    reechant = av.AudioResampler(format="s16", layout="mono", rate=FREQ)
    morceaux = []
    with av.open(fichier) as conteneur:
        for trame in conteneur.decode(audio=0):
            for sortie in reechant.resample(trame):
                morceaux.append(sortie.to_ndarray().flatten())
    return np.concatenate(morceaux).astype(np.int16)


def _jouer_echantillons(echantillons, freq=FREQ, interruption=None):
    """Joue le son. Si « interruption() » devient vraie, coupe et renvoie True."""
    global niveau, spectre
    pas = max(1, int(freq * 0.03))
    flottant = echantillons.astype(np.float32) / 32768.0
    absolu = np.abs(flottant)
    n = len(absolu) // pas
    enveloppe = absolu[:n * pas].reshape(n, pas).max(axis=1) if n else np.zeros(1)
    try:                                   # spectre de chaque instant, pour la couronne du réacteur
        spectres = bandes_spectre(flottant[:n * pas].reshape(n, pas), freq) if n else None
        if spectres is not None:
            spectres = np.sqrt(spectres / max(1e-9, float(np.percentile(spectres, 99))))
            spectres = np.clip(spectres, 0, 1)
    except Exception:
        spectres = None
    duree = len(echantillons) / freq
    sd.play(echantillons, freq)
    debut = time.time()
    try:
        while True:
            ecoule = time.time() - debut
            if ecoule >= duree:
                break
            instant = int(ecoule / 0.03)
            niveau = float(enveloppe[min(len(enveloppe) - 1, instant)])
            if spectres is not None:
                spectre = spectres[min(len(spectres) - 1, instant)]
            if interruption is not None and interruption():
                sd.stop()
                return True
            time.sleep(0.03)
        sd.wait()
        return False
    finally:
        niveau = 0.0
        spectre = None


def _son_pour(texte, varier=False, voix=None):
    """Prépare le son d'un texte (génération en ligne + décodage)."""
    nom = hashlib.md5(texte.encode("utf-8")).hexdigest()[:12]
    fichier = os.path.join(tempfile.gettempdir(), f"jarvis_{nom}_{threading.get_ident()}.mp3")
    try:
        asyncio.run(_generer(texte, fichier, varier, voix))
        return _decoder(fichier)
    finally:
        try:
            os.remove(fichier)
        except OSError:
            pass


def preparer(phrases):
    """Prépare à l'avance les phrases fréquentes. Elles sont gardées sur le disque
    (dossier cache_voix) : aux démarrages suivants, plus besoin d'Internet pour elles."""
    if av is None:
        return
    os.makedirs(DOSSIER_CACHE, exist_ok=True)
    for texte in phrases:
        cle = hashlib.md5(f"{VOIX}|{VITESSE}|{texte}".encode("utf-8")).hexdigest()[:16]
        fichier = os.path.join(DOSSIER_CACHE, cle + ".npy")
        try:
            if os.path.exists(fichier):
                _cache[texte] = np.load(fichier)
            else:
                _cache[texte] = _son_pour(texte)
                np.save(fichier, _cache[texte])
        except Exception as erreur:
            print("Phrase non préparée :", texte, erreur)


NOTES_BIP = ((880, 0.09), (1320, 0.13))    # les deux notes du bip : (fréquence, durée)


VOLUME_BIP = 0.4     # 0 à 1 (0,25 avant le 17/11/2026 : trop faible ; 0,6 encore un peu faible)


def bip(attendre=True, toujours=False):
    """Petit son de réveil (deux notes montantes), presque instantané.
    attendre=False : le son est lancé et l'on rend la main aussitôt (l'écoute démarre pendant le bip).
    En mode nuit, pas de bip, sauf pour un rappel (toujours=True)."""
    if sd is None or (mode_nuit() and not toujours):
        return
    try:
        freq = 44100
        notes = []
        for hz, duree in NOTES_BIP:
            t = np.linspace(0, duree, int(freq * duree), endpoint=False)
            enveloppe = np.minimum(1, np.minimum(t / 0.008, (duree - t) / 0.03))
            notes.append(VOLUME_BIP * np.sin(2 * np.pi * hz * t) * enveloppe)
        sd.play(np.concatenate(notes).astype(np.float32), freq)
        if attendre:
            sd.wait()
    except Exception as erreur:
        print("Bip impossible :", erreur)


NOTES_FIN_ECOUTE = ((988, 0.05), (659, 0.09))   # « j'ai entendu » : deux notes douces qui descendent
VOLUME_FIN_ECOUTE = 0.56                          # en proportion de VOLUME_BIP : bien plus discret que le bip


def bip_fin_ecoute():
    """Petit son léger quand Jarvis arrête d'écouter (ta demande est entendue), différent du bip de réveil.
    Sans attendre : la retranscription commence pendant qu'il sonne. Pas en mode nuit."""
    if sd is None or mode_nuit() or not VOLUME_FIN_ECOUTE:
        return
    try:
        freq = 44100
        notes = []
        for hz, duree in NOTES_FIN_ECOUTE:
            t = np.linspace(0, duree, int(freq * duree), endpoint=False)
            enveloppe = np.minimum(1, t / 0.005) * np.exp(-t * 22)        # attaque douce, s'éteint vite
            notes.append(VOLUME_FIN_ECOUTE * VOLUME_BIP * np.sin(2 * np.pi * hz * t) * enveloppe)
        sd.play(np.concatenate(notes).astype(np.float32), freq)
    except Exception as erreur:
        print("Son de fin d'écoute impossible :", erreur)


NOTES_FIN = ((1568, 0.07), (1319, 0.07), (1047, 0.16))   # petit carillon descendant : « c'est prêt »


def son_fini():
    """Petit carillon joué quand une longue tâche est terminée, juste avant la réponse (pas en mode nuit)."""
    if sd is None or mode_nuit():
        return
    try:
        freq = 44100
        notes = []
        for hz, duree in NOTES_FIN:
            t = np.linspace(0, duree, int(freq * duree), endpoint=False)
            enveloppe = np.minimum(1, t / 0.006) * np.exp(-t * 9)
            notes.append(0.25 * np.sin(2 * np.pi * hz * t) * enveloppe)
        sd.play(np.concatenate(notes).astype(np.float32), freq)
        sd.wait()
    except Exception as erreur:
        print("Son de fin impossible :", erreur)


def _decouper(texte):
    """Découpe un long texte en morceaux d'une ou plusieurs phrases."""
    phrases = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texte) if p.strip()]
    morceaux, courant = [], ""
    for phrase in phrases:
        if courant and len(courant) + len(phrase) > TAILLE_MORCEAU:
            morceaux.append(courant)
            courant = phrase
        else:
            courant = (courant + " " + phrase).strip()
    if courant:
        morceaux.append(courant)
    return morceaux


def _morceau(texte):
    global morceau_en_cours, numero_morceau, debut_morceau
    morceau_en_cours, debut_morceau = sans_balises_voix(texte or ""), time.time()
    numero_morceau += 1


def speak(texte, interruption=None, toujours=False):
    """Fait parler Jarvis avec la voix naturelle (ou la voix Windows en secours).
    Si « interruption » est donnée, la lecture peut être coupée : renvoie alors True.
    En mode nuit, le texte est seulement écrit dans la fenêtre de discussion, sauf pour un rappel (toujours=True)."""
    if not texte:
        return False
    a_deux_voix = OUVRE_AUTRE_VOIX in texte
    if a_deux_voix and (mode_nuit() and not toujours or av is None or sd is None):
        texte = sans_balises_voix(texte)
    # Ce que Jarvis dit s'écrit aussi dans la fenêtre de discussion (sauf si un texte à garder y est affiché)
    if afficher and time.time() >= _garde_affichage:
        try:
            afficher(sans_balises_voix(texte))
        except Exception:
            pass
    if mode_nuit() and not toujours:
        print("JARVIS (mode nuit, sans voix) :", texte)
        time.sleep(min(5.0, 1.0 + len(texte) / 40))       # le temps de lire le début
        return False
    print("JARVIS :", sans_balises_voix(texte))
    if av is None or sd is None:
        voix_windows(texte)
        return False
    if texte in _cache and not voix_enfant_active():   # les phrases préparées sont dans la voix habituelle
        try:
            _morceau(texte)
            return _jouer_echantillons(_cache[texte], interruption=interruption)
        except Exception as erreur:
            print("Lecture directe impossible :", erreur)

    avec_voix = _morceaux_et_voix(texte)
    morceaux = [m for m, _ in avec_voix]
    sons = queue.Queue()
    arret = threading.Event()

    def fabriquer():
        for morceau, voix in avec_voix:
            if arret.is_set():
                return
            try:
                sons.put(_son_pour(morceau, varier=True, voix=voix))
            except Exception as erreur:
                sons.put(erreur)
                return
        sons.put(None)

    threading.Thread(target=fabriquer, daemon=True).start()
    deja_dit = 0
    try:
        while True:
            son = sons.get()
            if son is None:
                return False
            if isinstance(son, Exception):
                print("Voix naturelle indisponible (", son, ") : voix Windows utilisée.")
                voix_windows(" ".join(morceaux[deja_dit:]))
                return False
            _morceau(morceaux[deja_dit] if deja_dit < len(morceaux) else "")
            if _jouer_echantillons(son, interruption=interruption):
                return True
            deja_dit += 1
    finally:
        arret.set()


if __name__ == "__main__":
    bip()
    speak("Bonjour. Je parle maintenant avec ma nouvelle voix. "
          "Les longues réponses sont préparées morceau par morceau, pour commencer plus vite.")
