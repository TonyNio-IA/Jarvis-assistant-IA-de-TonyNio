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
CODE_ARRET_EXTERIEUR = 0x40010004   # arrêté de l'extérieur (Gestionnaire des tâches, autre programme) : pas un plantage


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
        exterieur = code == CODE_ARRET_EXTERIEUR
        # code 1 sans « Erreur Jarvis » ni « s'arrête de lui-même » juste avant dans le journal : fermé de l'extérieur
        if code == 1 and not exterieur:
            try:
                with open(JOURNAL, encoding="utf-8", errors="replace") as f:
                    f.seek(max(0, os.path.getsize(JOURNAL) - 4000))
                    fin = f.read()
                fin = fin[fin.rfind("===== "):] if "===== " in fin else fin
                if "Erreur Jarvis" not in fin and "s'arrête de lui-même" not in fin and "Traceback" not in fin \
                        and "Fatal Python error" not in fin:
                    exterieur = True
            except OSError:
                pass
        noter((f"Jarvis a été arrêté de l'extérieur (code {code}, sans message d'erreur : sans doute un autre programme)"
               if exterieur else f"Jarvis s'est arrêté tout seul (code {code})") + f" après {time.time() - debut:.0f} s : relance.")
        reprise = os.path.join(DOSSIER, "reprise.json")      # Jarvis dira au redémarrage qu'il s'est relancé
        if not os.path.exists(reprise):                        # (sauf s'il a déjà noté la cause lui-même)
            try:
                with open(reprise, "w", encoding="utf-8") as f:
                    f.write('{"quand": %d, "cause": "%s", "detail": "code %s"}'
                            % (time.time(), "exterieur" if exterieur else "plantage", code))
            except OSError:
                pass
        relances = [t for t in relances if time.time() - t < 600] + [time.time()]
        time.sleep(60 if len(relances) > 5 else 3)


if __name__ == "__main__":
    main()
