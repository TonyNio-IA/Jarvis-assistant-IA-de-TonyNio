# -*- coding: utf-8 -*-
"""Limite de Claude : Jarvis propose une solution ; « lors l'application… » = « lance » ; « ouvre les assistants ».
Bac à sable : rien ne se passe sur le PC."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_claude as j
import jarvis_commandes as c
import jarvis_reglages_ui as r
import jarvis_assistants
import jarvis_enfant
import jarvis_personnalite
sys.stdout.reconfigure(encoding="utf-8")
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


ouvertures = []
r.ouvrir = lambda: ouvertures.append(r._fenetre.pop("page", None))     # (comme la vraie fenêtre : la page demandée est consommée)
_reponse_action = jarvis_assistants.reponse_action
j.CLAUDE_EXE = __file__
jarvis_assistants.utilisable_maintenant = lambda: False
jarvis_personnalite.vouvoiement = lambda: False
reponses = []


class Faux:
    def demander(self, message, *a, **k):
        return j.message_limite(), True


j.claude = Faux()
j._derniers_messages.clear()
c._attente = None
rep, err = j.demander_avec_secours("raconte-moi l'histoire de Rome", "raconte-moi l'histoire de Rome")
verifier(err and "assistant gratuit" in rep and "dis oui" in rep and rep.startswith("La limite d'utilisation de Claude est atteinte"),
         "1re fois : Jarvis propose de brancher un assistant gratuit -> " + rep[:95])
verifier(j.claude_indisponible(rep), "… et ce message compte toujours comme « Claude indisponible » (rapports, secours)")
verifier(c.confirmation_en_attente(), "… un « oui » est attendu")
t, rep2, a = b.essayer("oui")
verifier("onglet Assistants" in str(rep2) and "Gemini ou Groq" in str(rep2) and ouvertures == ["Assistants"],
         "« oui » -> les réglages s'ouvrent sur Assistants : " + str(rep2)[:80])
rep, err = j.demander_avec_secours("et la suite", "et la suite")
verifier(rep == j.LIMITE_PISTE_TU and j.claude_indisponible(rep), "ensuite (dans l'heure) : version courte, avec la piste -> " + rep[:80])
verifier(not c.confirmation_en_attente(), "… sans redemander « oui » à chaque fois")
jarvis_personnalite.vouvoiement = lambda: True
j._derniers_messages.clear()
rep, err = j.demander_avec_secours("x", "explique-moi les marées")
verifier("dites oui" in rep and "vous" in rep, "vouvoiement respecté -> " + rep[70:150])
jarvis_personnalite.vouvoiement = lambda: False
# mode enfant : jamais de proposition
c._attente = None
j._derniers_messages.clear()
jarvis_enfant.actif = lambda: True
rep, err = j.demander_avec_secours("x", "explique-moi les marées")
verifier("assistant gratuit" not in rep and not c.confirmation_en_attente(), "mode enfant : pas de proposition -> " + rep[:60])
jarvis_enfant.actif = lambda: False
# un assistant est déjà branché : pas de proposition, il répond
j._derniers_messages.clear()
jarvis_assistants.utilisable_maintenant = lambda: True
jarvis_assistants.reponse_action = lambda *a, **k: None
jarvis_assistants.demander = lambda *a, **k: ("Les marées viennent de la Lune.", "Google Gemini", None)
rep, err = j.demander_avec_secours("x", "explique-moi les marées")
verifier(not err and "Google Gemini" in rep and "Lune" in rep, "assistant déjà branché : c'est lui qui répond, comme avant -> " + rep[:70])
# autre panne que la limite : rien de changé
jarvis_assistants.utilisable_maintenant = lambda: False
j.claude.demander = lambda m, *a, **k: ("Je n'arrive pas à joindre Claude.", True)
rep, err = j.demander_avec_secours("x", "explique-moi les marées")
verifier(rep == "Je n'arrive pas à joindre Claude.", "autre panne que la limite : message inchangé")

# ---------- « lors l'application… » ----------
c._attente = None
jarvis_assistants.reponse_action = _reponse_action
for phrase, attendu in (("Lors l'application, Instagram.", "Instagram"), ("Lorses l'application Riot Game.", "Riot Game"),
                        ("lors chrome", "Chrome"), ("los l'application instagram", "Instagram")):
    t, rep, a = b.essayer(phrase)
    verifier(t and attendu.lower() in str(rep).lower(), f"« {phrase} » -> {str(rep)[:70]}")
for phrase in ("lors de la réunion on a parlé de quoi", "lorsque j'arrive allume la lumière", "los angeles c'est où"):
    propre = c._propre(phrase)
    verifier(not propre.startswith("lance"), f"« {phrase} » : pas changé en « lance » ({propre[:40]})")

# ---------- « ouvre les assistants » ----------
for phrase in ("ouvre les assistants", "montre-moi les assistants", "branche un assistant gratuit", "ajoute une ia gratuite",
               "connecte un autre assistant"):
    del ouvertures[:]
    rep = r.commande(phrase)
    verifier(rep and "Gemini et Groq" in rep and ouvertures == ["Assistants"], f"« {phrase} » -> onglet Assistants")
for phrase in ("ouvre les réglages", "ouvre chrome", "c'est quoi un assistant vocal"):
    del ouvertures[:]
    rep = r.commande(phrase)
    verifier(ouvertures != ["Assistants"], f"« {phrase} » : pas l'onglet Assistants")
t, rep, a = b.essayer("installe une IA gratuite sur mon PC")
verifier("Assistants" not in str(rep), "« installe une IA gratuite sur mon PC » reste l'IA locale (Ollama) -> " + str(rep)[:60])
print(f"\n{ok} / {total} essais réussis.")
