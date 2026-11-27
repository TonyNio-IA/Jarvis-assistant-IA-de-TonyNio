# Mode enfant simulé (sans toucher enfant.json) : aucune demande ne doit ouvrir le YouTube ordinaire
import sys, os
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
import jarvis_commandes as c, jarvis_enfant as e, jarvis_web as w
ouverts = []
e.actif = lambda: True
e._ouvrir = lambda a: ouverts.append(a)
os.startfile = lambda a: ouverts.append(a)
w.navigateur_actif = lambda: False
for q in ["mes mots en vidéo", "mes mois la vidéo de mike et chichi est sur youtube kids", "may youtube kids",
          "mais la 3ème vidéo", "mets de la musique", "mets la reine des neiges", "joue une chanson de pirates",
          "mets une vidéo de dinosaures"]:
    avant = len(ouverts)
    r = c.commande_instantanee([q])
    print(f"{q!r} -> {r!r} | ouvert: {ouverts[avant:]}")
print("YouTube ordinaire ouvert :", any("youtube.com/" in a and "youtubekids" not in a for a in ouverts))
