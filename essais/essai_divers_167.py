# -*- coding: utf-8 -*-
"""1.67 : « déconnecte-toi de Claude » sans Claude, surveillance de l'écoute (observation seulement).
Bac à sable : copie de Jarvis, rien ne se passe sur le PC."""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_claude as j
import jarvis_reglages_ui as r
sys.stdout.reconfigure(encoding="utf-8")
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


ouvertures = []
r.ouvrir = lambda: ouvertures.append(r._fenetre.get("page"))
for phrase in ("Deconecte toi sur mon Claude", "déconnecte-toi de Claude", "change de compte Claude",
               "je veux un autre compte Claude", "déconnecte mon compte Claude"):
    del ouvertures[:]
    rep = r.commande(phrase.lower())
    verifier(rep and "Changer de compte" in rep and ouvertures == ["Assistants"], f"« {phrase} » -> réglages, onglet Assistants")
del ouvertures[:]
rep = r.commande("connecte claude")
verifier(rep and "Connecter mon compte" in rep, "« connecte Claude » : toujours l'ancienne réponse (installer, connecter)")
for phrase in ("déconnecte le wifi", "change de chaîne", "ouvre chrome", "claude est super", "qui est claude françois"):
    verifier(r.commande(phrase) is None, f"« {phrase} » : pas pour les réglages")
t, rep, a = b.essayer("déconnecte-toi de mon Claude")
verifier(t and "Changer de compte" in str(rep), "dans le vrai circuit des commandes : traité sans Claude -> " + str(rep)[:70])

# ---------- surveillance de l'écoute ----------
j._tour_ecoute.update(quand=0.0, fil=None, note=0.0)
verifier(j.ecoute_occupee() == 0, "écoute pas encore démarrée : rien")
j._battre_ecoute()
verifier(j.ecoute_occupee() == 0 and j._tour_ecoute["fil"] == threading.get_ident(), "un tour vient d'avoir lieu : rien")
maintenant = time.time()
verifier(j.ecoute_occupee(maintenant + 14 * 60) == 0, "14 minutes sans tour : pas encore noté (une longue histoire peut durer)")
verifier(j.ecoute_occupee(maintenant + 16 * 60) >= 15 * 60, "16 minutes sans tour : noté")
lieu = j.ou_en_est_l_ecoute()
verifier("essai_divers_167.py" in lieu and "ou_en_est_l_ecoute" in lieu, "l'endroit exact est donné : " + lieu[:110])
# le fil de surveillance note une fois, et n'arrête rien
notes = []
j.jarvis_rapports.erreur = lambda source, exc=None, texte="": notes.append((source, texte))
j.ECOUTE_OCCUPEE_APRES = 0.2
bloque = {"fini": False}


def boucle_bloquee():
    j._tour_ecoute.update(quand=0.0, fil=None, note=0.0)
    j._battre_ecoute()
    while not bloque["fini"]:
        time.sleep(0.05)


fil = threading.Thread(target=boucle_bloquee, daemon=True)
fil.start()
threading.Thread(target=j._surveiller_ecoute, args=(0.15,), daemon=True).start()
time.sleep(1.2)
verifier(len(notes) == 1 and notes[0][0] == "ecoute" and "boucle_bloquee" in notes[0][1],
         f"écoute arrêtée : notée UNE fois, avec l'endroit ({len(notes)} note) -> " + (notes[0][1][:90] if notes else ""))
verifier(fil.is_alive(), "rien n'est arrêté ni relancé (observation seulement)")
bloque["fini"] = True
j.ECOUTE_OCCUPEE_APRES = 15 * 60
print(f"\n{ok} / {total} essais réussis.")
