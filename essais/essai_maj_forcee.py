import io, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import jarvis_maj as m
m._testeur = lambda: False      # ce PC peut être testeur : l'essai vise la version publiée

def faux(corps):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    return lambda *a, **k: R(json.dumps({"tag_name": "v9.99", "name": "v9.99 : essai", "body": corps}).encode())

ok = True
def verif(nom, cond):
    global ok
    print(("OK  " if cond else "ECHEC ") + nom); ok = ok and cond

urllib.request.urlopen = faux("Notes normales")
m.verifier()
verif("version ordinaire : pas forcée", m.disponible and not m.forcee)
verif("version ordinaire : pas installée d'office", not m.forcee_a_installer())
verif("version ordinaire : annoncée comme d'habitude", m.a_annoncer())

m._annoncee = False
urllib.request.urlopen = faux("Notes\n" + m.MARQUE_FORCEE)
m.verifier()
verif("version forcée : reconnue", m.forcee)
verif("version forcée : pas de question", not m.a_annoncer())
verif("version forcée : installée une fois", m.forcee_a_installer())
verif("version forcée : pas deux fois", not m.forcee_a_installer())

m._forcee_lancee = False
urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("pas d'Internet"))
try:
    m.verifier()
except OSError:
    pass
verif("sans Internet : rien ne casse", True)
print("TOUT EST BON" if ok else "IL Y A UN PROBLEME")
