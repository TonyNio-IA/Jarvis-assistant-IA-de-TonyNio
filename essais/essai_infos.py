# Essai du module jarvis_infos (sans toucher aux réglages réels : fichier temporaire, ville de test Toulouse).
import datetime, os, sys, tempfile
sys.path.insert(0, r"C:\Jarvis")
import jarvis_infos as i

i.FICHIER = os.path.join(tempfile.gettempdir(), "jarvis_infos_essai.json")
if os.path.exists(i.FICHIER):
    os.remove(i.FICHIER)
i._ville = lambda: ("Toulouse", 43.6045, 1.4442)
i._departement = lambda: "31"

def essai(phrase, enfant=False):
    try:
        r = i.commande(phrase, enfant=enfant)
    except Exception as e:
        r = "!!! ERREUR " + repr(e)
    print(f"« {phrase} »\n   -> {r}")

print("=== POUBELLES")
for p in ["quelle poubelle je sors ce soir ?",
          "la poubelle jaune passe le mercredi des semaines paires",
          "les ordures ménagères passent le lundi et le jeudi",
          "le verre c'est le premier vendredi du mois",
          "les encombrants passent une semaine sur deux le mardi",
          "quelle poubelle je sors ce soir ?",
          "c'est quand le verre ?",
          "c'est quand la poubelle jaune ?",
          "quels sont les jours de ramassage ?",
          "arrête les rappels de poubelles",
          "remets les rappels de poubelles",
          "oublie la poubelle jaune",
          "quels sont les jours de ramassage ?",
          "rappelle-moi de sortir la poubelle à 20 heures"]:
    essai(p)
print("=== VACANCES / FERIES")
for p in ["c'est quand les prochaines vacances ?", "on est en vacances ?", "c'est quand la rentrée ?",
          "c'est quand le prochain jour férié ?", "est-ce que demain est férié ?"]:
    essai(p)
print("=== CARBURANTS")
for p in ["combien coûte le gazole ?", "le prix du sans-plomb 98", "quel est le prix de l'essence ?",
          "c'est quoi le prix du carburant ?", "mon carburant c'est le gazole", "c'est quoi le prix du carburant ?"]:
    essai(p)
print("=== EPHEMERIDE")
for p in ["l'éphéméride", "qu'est-ce qui s'est passé un 14 juillet ?", "qu'est-ce qui s'est passé un 31 février ?"]:
    essai(p)
essai("l'éphéméride", enfant=True)
print("=== NE DOIT PAS REPONDRE (doit donner None)")
for p in ["quelle heure est-il", "mets un minuteur de 10 minutes", "quel temps fait-il demain", "ouvre chrome",
          "ajoute du pain à la liste", "j'aimerais partir en vacances en Espagne", "raconte-moi une histoire",
          "combien font 15 % de 80", "mets de la musique", "ferme la fenêtre", "note que je dois appeler le garage",
          "quel est le prix d'une baguette ?", "les vacances c'était super", "c'est quoi un jour férié ?"]:
    essai(p)
os.remove(i.FICHIER)
