# -*- coding: utf-8 -*-
"""Mémoire rangée : limite, catégories, faits passagers, recherche par sujet, rappel des faits anciens.
Le fichier de mémoire de l'essai est dans un dossier provisoire (mkdtemp) : la vraie mémoire n'est jamais touchée."""
import datetime, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_memoire as m
sys.stdout.reconfigure(encoding="utf-8")
VRAI = m.FICHIER
m.FICHIER = os.path.join(tempfile.mkdtemp(), "memoire.json")
m._donnees = None
m._invite = lambda: False
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


def dire(phrase):
    r = m.commande(phrase)
    return r[1] if r else None


# ---------- ancien fichier (forme d'avant) relu tel quel ----------
json.dump({"faits": [{"texte": "ma voiture est une Clio grise", "date": "2026-11-01 10:00"}],
           "echanges": [{"date": "2026-11-01 10:00", "demande": "a", "reponse": "b"}]}, open(m.FICHIER, "w", encoding="utf-8"))
verifier(m.faits() == ["ma voiture est une Clio grise"], "ancien fichier memoire.json relu sans conversion")
verifier(m.tous()[0]["categorie"] == "Véhicules" and m.tous()[0]["source"] == "toi", "ancien fait : catégorie trouvée, source « toi »")

# ---------- retenir, catégories ----------
exemples = {"mon fils adore les dinosaures": "Famille et proches", "on a décidé de refaire la terrasse en mai": "Projets et décisions",
            "j'ai rendez-vous chez le dentiste le 12": "Santé", "le code du portail est 4521": "Maison",
            "mon film préféré est Retour vers le futur": "Goûts et loisirs", "je travaille chez Dupont": "Travail et études",
            "le concert est le 14 juin": "Rendez-vous et dates", "la tondeuse est chez Paul": "Autre"}
for phrase, attendu in exemples.items():
    verifier(dire("retiens que " + phrase) == "C'est retenu." and m.categorie(phrase) == attendu, f"« {phrase} » -> {m.categorie(phrase)}")
verifier(dire("retiens que le code du portail est 4521") == "Je l'avais déjà retenu.", "pas de doublon")
verifier(len(m.faits()) == 9, "9 faits en mémoire")

# ---------- par sujet ----------
r = dire("qu'est-ce que tu as retenu sur ma voiture ?")
verifier(r and "Clio" in r and "dinosaures" not in r, "retenu sur ma voiture : " + str(r))
r = dire("qu'est-ce que tu sais sur ma voiture")
verifier(r and "Clio" in r, "« sais sur ma voiture » : la mémoire répond quand elle a quelque chose")
verifier(dire("qu'est-ce que tu sais sur les trous noirs") is None, "« sais sur les trous noirs » : pas pour la mémoire (Wikipédia, Claude)")
verifier(dire("qu'est-ce que tu sais sur mon vélo") is None, "« sais sur mon vélo » sans rien en mémoire : laissé au reste de Jarvis")
r = dire("rappelle-moi ce qu'on avait décidé pour la terrasse")
verifier(r and "terrasse en mai" in r, "ce qu'on avait décidé pour la terrasse : " + str(r))
r = dire("qu'est-ce qu'on avait décidé pour le jardin")
verifier(r == "Je n'ai rien retenu sur le jardin.", "rien sur le jardin : " + str(r))
r = dire("qu'est-ce que tu as retenu sur ma famille ?")
verifier(r and "dinosaures" in r and "Clio" not in r, "par catégorie (ma famille) : " + str(r))
r = dire("cherche dans ta mémoire le code du portail")
verifier(r and "4521" in r, "cherche dans ta mémoire : " + str(r))
r = dire("qu'est-ce que tu sais sur moi ?")
verifier(r and r.startswith("J'ai retenu 9 choses"), "« sur moi » : toute la liste, comme avant")
verifier(dire("qu'est-ce que tu as retenu ?").startswith("J'ai retenu 9 choses"), "« qu'est-ce que tu as retenu ? » : comme avant")
verifier(dire("rappelle-moi dans 10 minutes de sortir le linge") is None, "un vrai rappel n'est pas pris pour la mémoire")
verifier(dire("rappelle-moi d'appeler le garage pour la voiture") is None, "« rappelle-moi d'appeler… » non plus")
verifier(dire("quelle heure est-il") is None and dire("retiens ça") is None, "phrases sans rapport : rien")

