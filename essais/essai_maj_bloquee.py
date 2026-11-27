import io, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request, subprocess
import jarvis_maj as m
m.FICHIER_SUIVI = os.path.join(os.environ.get("TEMP", "."), "essai_suivi_bloquee.json")
m.ATTENTE_AVANT_INSTALLATION = 0.2
m.disponible = ("9.99", "essai")
ok = True
def verif(nom, cond):
    global ok
    print(("OK  " if cond else "ECHEC ") + nom); ok = ok and cond

class R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
def faux_urlopen(requete, timeout=0):
    return R(b"MZ" + b"x" * 80_000)
urllib.request.urlopen = faux_urlopen
# 1.69 : la mise à jour est accompagnée d'un manifeste signé (sa signature est essayée dans essai_signature_169)
import hashlib
_emp = hashlib.sha256(b"MZ" + b"x" * 80_000).hexdigest().upper()
def faux_manifeste(cible):
    m._manifeste = {"publication": {"Installer-Jarvis.exe": _emp, "Installer-Jarvis.bat": _emp}, "code": {}, "etiquette": "v9.99"}
    return m._manifeste, b"{}", b"signature"
m.charger_manifeste = faux_manifeste

lances = []
drap = []
mode = {"exe_bloque": True, "tout_bloque": False}
def faux_popen(cmd, **k):
    lances.append(cmd)
    if cmd[0].lower().endswith(("explorer.exe", "notepad.exe", "clip")):
        class _Rien:
            def communicate(self, *a, **b): return (b"", b"")
        return _Rien()
    drap.append(k.get("creationflags"))
    if cmd[0].lower().endswith(".exe") and "cmd.exe" not in cmd[0].lower() and mode["exe_bloque"]:
        raise OSError(4551, "Une stratégie de contrôle d'application a bloqué ce fichier")
    if mode["tout_bloque"]:
        raise OSError(4551, "bloqué")
    return None
subprocess.Popen = faux_popen

m.installer(); time.sleep(4.0)
verif("exe bloqué : le .bat est lancé par cmd.exe", any("cmd.exe" in str(c[0]).lower() and str(c[-1]).endswith(".bat") for c in lances))
verif("exe bloqué mais .bat accepté : pas de message d'échec", m.echec_a_dire() is None)

lances.clear(); mode["tout_bloque"] = True
m.installer(); time.sleep(4.0)
phrase = m.echec_a_dire()
verif("tout bloqué : phrase d'échec donnée", bool(phrase) and "bloqué" in phrase)
verif("tout bloqué : le Bloc-notes s'ouvre avec le texte d'aide", any(str(c[0]).lower().endswith("notepad.exe") for c in lances))
verif("le fichier d'aide contient la ligne à coller", m.LIGNE_INSTALLATION in open(os.path.join(os.environ["TEMP"], "Jarvis-aide-Windows.txt"), encoding="utf-8-sig").read())
verif("la console de l'installateur est cachée", drap and all(d == 0x08000000 for d in drap))
verif("la phrase n'est dite qu'une fois", m.echec_a_dire() is None)

lances.clear(); mode.update(exe_bloque=False, tout_bloque=False)
m.installer(); time.sleep(4.0)
verif("cas normal : seul l'exe est lancé", len(lances) == 1 and str(lances[0][0]).endswith("Installer-Jarvis.exe"))
print("RESULTAT :", "TOUT EST BON" if ok else "ECHEC")
