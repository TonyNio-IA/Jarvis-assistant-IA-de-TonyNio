# -*- coding: utf-8 -*-
"""Essai de l'onglet « Assistants » : on ouvre la vraie fenêtre de réglages (réseau coupé, fichier de comptes
temporaire), on parcourt les étapes en cliquant dans la fenêtre (événements internes à Tk, rien envoyé au bureau),
on vérifie les textes, l'absence d'erreur et que rien ne dépasse de la fenêtre, y compris en petite fenêtre."""
import sys, os, tempfile, tkinter as tk
sys.path.insert(0, r"C:\Jarvis")
import jarvis_assistants as ja

ja.FICHIER = os.path.join(tempfile.mkdtemp(), "assistants.json")
ja.FICHIER_JOURNAL = os.path.join(tempfile.mkdtemp(), "journal_test.jsonl")
def pas_de_reseau(*a, **k):
    raise ja.Erreur("adresse", "Impossible de joindre le service : essai sans réseau.")
ja._requete = pas_de_reseau
import jarvis_reglages_ui as u

echecs = 0
erreurs = []
tk.Tk.report_callback_exception = lambda self, *a: erreurs.append(a)


def verif(nom, ok, detail=""):
    global echecs
    print(("OK   " if ok else "ECHEC"), nom, "->", str(detail)[:150])
    echecs += not ok


def tous(w):
    yield w
    for e in w.winfo_children():
        yield from tous(e)


def textes(racine):
    out = []
    for w in tous(racine):
        try:
            t = w.cget("text")
            if t:
                out.append(str(t))
        except Exception:
            pass
    return out


def cliquer(racine, texte):
    for w in tous(racine):
        try:
            if str(w.cget("text")) == texte:
                w.event_generate("<Button-1>")
                racine.update()
                return True
        except Exception:
            pass
    return False


def debordements(racine):
    droite = racine.winfo_rootx() + racine.winfo_width() + 2
    mauvais = []
    for w in tous(racine):
        try:
            if w.winfo_ismapped() and w.winfo_class() in ("Label", "Entry") and w.winfo_width() > 5:
                if w.winfo_rootx() + w.winfo_width() > droite:
                    mauvais.append((w.winfo_class(), str(w.cget("text"))[:30] if w.winfo_class() == "Label" else "entry"))
        except Exception:
            pass
    return mauvais


def pomper(racine, n=6):
    for _ in range(n):
        racine.update()
        racine.after(40)


