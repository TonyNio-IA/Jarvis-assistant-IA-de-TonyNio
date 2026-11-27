# -*- coding: utf-8 -*-
"""Le son enregistré par l'application Android (AAC dans un fichier MP4, 16 kHz) est-il bien lu par la tablette ?
Un son d'une seconde est fabriqué dans ce format, puis décodé comme une vraie demande. Rien n'est gardé."""
import io
import os
import sys

sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
sys.stdout.reconfigure(encoding="utf-8")
import av
import numpy as np
import jarvis_tablette as t

tampon = io.BytesIO()
with av.open(tampon, "w", format="mp4") as sortie:
    flux = sortie.add_stream("aac", rate=16000)
    flux.bit_rate = 64000
    son = (0.3 * np.sin(2 * np.pi * 220 * np.arange(16000) / 16000)).astype(np.float32)
    for debut in range(0, 16000, 1024):
        morceau = son[debut:debut + 1024]
        if len(morceau) < 1024:
            morceau = np.pad(morceau, (0, 1024 - len(morceau)))
        trame = av.AudioFrame.from_ndarray(morceau.reshape(1, -1), format="fltp", layout="mono")
        trame.sample_rate = 16000
        for paquet in flux.encode(trame):
            sortie.mux(paquet)
    for paquet in flux.encode(None):
        sortie.mux(paquet)
octets = tampon.getvalue()
audio = t._decoder(octets)
bon = 14000 < len(audio) < 19000 and float(np.max(np.abs(audio))) > 0.15
print(("OK    " if bon else "ECHEC ") + f"MP4/AAC de {len(octets)} octets : {len(audio)} échantillons, crête {float(np.max(np.abs(audio))):.2f}")
print("erreurs :", 0 if bon else 1)
