import sys, os
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
import jarvis_commandes as c, jarvis_extras as x, jarvis_vigilance as v, jarvis_accueil as a
import tempfile, shutil
_essai = tempfile.mkdtemp()
if os.path.exists(x.FICHIER_RECETTE):
    shutil.copy(x.FICHIER_RECETTE, os.path.join(_essai, 'recette.json'))
x.FICHIER_RECETTE = os.path.join(_essai, 'recette.json')   # jamais la vraie recette en cours
def essai(phrase):
    try:
        r = c.commande_instantanee([phrase])
    except Exception as e:
        r = "ERREUR " + repr(e)
    print(f"{phrase!r} -> {r!r}")
for p in ["quelle heure est-il à Tokyo", "quelle heure est-il à New York", "quelle heure est-il",
          "c'est quoi mon dernier téléchargement", "y a-t-il une alerte météo", "étape suivante",
          "quels sont les prochains anniversaires", "quand est l'anniversaire de Marie",
          "active le mode invité", "lis mes mails", "lis mes notes", "quel temps fait-il", "désactive le mode invité",
          "ferme tout", "non", "le mode cinéma est activé ?", "avant de 30 secondes", "recule de dix secondes"]:
    essai(p)
print("departement trouvé:", bool(v.departement()))
print("accueil fini pour cet utilisateur:", a._lire().get("fini"), "question:", repr(a.question()))