def pilote(racine):
    pomper(racine, 10)
    t = textes(racine)
    verif("bandeau bêta visible", any("VERSION DE TEST" in x for x in t))
    verif("avertissement « il peut y avoir des problèmes »", any("il peut y avoir des problèmes" in x for x in t))
    verif("étape 1 : accord demandé", any("J'ai compris, j'autorise" in x for x in t))
    verif("liste vide annoncée", any("Aucun assistant ajouté" in x for x in t))
    visibles = [f for f in ja.FOURNISSEURS if f.get("groupe") != "payant"]
    verif("gratuits et « Autre » listés, payants repliés (1.66)", sum(1 for x in t if x == "Choisir") == len(visibles),
          sum(1 for x in t if x == "Choisir"))
    verif("pas de débordement (fenêtre normale)", not debordements(racine), debordements(racine))
    cliquer(racine, "Voir les assistants payants"); pomper(racine)
    verif("tous les fournisseurs listés une fois les payants ouverts",
          sum(1 for x in textes(racine) if x == "Choisir") == len(ja.FOURNISSEURS), sum(1 for x in textes(racine) if x == "Choisir"))
    verif("pas de débordement avec les payants ouverts", not debordements(racine), debordements(racine))
    cliquer(racine, "Masquer"); pomper(racine)

    cliquer(racine, "J'ai compris, j'autorise"); pomper(racine)
    verif("accord enregistré", ja.charger()["consentement"] is True)
    verif("accord affiché", any("autorisés" in x for x in textes(racine)))

    cliquer(racine, "Choisir"); pomper(racine)       # le premier : Gemini
    verif("formulaire ouvert", any("Assistant choisi" in x for x in textes(racine)))
    cliquer(racine, "Assistants"); pomper(racine, 10)  # reclic sur l'onglet dans le menu
    verif("reclic sur Assistants -> retour à la liste (première page)",
          (not any("Assistant choisi" in x for x in textes(racine))) and any(x == "Choisir" for x in textes(racine)),
          [x for x in textes(racine) if "choisi" in x])
    cliquer(racine, "Choisir"); pomper(racine)
    t = textes(racine)
    verif("étape B : explication de la clé", any("clé API" in x and "mot de passe" in x for x in t))
    verif("bouton « Ouvrir le site »", any(x.startswith("Ouvrir le site de") for x in t))
    verif("étape C et D présentes", any(x.startswith("C. Colle") for x in t) and any(x.startswith("D. Ajoute") for x in t))
    verif("avancé replié par défaut", not any("Adresse du service" in x for x in t))
    verif("pas de débordement (étape clé)", not debordements(racine), debordements(racine))

    cliquer(racine, "Afficher les réglages avancés"); pomper(racine)
    verif("avancé déplié", any("Adresse du service" in x for x in textes(racine)))

    # clé trop courte
    cliquer(racine, "Ajouter et tester"); pomper(racine)
    verif("clé vide refusée avec message", any("trop courte" in x for x in textes(racine)), [x for x in textes(racine) if "clé semble" in x])
    verif("aucun compte créé", ja.charger()["comptes"] == [])

    # clé plausible mais pas de réseau -> « adresse » : compte non gardé
    for w in tous(racine):
        if w.winfo_class() == "Entry" and w.cget("show") == "•":
            w.delete(0, "end"); w.insert(0, "AIzaFAUSSECLE12345678")
    pomper(racine, 3)
    cliquer(racine, "Ajouter et tester")
    for _ in range(40):
        pomper(racine, 2)
        if not u.__dict__.get("_x") and any("Impossible de joindre" in x for x in textes(racine)):
            break
    verif("échec réseau expliqué", any("Impossible de joindre" in x for x in textes(racine)))
    verif("compte non gardé après échec réseau", ja.charger()["comptes"] == [], ja.charger()["comptes"])

    # un compte déjà là : affichage de la liste + boutons
    ja.ajouter_compte("mistral", "cle-mistral-123456", etiquette="perso")
    ja.ajouter_compte("deepseek", "cle-deepseek-123456")
    cliquer(racine, "Changer d'assistant"); pomper(racine, 4)
    t = textes(racine)
    verif("liste : 2 comptes", any(x.startswith("1. Mistral") for x in t) and any(x.startswith("2. DeepSeek") for x in t), [x for x in t if x[:2] in ("1.", "2.")])
    verif("clé masquée dans la liste", any("cle…3456" in x or "cle…" in x for x in t) and not any("cle-mistral-123456" in x for x in t))
    verif("boutons Tester/Retirer/Monter/Descendre", all(b in t for b in ("Tester", "Retirer", "Monter", "Descendre")))
    cliquer(racine, "Descendre"); pomper(racine, 4)
    verif("ordre changé", [c["fournisseur"] for c in ja.charger()["comptes"]] == ["deepseek", "mistral"])
    cliquer(racine, "Mettre de côté"); pomper(racine, 4)
    verif("mis de côté", ja.charger()["comptes"][0]["actif"] is False)
    verif("état « mis de côté » affiché", any("Mis de côté" in x for x in textes(racine)))

    # petite fenêtre
    racine.geometry("720x520"); pomper(racine, 10)
    verif("pas de débordement (petite fenêtre)", not debordements(racine), debordements(racine))
    verif("aucune erreur Tk", not erreurs, erreurs[:1])
    print("ECHECS :", echecs)
    racine.destroy()


tk.Tk.mainloop = lambda self, n=0: pilote(self)
u._fenetre["page"] = "Assistants"
try:
    u._fenetre_principale(None)
except SystemExit:
    pass
except Exception as e:
    import traceback; traceback.print_exc(); echecs += 1
print("FIN, échecs :", echecs, "erreurs Tk :", len(erreurs))
sys.exit(1 if echecs else 0)
