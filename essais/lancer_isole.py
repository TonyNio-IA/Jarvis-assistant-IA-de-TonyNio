# -*- coding: utf-8 -*-
"""Lance un ancien essai dans une COPIE temporaire de Jarvis (programmes + config), pour qu'il ne touche jamais
la vraie installation. Usage : python lancer_isole.py essai_xxx.py"""
import glob, os, shutil, subprocess, sys, tempfile
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
copie = tempfile.mkdtemp(prefix="jarvis_isole_")
try:
    for f in glob.glob(os.path.join(racine, "*.py")) + glob.glob(os.path.join(racine, "*.json")) + [os.path.join(racine, "VERSION")]:
        if os.path.isfile(f):
            shutil.copy2(f, copie)
    os.makedirs(os.path.join(copie, "tests"))
    for f in glob.glob(os.path.join(racine, "tests", "*.py")):
        shutil.copy2(f, os.path.join(copie, "tests"))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", TEMP=copie, TMP=copie)
    r = subprocess.run([sys.executable, os.path.join(copie, "tests", sys.argv[1])], cwd=os.path.join(copie, "tests"), env=env)
    sys.exit(r.returncode)
finally:
    shutil.rmtree(copie, ignore_errors=True)
