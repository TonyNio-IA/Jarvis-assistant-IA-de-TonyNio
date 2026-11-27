import sys
sys.path.insert(0, r"C:\Jarvis")
import jarvis_voix, jarvis_config
import jarvis_commandes as jc
import jarvis_reglages as jr

echecs = 0


def verif(nom, ok, detail=""):
    global echecs
    print(("OK   " if ok else "ECHEC"), nom, "->", str(detail)[:140])
    echecs += not ok


def ci(x):
    return jc.commande_instantanee([x])


MARQUE = "mode nuit, donc je réponds par écrit"
# on n'écrit rien sur le disque : on neutralise l'enregistrement des réglages
jarvis_voix._enregistrer_reglages = lambda: None

# 1) mode nuit actif (sans horaires) : les phrases du vrai utilisateur reçoivent l'explication
jarvis_config.HEURES_NUIT = None
jarvis_voix.forcer_nuit(True)
for ph in ["parle un peu", "Jarvis, parle un peu", "ralumer le micro", "rallume le micro", "tu ne parles plus",
           "pourquoi tu ne parles pas", "pourquoi tu réponds par écrit", "je t'entends pas",
           "réponds-moi à l'oral", "pourquoi tu parles plus"]:
    r = ci(ph)
    verif("nuit: " + ph, isinstance(r, str) and 'mode nuit' in r and 'écrit' in r, r)

# 2) avec horaires automatiques : le message ajoute le réglage
jarvis_config.HEURES_NUIT = (0, 24)
jarvis_voix._nuit_forcee = None
r = ci("parle un peu")
verif("nuit auto: mentionne le réglage", isinstance(r, str) and "Mode nuit automatique" in r, r)

# 3) les commandes voisines ne sont pas détournées
jarvis_config.HEURES_NUIT = None
jarvis_voix.forcer_nuit(True)
for ph in ["parle plus vite", "parle plus lentement", "remets le son", "baisse le son", "quelle heure est-il"]:
    r = ci(ph)
    verif("nuit, non détourné: " + ph, not (isinstance(r, str) and MARQUE in r), r)

# 4) désactiver fonctionne toujours, puis plus d'explication
r = ci("désactive le mode nuit")
verif("désactive le mode nuit", isinstance(r, str) and "je parle de nouveau" in r, r)
verif("mode nuit éteint", not jarvis_voix.mode_nuit())
for ph in ["parle un peu", "ralumer le micro", "pourquoi tu ne parles pas"]:
    r = ci(ph)
    verif("hors nuit, pas d'explication: " + ph, not (isinstance(r, str) and MARQUE in r), r)

# 5) active toujours le mode nuit via « ne parle plus »
r = ci("ne parle plus")
verif("ne parle plus active la nuit", isinstance(r, str) and "Mode nuit activé" in r, r)
print("ECHECS:", echecs)
sys.stdout.flush()
import os
os._exit(1 if echecs else 0)
