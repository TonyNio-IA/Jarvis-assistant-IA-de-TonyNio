# -*- coding: utf-8 -*-
"""Jarvis SANS Claude, avec un seul autre assistant (réseau simulé)."""
import os, sys, tempfile
sys.path.insert(0, r"C:\Jarvis")
import jarvis_assistants as ja
import jarvis_claude as jc
import jarvis_local

ok = True
def verif(nom, cond):
    global ok
    print(("OK   " if cond else "ECHEC"), nom)
    ok = ok and bool(cond)

ja.FICHIER = os.path.join(tempfile.mkdtemp(), "assistants.json")
ja.FICHIER_JOURNAL = os.path.join(tempfile.mkdtemp(), "journal_test.jsonl")
appels = []
def faux(c, chemin, corps=None, delai=60):
    appels.append(corps)
    if chemin == "/models":
        return {"data": [{"id": "mistral-small-latest"}]}
    return {"choices": [{"message": {"content": "**Demain** il fera beau."}}]}
ja._requete = faux

verif("rien de branché -> indisponible", not ja.utilisable_maintenant())
r, e, id_ = ja.ajouter_compte("mistral", "cle-test-1234567890")
verif("compte ajouté", r)
ja.accepter_consentement(True)
verif("assistant utilisable seul", ja.utilisable_maintenant())

# Claude absent
jc.CLAUDE_EXE = r"C:\inexistant\claude.exe"
jc.claude.demarrer()
rep, err = jc.demander_avec_secours("note interne : question", "quel temps demain ?")
verif("réponse de l'autre assistant", (not err) and "Demain il fera beau" in rep)
verif("pas de préfixe 'Claude n'est pas disponible'", "Claude n'est pas disponible" not in rep)
verif("la note interne ne part pas", all("note interne" not in str(a) for a in appels))
rep2, err2 = jc.demander_avec_secours("x", "et après-demain ?")
msgs = [a for a in appels if a and "messages" in a][-1]["messages"]
verif("historique transmis", len(msgs) >= 4)
ja.oublier()
verif("oubli de la conversation", not ja._recent())

# économie de quota
ja.oublier()
n0 = len(appels)
ja.demander("euh")
verif("bruit : aucun appel réseau", len(appels) == n0)
a1 = ja.demander("quelle est la capitale du Japon")
n1 = len(appels)
a2 = ja.demander("Quelle est la capitale du Japon ?")
verif("même question redite : pas de second appel", len(appels) == n1 and a1[0] == a2[0])
ja.oublier()
ja.demander("quelle est la capitale du Japon")
verif("après « oublie » : nouvel appel", len(appels) > n1)

# sans_claude ne propose plus Google quand un assistant est prêt
jarvis_local._claude_installe = lambda: False
res = jarvis_local.sans_claude("quel temps fait-il demain à Paris", "quel temps fait-il demain à Paris",
                               lambda *a, **k: False, lambda *a, **k: None)
verif("pas de proposition Google", res is None)

# sans assistant : ancien comportement (message d'aide)
ja.modifier_compte(id_, actif=False)
rep3, err3 = jc.demander_avec_secours("x", "quelle heure ?")
verif("sans assistant : erreur renvoyée (message d'aide, court si déjà dit)", bool(err3) and bool(rep3))
print("\nRESULTAT :", "TOUT OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
