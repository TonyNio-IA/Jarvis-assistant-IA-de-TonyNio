# -*- coding: utf-8 -*-
"""Lance un ANCIEN essai (non isolé) à l'intérieur du bac à sable : programmes, réseau, clavier, souris, fenêtres, son,
presse-papiers et registre sont bloqués, et Jarvis travaille sur une copie provisoire de ses fichiers.
    python lancer_dans_bac.py essai_xxx.py
En plus du bac à sable : tout « import jarvis_… » vient de la copie (jamais de C:\\Jarvis), et un « os.chdir(C:\\Jarvis) »
de l'essai est renvoyé vers la copie."""
import importlib.abc, importlib.util, os, runpy, sys
ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import bac_a_sable as b          # (bloque tout, puis charge Jarvis depuis la copie)

VRAI = os.path.normcase(os.path.normpath(b.SOURCE))
_chdir = os.chdir


def _chdir_garde(chemin):
    c = os.path.normcase(os.path.normpath(os.path.abspath(chemin)))
    _chdir(b.DOSSIER if c == VRAI else chemin)


os.chdir = _chdir_garde


class _Copie(importlib.abc.MetaPathFinder):
    def find_spec(self, nom, chemin=None, cible=None):
        if nom.startswith("jarvis_") and "." not in nom:
            fichier = os.path.join(b.DOSSIER, nom + ".py")
            if os.path.exists(fichier):
                return importlib.util.spec_from_file_location(nom, fichier)
        return None


sys.meta_path.insert(0, _Copie())
essai = os.path.join(ICI, sys.argv[1])
sys.argv = [essai] + sys.argv[2:]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
runpy.run_path(essai, run_name="__main__")
