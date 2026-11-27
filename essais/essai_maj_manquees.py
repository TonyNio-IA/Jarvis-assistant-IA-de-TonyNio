import io, json, sys
sys.path.insert(0, r"C:\Jarvis")
import urllib.request
import jarvis_maj as m
m._testeur = lambda: False
m.version_actuelle = lambda: "1.30"
def faux(rep):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    return lambda req, *a, **k: R(json.dumps(rep(req.full_url)).encode())
M = m.MARQUE_FORCEE
liste = [{"tag_name": "v1.33", "body": "normale"}, {"tag_name": "v1.32", "body": M}, {"tag_name": "v1.31", "body": M}, {"tag_name": "v1.30", "body": ""}]
urllib.request.urlopen = faux(lambda u: liste if "per_page" in u else liste[0])
m.verifier(); print("1.30 -> derniere 1.33 normale, 1.31/1.32 forcees manquees :", m.disponible, "forcee =", m.forcee)
m.version_actuelle = lambda: "1.32"
m.verifier(); print("1.32 -> 1.33 normale (rien de force manque) :", m.disponible, "forcee =", m.forcee)
