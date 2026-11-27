import sys, time; sys.path.insert(0, r"C:\Jarvis")
import jarvis_rapports as r, jarvis_tablette as t
notes = []
r.noter = lambda genre, **i: notes.append((genre, i))
t.mode_essai = lambda: False
t._rapport_tablette("raconte-moi une histoire de pirates", "claude", time.time() - 2, {"enfant": True})
t._rapport_tablette("quelle heure est-il", "local", time.time() - 0.3, {"enfant": False})
t._rapport_tablette("c'est quoi la capitale du Pérou", "claude", time.time() - 4, {"enfant": False}, reponse="Lima.")
for g, i in notes: print(g, i)
enfant_textes = [i for g, i in notes[:1]]
print("enfant : aucun texte envoyé :", all("demande" not in i and "texte" not in i for g, i in notes[:1]) and len([n for n in notes if n[0]=="demande_claude"]) == 1)
