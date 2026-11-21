# -*- coding: utf-8 -*-
"""Fabrique installateur/jarvis.ico (fenêtres, barre des tâches, installateur) avec le même réacteur que l'application
de la tablette (android/dessin.py). L'ancienne icône est gardée à côté (jarvis_ancienne.ico)."""
import os
import shutil
import struct
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import construire  # noqa: E402
import dessin      # noqa: E402

TAILLES = (16, 24, 32, 48, 64, 128, 256)


def fabriquer(chemin):
    images = []
    for t in TAILLES:
        # petites tailles : réacteur un peu plus grand dans le disque pour rester lisible
        img = dessin.reacteur(t, echelle=0.98 if t <= 32 else 0.94, fond="disque")
        images.append(construire.png(dessin.octets(img)))
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire, donnees = b"", b""
    for t, png in zip(TAILLES, images):
        repertoire += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(png), decalage + len(donnees))
        donnees += png
    with open(chemin, "wb") as f:
        f.write(entete + repertoire + donnees)


if __name__ == "__main__":
    cible = os.path.join(ICI, "..", "installateur", "jarvis.ico")
    ancienne = os.path.join(ICI, "..", "installateur", "jarvis_ancienne.ico")
    if os.path.exists(cible) and not os.path.exists(ancienne):
        shutil.copy2(cible, ancienne)
    fabriquer(cible)
    print("écrit", os.path.abspath(cible), os.path.getsize(cible))
