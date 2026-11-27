# -*- coding: utf-8 -*-
"""Mise à jour bloquée (Windows, antivirus) : au 2e essai raté vers la même version, Jarvis explique comment débloquer
(phrase + Bloc-notes + ligne copiée), une seule fois par version. Bac à sable : rien ne s'ouvre, rien ne se télécharge."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_maj as m
sys.stdout.reconfigure(encoding="utf-8")
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


def bloc_notes():
    return any("notepad" in x.lower() for x in b.bloque)


m.oublier_echecs()
m.disponible = ("9.99", "essai")
del b.bloque[:]
verifier(m.noter_echec("installation") is False and not bloc_notes(), "1er essai raté : rien de montré")
verifier(m.noter_echec("installation") is True and bloc_notes(), "2e essai raté : Bloc-notes ouvert " + str(b.bloque[:2]))
phrase = m.echec_a_dire()
verifier(phrase and "antivirus" in phrase and "Contrôle V" in phrase, "phrase dite : " + str(phrase))
texte = open(os.path.join(os.environ["TEMP"], "Jarvis-aide-Windows.txt"), encoding="utf-8-sig").read() \
    if os.path.exists(os.path.join(os.environ["TEMP"], "Jarvis-aide-Windows.txt")) else m.texte_aide_blocage()
t = m.texte_aide_blocage("installation")
verifier(m.LIGNE_INSTALLATION in t and "Exécuter quand même" in t and "Historique de protection" in t
         and "quarantaine" in t and "méthode recommandée" not in t.lower() or "recommandée, elle marche sur tous les PC" in t,
         "aide : ligne du Terminal, SmartScreen, Sécurité Windows, autres antivirus")
del b.bloque[:]
verifier(m.noter_echec("installation") is False and not bloc_notes(), "3e essai raté : pas de répétition")
m.disponible = ("10.00", "autre")
m.noter_echec("installation")
verifier(m.noter_echec("installation") is True, "nouvelle version : l'aide peut revenir une fois")
m.echec_a_dire()

# téléchargement raté (réseau coupé dans le bac à sable) : 1er message normal, 2e = l'aide
m.oublier_echecs()
m.disponible = ("9.98", "essai")
r1 = m.installer()
r2 = m.installer()
verifier("connexion Internet" in r1, "1er téléchargement raté : " + r1)
verifier("antivirus" in r2 and "Bloc-notes" in r2, "2e téléchargement raté : " + r2)
verifier("téléchargement" in m.texte_aide_blocage("telechargement"), "aide adaptée au téléchargement")

# bilan au démarrage : mise à jour lancée, mais toujours la même version au redémarrage
m.oublier_echecs()
for n in (1, 2):
    json.dump({"depuis": m.version_actuelle(), "vers": "9.97", "quand": "x"}, open(m.FICHIER_SUIVI, "w", encoding="utf-8"))
    r = m.bilan_au_demarrage()
    verifier(("n'a pas abouti" in r) if n == 1 else ("antivirus" in r), f"bilan après échec n° {n} : {r[:90]}")
# réussite : les échecs sont oubliés
m.noter_echec("installation", "9.96")
json.dump({"depuis": "0.1", "vers": m.version_actuelle(), "quand": "x"}, open(m.FICHIER_SUIVI, "w", encoding="utf-8"))
m.notes_de = lambda v: ""
m.notes_depuis = lambda d, a: []
r = m.bilan_au_demarrage()
verifier("terminée" in r and not os.path.exists(m.FICHIER_ECHECS), "réussite : compteur effacé")

# mise à jour forcée : installateur lancé mais Jarvis tourne toujours 15 min après -> compté, sans double compte
m.oublier_echecs()
m.disponible, m.forcee = ("9.95", "essai"), True
m._forcee_lancee, m._forcee_essais, m._telechargement_rate, m._bloquee_par_windows = True, 1, False, False
m._forcee_lancee_le = time.time() - m.NOUVEL_ESSAI_INSTALLATION - 1
json.dump({"depuis": m.version_actuelle(), "vers": "9.95"}, open(m.FICHIER_SUIVI, "w", encoding="utf-8"))
m._rearmer_forcee()
verifier(m._lire_echecs().get("echecs") == 1 and not os.path.exists(m.FICHIER_SUIVI),
         "forcée : essai raté compté une fois (le bilan ne le recompte pas)")
print(f"\n{ok} / {total} essais réussis.")
