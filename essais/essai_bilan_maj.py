# -*- coding: utf-8 -*-
"""Essai de la phrase d'accueil après une mise à jour (jarvis_maj.bilan_au_demarrage), sans rien changer de réel."""
import sys, os, json, tempfile
sys.path.insert(0, r"C:\Jarvis")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import jarvis_maj as m
import jarvis_rapports as r

etat = {"id": "a0c818" + "0" * 26, "messages_envoyes": {"idee": 1}}
r.valeur = lambda cle, defaut=None: etat.get(cle, defaut)
r.regler = lambda cle, val: etat.__setitem__(cle, val)
echecs = 0


def verif(nom, bon, sortie):
    global echecs
    print(("OK   " if bon else "ÉCHEC"), nom, "->", repr(sortie))
    if not bon:
        echecs += 1


tmp = os.path.join(tempfile.gettempdir(), "suivi_essai.json")
m.FICHIER_SUIVI = tmp
actuelle = m.version_actuelle()
NOTES = "- **Commandes locales** : x\n- **Dés et calendrier** : y\n<!-- jarvis-merci: idee=a0c818 -->"
m.notes_de = lambda v: NOTES
m.notes_depuis = lambda d, a: [(a, NOTES)]
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "0.0"}, f)
s = m.bilan_au_demarrage()
verif("mise à jour réussie avec notes", s and s.startswith("Mise à jour terminée") and "commandes locales" in s
      and "prise en compte" in s and not os.path.exists(tmp), s)
etat["messages_envoyes"] = {"probleme": 1}
m.notes_de = lambda v: ""
m.notes_depuis = lambda d, a: []
etat.pop("merci_versions", None)
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "0.0"}, f)
s = m.bilan_au_demarrage()
verif("hors ligne (notes vides)", s and "Mise à jour terminée" in s and "Ton signalement a bien été reçu" in s, s)
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "999.0"}, f)
etat["messages_envoyes"] = {"idee": 1}
s = m.bilan_au_demarrage()
verif("mise à jour échouée : pas de merci, décompte gardé", s and "n'a pas abouti" in s and "merci" not in s.lower()
      and etat["messages_envoyes"] == {"idee": 1}, s)
verif("sans fichier de suivi : rien", m.bilan_au_demarrage() is None, None)

# versions sautées : le remerciement d'une version intermédiaire est dit, une seule fois
etat.clear()
etat.update({"id": "a0c818" + "0" * 26, "messages_envoyes": {}})
m.notes_depuis = lambda d, a: [("1.59", "- **Gros ajout** : x\n<!-- jarvis-merci: idee=a0c818 -->"), (a, "- **Petit ajout** : y")]
m.notes_de = lambda v: "- **Petit ajout** : y"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "1.58"}, f)
s = m.bilan_au_demarrage()
verif("version sautée : remerciement dit", s and "prise en compte" in s, s)
verif("versions notées pour ne pas le redire", etat.get("merci_versions") == ["1.59", actuelle], etat.get("merci_versions"))
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "1.58"}, f)
s = m.bilan_au_demarrage()
verif("deuxième fois : pas redit", s and "prise en compte" not in s, s)

# PC non concerné : listé nulle part, rien envoyé -> aucune phrase de remerciement (et pas les idées des autres)
etat.clear()
etat.update({"id": "ffffff" + "0" * 26, "messages_envoyes": {}})
m.notes_depuis = lambda d, a: [("1.59", "- **Gros ajout** : x\n<!-- jarvis-merci: idee=a0c818 probleme=123abc -->"), (a, "- **Petit ajout** : y")]
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "1.58"}, f)
s = m.bilan_au_demarrage()
verif("PC non concerné : aucun remerciement", s and "Merci" not in s and "suggestion" not in s and "probl" not in s, s)
# PC concerné par une idée ET un problème dans deux versions : une phrase de chaque, pas de doublon
etat.clear()
etat.update({"id": "a0c818" + "0" * 26, "messages_envoyes": {}})
m.notes_depuis = lambda d, a: [("1.59", "<!-- jarvis-merci: idee=a0c818 -->"), (a, "<!-- jarvis-merci: idee=a0c818 probleme=a0c818 -->")]
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "1.58"}, f)
s = m.bilan_au_demarrage()
verif("deux versions, une phrase de chaque", s and s.count("suggestion") == 1 and s.count("problème") == 1 and s.count("Merci") == 1, s)
# mise à jour refaite depuis une version plus ancienne : déjà lu, rien redit
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"depuis": "1.58"}, f)
s = m.bilan_au_demarrage()
verif("versions déjà lues : rien redit", s and "Merci" not in s and "suggestion" not in s, s)
print("\n=== %d ÉCHEC(S) ===" % echecs)
