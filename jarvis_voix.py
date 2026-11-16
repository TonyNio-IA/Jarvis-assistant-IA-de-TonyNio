"""
JARVIS - voix naturelle.

Utilise la voix « Henri » de Microsoft (edge-tts, gratuite, nécessite Internet).
Le son est joué directement par Python (plus rapide qu'en passant par PowerShell).
Les phrases fréquentes sont préparées à l'avance pour être dites sans délai.
Si la voix en ligne ne répond pas, Jarvis reprend automatiquement l'ancienne
voix de Windows (jarvis_tts.speak), pour ne jamais rester muet.
"""

import asyncio
import hashlib
import os
import subprocess
import tempfile

import edge_tts
import numpy as np

from jarvis_tts import speak as voix_windows

try:
    import av
    import sounddevice as sd
except Exception:
    av = sd = None

VOIX = "fr-FR-HenriNeural"
VITESSE = "+5%"     # "+0%" = normal, "+10%" = un peu plus rapide, "-10%" = plus lent
FREQ = 24000        # fréquence du son fourni par edge-tts

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


def _jouer_echantillons(echantillons, freq=FREQ):
    sd.play(echantillons, freq)
    sd.wait()


def _jouer_powershell(fichier):
    script = (
        "Add-Type -AssemblyName PresentationCore; "
        "$p = New-Object System.Windows.Media.MediaPlayer; "
        "$p.Open([uri]$env:JARVIS_AUDIO); "
        "$t = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $t -lt 50) "
        "{ Start-Sleep -Milliseconds 100; $t++ }; "
        "$p.Play(); "
        "Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 200); "
        "$p.Close()"
    )
    env = os.environ.copy()
    env["JARVIS_AUDIO"] = fichier
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _fichier_pour(texte):
    nom = hashlib.md5(texte.encode("utf-8")).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"jarvis_{nom}.mp3")


def preparer(phrases):
    """Prépare à l'avance les phrases fréquentes (au démarrage de Jarvis)."""
    if av is None:
        return
    for texte in phrases:
        try:
            fichier = _fichier_pour(texte)
            asyncio.run(_generer(texte, fichier))
            _cache[texte] = _decoder(fichier)
            os.remove(fichier)
        except Exception as erreur:
            print("Phrase non préparée :", texte, erreur)


def bip():
    """Petit son de réveil (deux notes montantes), presque instantané."""
    if sd is None:
        return
    try:
        freq = 44100
        notes = []
        for hz, duree in ((880, 0.07), (1320, 0.10)):
            t = np.linspace(0, duree, int(freq * duree), endpoint=False)
            enveloppe = np.minimum(1, np.minimum(t / 0.008, (duree - t) / 0.03))
            notes.append(0.25 * np.sin(2 * np.pi * hz * t) * enveloppe)
        _jouer_echantillons(np.concatenate(notes).astype(np.float32), freq)
    except Exception as erreur:
        print("Bip impossible :", erreur)


def speak(texte):
    """Fait parler Jarvis avec la voix naturelle (ou la voix Windows en secours)."""
    if not texte:
        return
    if texte in _cache and sd is not None:
        print("JARVIS :", texte)
        try:
            _jouer_echantillons(_cache[texte])
            return
        except Exception as erreur:
            print("Lecture directe impossible :", erreur)
    fichier = _fichier_pour(texte)
    try:
        asyncio.run(_generer(texte, fichier))
    except Exception as erreur:
        print("Voix naturelle indisponible (", erreur, ") : voix Windows utilisée.")
        voix_windows(texte)
        return
    print("JARVIS :", texte)
    try:
        if av is None:
            raise RuntimeError("lecture directe indisponible")
        _jouer_echantillons(_decoder(fichier))
    except Exception as erreur:
        print("Lecture directe impossible (", erreur, ") : lecture par PowerShell.")
        try:
            _jouer_powershell(fichier)
        except Exception:
            voix_windows(texte)
    finally:
        try:
            os.remove(fichier)
        except OSError:
            pass


if __name__ == "__main__":
    bip()
    speak("Bonjour TonyNio. Je parle maintenant avec ma nouvelle voix.")
