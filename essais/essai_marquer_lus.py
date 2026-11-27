import sys, imaplib
sys.path.insert(0, r"C:\Jarvis")
import jarvis_mails as jm
import jarvis_commandes as jc

echecs = 0


def verif(nom, ok, detail=""):
    global echecs
    print(("OK   " if ok else "ECHEC"), nom, "->", str(detail)[:150])
    echecs += not ok


class FausseBoite:
    """Fausse messagerie : aucune connexion réelle."""
    etat = {"non_lus": 1048, "lecture_seule": None, "refuse_ecriture": False, "refuse_store": False,
            "store_partiel": False, "stores": 0, "tranches": []}

    def __init__(self, *a, **k): pass
    def login(self, *a): return ("OK", [b""])
    def select(self, nom, readonly=False):
        FausseBoite.etat["lecture_seule"] = readonly
        if not readonly and FausseBoite.etat["refuse_ecriture"]:
            return ("NO", [b"read-only"])
        return ("OK", [b"1"])
    def search(self, _, critere):
        n = FausseBoite.etat["non_lus"]
        return ("OK", [b" ".join(str(i).encode() for i in range(1, n + 1))])
    def store(self, numeros, op, drapeau):
        e = FausseBoite.etat
        e["stores"] += 1
        e["tranches"].append(len(numeros.split(b",")))
        assert op == "+FLAGS" and drapeau == "\\Seen", (op, drapeau)
        if e["refuse_store"]:
            return ("NO", [b"refus"])
        if e["store_partiel"]:
            e["non_lus"] = 5
        else:
            e["non_lus"] = max(0, e["non_lus"] - len(numeros.split(b",")))
        return ("OK", [b""])
    def fetch(self, numero, quoi):
        return ("OK", [(b"1 (BODY[HEADER])", b"From: Marie <marie@exemple.fr>\r\nSubject: Test\r\n\r\n"), b")"])
    def logout(self): return ("BYE", [b""])


imaplib.IMAP4_SSL = FausseBoite
jm._bon_compte = lambda: None
jm.identifiants = lambda cible=None: ("faux@exemple.fr", "motdepasse")
jm._serveur = lambda: "imap.exemple.fr"
E = FausseBoite.etat


def ci(x):
    return jc.commande_instantanee([x])


def remettre(**k):
    E.update({"non_lus": 1048, "lecture_seule": None, "refuse_ecriture": False, "refuse_store": False,
              "store_partiel": False, "stores": 0, "tranches": []})
    E.update(k)
    jc._attente = None


# 1. les vraies phrases entendues, et celles qu'on peut dire
for phrase in ("marque tous mes mails comme lus", "Jarvis, marque tous mes mails comme lus", "Mark, tout mes mails comme lui.",
               "Est-ce que tu peux marquer, tu mets mails comme lui ?", "mets tous mes mails en lus",
               "marque mes messages reçus comme lus", "passe tous mes courriels comme lus", "tout marquer comme lu mes mails"):
    remettre()
    r = jm.commande_marquer_lus(phrase, lambda a: None)
    verif("détecté : " + phrase, r is not None and "1048 mails" in r, r)

# 2. ce qui ne doit PAS être pris pour cette commande
for phrase in ("lis-moi tous mes mails", "combien de mails non lus", "marque la musique comme lue", "supprime tous mes mails",
               "envoie un mail comme lu", "ouvre le premier mail", "quelle heure est-il", "mets la musique"):
    remettre()
    r = jm.commande_marquer_lus(phrase, lambda a: None)
    verif("non détecté : " + phrase, r is None, r)

# 3. enfant, invité : rien ne se passe, rien n'est demandé
remettre()
dem = []
verif("enfant refusé", jm.commande_marquer_lus("marque tous mes mails comme lus", dem.append, enfant=True) ==
      "Les mails, c'est réservé aux parents." and not dem and E["stores"] == 0)
verif("invité refusé", "invité" in jm.commande_marquer_lus("marque tous mes mails comme lus", dem.append, invite=True) and not dem)

# 4. chemin complet par le répartiteur : phrase -> question -> « oui » -> fait, avec tranches
remettre()
r = ci("marque tous mes mails comme lus")
verif("répartiteur : demande confirmation", r and "1048 mails" in r and "oui" in r.lower() and E["stores"] == 0
      and E["lecture_seule"] is True, r)
r = ci("oui")
verif("« oui » : fait", r and "1048 mails marqués comme lus" in r and E["non_lus"] == 0 and E["lecture_seule"] is False, r)
verif("tranches de 400 au plus", max(E["tranches"]) <= 400 and sum(E["tranches"]) == 1048, E["tranches"])

# 5. « non » : rien n'est modifié
remettre()
ci("marque tous mes mails comme lus")
r = ci("non")
verif("« non » : rien modifié", E["stores"] == 0 and E["non_lus"] == 1048, r)

# 6. aucun non lu
remettre(non_lus=0)
r = ci("marque tous mes mails comme lus")
verif("aucun non lu", r == "Tu n'as aucun mail non lu." and not jc.confirmation_en_attente(), r)

# 7. un seul mail : singulier
remettre(non_lus=1)
r = ci("marque tous mes mails comme lus")
verif("singulier (question)", r and "1 mail comme lu." in r, r)
r = ci("oui")
verif("singulier (fait)", r == "C'est fait, 1 mail marqué comme lu.", r)

# 8. impossible : la messagerie refuse -> « Je ne sais pas faire ça. »
remettre(refuse_ecriture=True)
ci("marque tous mes mails comme lus")
r = ci("oui")
verif("boîte en lecture seule : je ne sais pas faire ça", r == "Je ne sais pas faire ça.", r)
remettre(refuse_store=True)
ci("marque tous mes mails comme lus")
r = ci("oui")
verif("modification refusée : je ne sais pas faire ça", r == "Je ne sais pas faire ça.", r)
remettre(store_partiel=True)
ci("marque tous mes mails comme lus")
r = ci("oui")
verif("partiel : dit ce qui reste", r and "1043" in r and "Il en reste 5" in r, r)

# 9. boîte non reliée / mot de passe refusé : messages habituels, pas « je ne sais pas »
remettre()
jm.identifiants = lambda cible=None: None
r = ci("marque tous mes mails comme lus")
verif("boîte non reliée : explique comment la relier", r and "relie mes mails" in r.lower(), r)

# 10. les anciennes commandes de mails marchent toujours
jm.identifiants = lambda cible=None: ("faux@exemple.fr", "motdepasse")
remettre()
r = ci("j'ai combien de nouveaux mails")
verif("compter les mails : toujours là", r and "1048 nouveaux mails" in r and "Marie" in r and E["lecture_seule"] is True, r)
print("=== %d ÉCHEC(S) ===" % echecs)
sys.exit(1 if echecs else 0)
