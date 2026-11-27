# -*- coding: utf-8 -*-
"""Essai de jarvis_assistants SANS réseau et sans toucher au vrai assistants.json."""
import sys, os, tempfile, time
sys.path.insert(0, r"C:\Jarvis")
import jarvis_assistants as ja

echecs = 0


def verif(nom, ok, detail=""):
    global echecs
    print(("OK   " if ok else "ECHEC"), nom, "->", str(detail)[:140])
    echecs += not ok


# fichier de réglages temporaire : le vrai n'est jamais touché
ja.FICHIER = os.path.join(tempfile.mkdtemp(), "assistants.json")
ja.FICHIER_JOURNAL = os.path.join(tempfile.mkdtemp(), "journal_test.jsonl")

verif("réglages vides au départ", ja.charger() == {"consentement": False, "comptes": []})
verif("pas disponible sans compte", ja.disponible() is False)

# nettoyage des clés / adresses
verif("clé nettoyée", ja.nettoyer_cle('  "Bearer sk-abc 123456\n" ') == "sk-abc123456", ja.nettoyer_cle('  "Bearer sk-abc 123456\n" '))
verif("adresse nettoyée", ja.nettoyer_adresse("https://api.x.ai/v1/chat/completions/") == "https://api.x.ai/v1")
verif("http distant refusé", not ja.adresse_valide("http://exemple.com/v1"))
verif("http localhost accepté", ja.adresse_valide("http://localhost:11434/v1"))
verif("https accepté", ja.adresse_valide("https://api.mistral.ai/v1"))

# chiffrement Windows
c = ja.chiffrer_cle("sk-secret-12345678")
verif("clé chiffrée != clair", "secret" not in c)
verif("clé déchiffrée", ja.dechiffrer_cle(c) == "sk-secret-12345678")
verif("déchiffrement d'un texte faux -> vide", ja.dechiffrer_cle("pasbase64!!") == "")
verif("masque", ja.masquer("sk-secret-12345678") == "sk-…5678", ja.masquer("sk-secret-12345678"))

# ajout / refus
ok, m, _ = ja.ajouter_compte("gemini", "abc", "")
verif("clé trop courte refusée", not ok, m)
ok, m, _ = ja.ajouter_compte("inconnu", "abcdefgh12")
verif("fournisseur inconnu refusé", not ok, m)
ok, m, _ = ja.ajouter_compte("autre", "abcdefgh12", adresse="http://exemple.com/v1")
verif("http distant refusé à l'ajout", not ok, m)
ok, m, id1 = ja.ajouter_compte("deepseek", "sk-deepseek-0001")
verif("ajout DeepSeek", ok and id1, m)
ok, m, id2 = ja.ajouter_compte("mistral", "mistral-key-0002", etiquette="perso")
verif("ajout Mistral", ok and id2, m)
ok, m, id3 = ja.ajouter_compte("ollama", "")
verif("Ollama sans clé accepté", ok and id3, m)
brut = open(ja.FICHIER, encoding="utf-8").read()
verif("aucune clé en clair dans le fichier", "sk-deepseek-0001" not in brut and "mistral-key-0002" not in brut)
verif("modèle conseillé DeepSeek gardé", ja.compte(id1)["modele"] == "deepseek-flash")

# consentement : rien ne part SUR INTERNET sans accord. Depuis la 1.66, Ollama (sur ce PC, rien ne sort) reste utilisable.
verif("Ollama (sur ce PC) utilisable sans accord", ja.disponible() is True)
verif("sans accord, seul Ollama serait essayé", [c["fournisseur"] for c in ja._utilisables()] == ["ollama"])
ja.supprimer_compte(id3)
verif("indisponible sans consentement", ja.disponible() is False)
r, n, e = ja.demander("quelle heure est-il maintenant")
verif("demander refuse sans consentement", r == "" and "pas activés" in e, e)
ok, m, id3 = ja.ajouter_compte("ollama", "")
ja.accepter_consentement(True)
verif("disponible avec consentement", ja.disponible() is True)

# ordre
verif("monter Mistral", ja.deplacer_compte(id2, -1))
verif("ordre après montée", [c["id"] for c in ja.charger()["comptes"]][:2] == [id2, id1])
verif("monter le premier impossible", ja.deplacer_compte(id2, -1) is False)

# faux réseau
appels = []


def faux(c, chemin, corps=None, delai=0):
    appels.append((c["fournisseur"], chemin))
    if chemin == "/models":
        return {"data": [{"id": "gros-modele"}, {"id": "text-embedding-x"}, {"id": "petit-flash"}]}
    f = c["fournisseur"]
    if f == "mistral":
        raise ja.Erreur("quota", "limite")
    if f == "deepseek":
        return {"choices": [{"message": {"content": "**Bonjour** Tony, <think>x</think>ça va ?"}}]}
    raise ja.Erreur("panne", "x")


ja._requete = faux
verif("modèles filtrés et triés", ja.lister_modeles(ja.compte(id2)) == ["petit-flash", "gros-modele"], ja.lister_modeles(ja.compte(id2)))
r, n, e = ja.demander("quel temps fera-t-il demain")
verif("bascule Mistral(quota) -> DeepSeek", r == "Bonjour Tony, ça va ?" and "DeepSeek" in n, (r, n, e))
verif("Mistral mis en pause", ja.compte(id2)["pause_jusqua"] > time.time())
appels.clear()
r, n, e = ja.demander("et après-demain alors")
verif("Mistral en pause sauté", all(a[0] != "mistral" for a in appels), appels)
verif("modèle choisi automatiquement et gardé", ja.compte(id2)["modele"] == "petit-flash")

# clé refusée : le compte est désactivé
ja.modifier_compte(id1, pause_jusqua=0)
def faux_cle(c, chemin, corps=None, delai=0):
    raise ja.Erreur("cle", "refusée")
ja._requete = faux_cle
r, n, e = ja.demander("raconte une blague courte")
verif("clé refusée -> compte désactivé", ja.compte(id1)["actif"] is False and r == "", (r, e))
ok, m = ja.tester(id1)
verif("test échoue proprement", ok is False and "refusée" in m, m)

# tout en panne
ja.modifier_compte(id1, actif=True, pause_jusqua=0)
ja.modifier_compte(id2, actif=True, pause_jusqua=0)
ja._requete = faux
ja.modifier_compte(id1, actif=False)
ja.modifier_compte(id3, actif=False)
r, n, e = ja.demander("donne-moi une autre idée")
verif("quota seul -> message d'erreur", r == "" and e, e)

# suppression
verif("suppression", ja.supprimer_compte(id1) and ja.compte(id1) is None)
# fichier abîmé
open(ja.FICHIER, "w").write("{pas du json")
verif("fichier abîmé -> réglages vides", ja.charger() == {"consentement": False, "comptes": []})
print("ECHECS :", echecs)
sys.exit(1 if echecs else 0)
