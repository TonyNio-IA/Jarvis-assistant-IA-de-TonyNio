import io, json, sys, os
sys.path.insert(0, r"C:\Jarvis")
import urllib.request
import jarvis_maj as m
vrai = urllib.request.urlopen
ok = True
def verif(nom, c):
    global ok; print(("OK  " if c else "ECHEC ") + nom); ok = ok and c
def faux(rep):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    return lambda req, *a, **k: R(json.dumps(rep(req.full_url)).encode())
liste = [{"tag_name": "v9.98", "prerelease": True, "draft": False, "name": "v9.98 : essai", "body": "",
          "assets": [{"name": "Installer-Jarvis.exe", "browser_download_url": "https://exemple/pre.exe"}]},
         {"tag_name": "v9.99", "draft": True, "name": "brouillon", "body": "", "assets": []},
         {"tag_name": "v1.32", "prerelease": False, "draft": False, "name": "v1.32", "body": "", "assets": []}]
stable = {"tag_name": "v1.32", "prerelease": False, "draft": False, "name": "v1.32", "body": "", "assets": []}
urllib.request.urlopen = faux(lambda u: liste if "per_page" in u else stable)
m._testeur = lambda: False
verif("non testeur : la pré-version est ignorée", m.verifier() is None)
m._testeur = lambda: True
r = m.verifier()
verif("testeur : la pré-version 9.98 est proposée (pas le brouillon 9.99)", r is not None and r[0] == "9.98")
verif("testeur : son installateur et son étiquette sont pris", m._installateur == "https://exemple/pre.exe" and m._etiquette == "v9.98")
urllib.request.urlopen = vrai
m._testeur = lambda: False
try:
    verif("vrai GitHub : à jour en 1.32", m.verifier() is None)
except Exception as e:
    print("GitHub injoignable :", e)
print("TOUT EST BON" if ok else "IL Y A UN PROBLEME")
