import importlib, tempfile, os, sys
sys.path.insert(0, r"C:\Jarvis")
import jarvis_ateliers as a
d = tempfile.mkdtemp(); p = {"id": "essai_redemarrage", "enfant": True, "prenom": ""}
r = a.traiter("on fait de la dictée", p, d)
print("depart:", r["reponse"][:70])
a = importlib.reload(a)                       # comme un redémarrage de Jarvis
print("repris apres redemarrage:", a.en_cours("essai_redemarrage"))
r2 = a.traiter("chat", p, d)
print("reponse apres redemarrage:", (r2 or {}).get("reponse", "AUCUNE")[:80])
a.arreter("essai_redemarrage"); a = importlib.reload(a)
print("apres arret, oublie:", not a.en_cours("essai_redemarrage"))
