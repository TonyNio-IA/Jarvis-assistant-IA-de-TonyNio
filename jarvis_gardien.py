"""
JARVIS - gardien.

C'est lui que le raccourci lance. Il démarre Jarvis (jarvis_reacteur.py) et le surveille :
  - si Jarvis plante ou perd le micro, il le relance tout seul ;
  - si tu choisis « Arrêter Jarvis » (clic droit sur le réacteur), il s'arrête aussi ;
  - « Jarvis, redémarre-toi » relance Jarvis proprement.
Après 5 relances en 10 minutes, il attend une minute entre deux essais, pour ne pas tourner en rond.
"""

import os
import socket
import subprocess
import sys
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(DOSSIER, "jarvis.log")
CODE_REDEMARRER = 3          # Jarvis demande lui-même à être relancé


def noter(message):
    try:
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(f"[gardien {time.strftime('%d/%m %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def main():
    verrou = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        verrou.bind(("127.0.0.1", 47822))          # un seul gardien à la fois
    except OSError:
        return
    environnement = dict(os.environ, JARVIS_GARDIEN="1")
    relances = []
    while True:
        debut = time.time()
        code = subprocess.call([sys.executable, os.path.join(DOSSIER, "jarvis_reacteur.py")],
                               cwd=DOSSIER, env=environnement)
        if code == 0:
            return                                 # arrêt demandé (ou Jarvis tournait déjà)
        if code == CODE_REDEMARRER:
            noter("redémarrage demandé à la voix.")
            time.sleep(1)
            continue
        noter(f"Jarvis s'est arrêté tout seul (code {code}) après {time.time() - debut:.0f} s : relance.")
        relances = [t for t in relances if time.time() - t < 600] + [time.time()]
        time.sleep(60 if len(relances) > 5 else 3)


if __name__ == "__main__":
    main()