# ---------- oublier ----------
verifier(dire("oublie que la tondeuse est chez Paul") == "C'est oublié : la tondeuse est chez Paul.", "oublier à la voix : comme avant")
verifier(m.oublier_exact("le concert est le 14 juin") and not m.oublier_exact("jamais retenu"), "oublier depuis les réglages (texte exact)")
verifier(len(m.faits()) == 7, "7 faits restants")

# ---------- faits passagers ----------
m.retenir("demain j'ai piscine à 18 h")
verifier("demain j'ai piscine à 18 h" in m.faits(), "fait passager récent : rappelé")
with m._verrou:
    m._charger()["faits"][-1]["date"] = (datetime.datetime.now() - datetime.timedelta(days=45)).strftime("%Y-%m-%d %H:%M")
verifier("demain j'ai piscine à 18 h" not in m.faits(), "fait passager de plus de 30 jours : plus rappelé")
verifier(any(f["perime"] and "piscine" in f["texte"] for f in m.tous()), "… mais toujours visible dans les réglages (marqué ancien)")
verifier("piscine" not in m.contexte(), "… et plus donné à Claude")
with m._verrou:
    m._charger()["faits"][0]["date"] = "2020-01-01 10:00"
verifier("ma voiture est une Clio grise" in m.faits(), "un fait durable, même très ancien, reste rappelé")

# ---------- source ----------
m.appliquer_balises("Très bien.\nRETENIR: Tony préfère le thé")
verifier(m.tous()[0]["source"] == "jarvis" and m.tous()[0]["texte"] == "Tony préfère le thé", "fait retenu par Jarvis de lui-même : marqué")

# ---------- plus de limite à 60, contexte borné ----------
m.tout_effacer()
m.retenir("ma voiture est une Clio grise")
m.retenir("le chat s'appelle Félix")
for i in range(1, 99):
    m.retenir(f"note numéro {i} sur la peinture du salon")
verifier(len(m.faits()) == 100, "100 faits gardés (avant : les 40 plus anciens étaient perdus)")
contexte = m.contexte()
verifier(contexte.count("\n- ") + contexte.startswith("- ") <= 41 and "note numéro 98" in contexte and "Clio" not in contexte,
         "Claude reçoit les 40 plus récents au début (pas les 100 : moins de quota)")
verifier("60 faits plus anciens" in contexte, "… et sait qu'il y en a 60 autres")
r = m.nouveautes("combien consomme ma voiture sur autoroute")
verifier("Clio" in r and "Félix" not in r, "la demande parle de la voiture : le vieux fait revient -> " + r[:90])
verifier(m.nouveautes("et ma voiture, elle est de quelle couleur") == "", "… une seule fois par conversation")
verifier(m.nouveautes("quel temps fait-il") == "", "demande sans rapport : rien n'est ajouté")
m.retenir("mon pull est rouge")
r = m.nouveautes("merci")
verifier("vient de te demander de retenir" in r and "pull est rouge" in r, "fait tout neuf : toujours annoncé à Claude, comme avant")
m.tout_effacer()
for i in range(520):
    m.retenir(f"fait {i}")
verifier(len(m.faits()) == 500 and m.faits()[0] == "fait 20", "au-delà de 500 : les plus anciens partent")
m.tout_effacer()
m.retenir("j'aime le jazz")
verifier(m.contexte().count("j'aime le jazz") == 1 and "plus anciens" not in m.contexte() and m.nouveautes("jazz") == "",
         "peu de faits : exactement comme avant (tout est donné au début, rien de plus ensuite)")
verifier(m.FICHIER != VRAI and "Temp" in m.FICHIER, "la vraie mémoire n'a pas été touchée")
print(f"\n{ok} / {total} essais réussis.")
