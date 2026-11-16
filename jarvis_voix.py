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

VOIX = "fr-FR-HenriNeural"
VITESSE = "+12%"    # "+0%" = normal, "+10%" = un peu plus rapide, "-10%" = plus lent
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


async def _generer(texte, fichier):
    await edge_tts.Communicate(texte, VOIX, rate=VITESSE).save(fichier)


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


def _son_pour(texte):
    """Prépare le son d'un texte (génération en ligne + décodage)."""
    nom = hashlib.md5(texte.encode("utf-8")).hexdigest()[:12]
    fichier = os.path.join(tempfile.gettempdir(), f"jarvis_{nom}_{threading.get_ident()}.mp3")
    try:
        asyncio.run(_generer(texte, fichier))
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


NOTES_BIP = ((880, 0.07), (1320, 0.10))    # les deux notes du bip : (fréquence, durée)


def bip(attendre=True):
    """Petit son de réveil (deux notes montantes), presque instantané.
    attendre=False : le son est lancé et l'on rend la main aussitôt (l'écoute démarre pendant le bip)."""
    if sd is None:
        return
    try:
        freq = 44100
        notes = []
        for hz, duree in NOTES_BIP:
            t = np.linspace(0, duree, int(freq * duree), endpoint=False)
            enveloppe = np.minimum(1, np.minimum(t / 0.008, (duree - t) / 0.03))
            notes.append(0.25 * np.sin(2 * np.pi * hz * t) * enveloppe)
        sd.play(np.concatenate(notes).astype(np.float32), freq)
        if attendre:
            sd.wait()
    except Exception as erreur:
        print("Bip impossible :", erreur)


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


def speak(texte, interruption=None):
    """Fait parler Jarvis avec la voix naturelle (ou la voix Windows en secours).
    Si « interruption » est donnée, la lecture peut être coupée : renvoie alors True."""
    if not texte:
        return False
    print("JARVIS :", texte)
    if av is None or sd is None:
        voix_windows(texte)
        return False
    if texte in _cache:
        try:
            return _jouer_echantillons(_cache[texte], interruption=interruption)
        except Exception as erreur:
            print("Lecture directe impossible :", erreur)

    morceaux = _decouper(texte) or [texte]
    sons = queue.Queue()
    arret = threading.Event()

    def fabriquer():
        for morceau in morceaux:
            if arret.is_set():
                return
            try:
                sons.put(_son_pour(morceau))
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
            if _jouer_echantillons(son, interruption=interruption):
                return True
            deja_dit += 1
    finally:
        arret.set()


if __name__ == "__main__":
    bip()
    speak("Bonjour TonyNio. Je parle maintenant avec ma nouvelle voix. "
          "Les longues réponses sont préparées morceau par morceau, pour commencer plus vite.")
