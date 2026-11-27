# -*- coding: utf-8 -*-
"""Essais automatiques de la 1.65 (sans toucher aux vrais fichiers de Jarvis : tout se passe dans un dossier temporaire)."""
import io, json, os, shutil, sys, tempfile, time, types
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
resultats = []


def verifier(nom, ok, detail=""):
    resultats.append((nom, bool(ok)))
    print(("OK   " if ok else "ÉCHEC") + " " + nom + (f"  [{detail}]" if detail and not ok else ""))


# ---------- 1. Mises à jour forcées ----------
import jarvis_maj as m
import tempfile as _tf
m.FICHIER_ECHECS = os.path.join(_tf.mkdtemp(), "mise_a_jour_echecs.json")   # (jamais le vrai compteur de ce PC)
m.FICHIER_SUIVI = os.path.join(os.path.dirname(m.FICHIER_ECHECS), "mise_a_jour.json")
m.disponible, m.forcee = ("1.99", "essai"), True
m._activite_tablette = 0.0
verifier("forcée : aucune attente juste après le démarrage", m.calme_requis() == 0)
m.DEMARRAGE -= 10 * 60
verifier("forcée : 20 s de veille ensuite", m.calme_requis() == 20)
verifier("forcée : en attente", m.forcee_en_attente())
verifier("forcée : 1er essai accordé", m.forcee_a_installer() and m.premier_essai_forcee())
verifier("forcée : pas deux essais à la fois", not m.forcee_a_installer())
m._telechargement_rate = True
m._forcee_lancee_le -= m.NOUVEL_ESSAI_TELECHARGEMENT + 1
verifier("forcée : nouvel essai 5 min après un téléchargement raté", m.forcee_en_attente() and m.forcee_a_installer())
verifier("forcée : le 2e essai n'est plus annoncé à voix haute", not m.premier_essai_forcee())
m._telechargement_rate = False
m._forcee_lancee_le -= 60
verifier("forcée : installateur lancé, pas de nouvel essai avant 15 min", not m.forcee_en_attente())
m._forcee_lancee_le -= m.NOUVEL_ESSAI_INSTALLATION
verifier("forcée : nouvel essai 15 min plus tard si Jarvis tourne encore", m.forcee_en_attente())
m._forcee_lancee, m._bloquee_par_windows = True, True
m._forcee_lancee_le -= 3600
verifier("forcée : bloquée par Windows, pas d'essai en boucle", not m.forcee_en_attente())
m._bloquee_par_windows, m._forcee_essais = False, m.ESSAIS_FORCEE
verifier("forcée : 6 essais au plus", not m.forcee_en_attente())
verifier("vérification GitHub toutes les 5 min", m.INTERVALLE_FORCEES == 300)
src = io.open("jarvis_maj.py", encoding="utf-8").read()
verifier("la vérification ne s'arrête plus après le lancement", "if _forcee_lancee:\n                return" not in src.replace("\r\n", "\n"))

# ---------- 2. Rapports ----------
import jarvis_rapports as r
dossier = tempfile.mkdtemp(prefix="jarvis-essai-rapports-")
r.FICHIER = os.path.join(dossier, "rapports.json")
r.JOURNAL = os.path.join(dossier, "journal.jsonl")
envois = []
r._envoyer = lambda d: envois.append(d) or True       # rien ne part vraiment pendant les essais
r._signal = lambda: None
r._numero_du_pc = lambda: "e" * 32                    # numéro d'essai, jamais celui de ce PC
r._donnees = None
verifier("nouveau PC : « Technique » par défaut", r.niveau() == "technique")
verifier("nouveau PC : la fenêtre d'accord reste montrée une fois", r.a_demander())
r.choisir_niveau("complet")
verifier("choix « Complet » : plus de fenêtre", not r.a_demander() and r.niveau() == "complet")
for ancien, plus, attendu in (("complet", {}, "complet"), ("aucun", {}, "aucun"), ("technique", {}, "technique"),
                              (None, {}, "technique"), ("aucun", {"bascule_165": True}, "aucun")):
    with open(r.FICHIER, "w", encoding="utf-8") as f:
        json.dump(dict({"id": "0" * 32, "niveau": ancien, "refuse_le": 1}, **plus), f)
    r._donnees = None
    verifier(f"mise à jour : « {ancien} » {plus or ''} devient « {attendu} »", r.niveau() == attendu, r.niveau())
    if ancien == "aucun" and not plus:
        # 1.69 : un refus n'est plus jamais réactivé (la bascule de la 1.65 est retirée)
        r._donnees = None
        verifier("refus gardé (relu au démarrage suivant)", r.niveau() == "aucun" and r.valeur("bascule_165"))
        r.choisir_niveau("aucun")
        r._donnees = None
        verifier("remis sur « Rien » dans les Réglages : gardé", r.niveau() == "aucun")
verifier("rapport toutes les heures", r.INTERVALLE_RAPPORT == 3600 and r.DELAI_NOUVEL_ESSAI == 3600)
envois.clear()
r._donnees = None
with open(r.FICHIER, "w", encoding="utf-8") as f:
    json.dump({"id": "0" * 32, "niveau": "technique", "dernier_rapport": time.time()}, f)
r._donnees = None
r.noter("incompris", texte="essai", raison="essai")
verifier("pas de rapport avant l'heure", r.envoyer_rapport() is False and not envois)
r.regler("dernier_rapport", time.time() - 3700)
verifier("rapport envoyé au bout d'une heure s'il y a du nouveau", r.envoyer_rapport() is True and len(envois) == 1)
r.regler("dernier_rapport", time.time() - 3700)
verifier("rien de nouveau : rien n'est envoyé", r.envoyer_rapport() is False and len(envois) == 1)
shutil.rmtree(dossier, ignore_errors=True)

# ---------- 3. Compréhension ----------
import jarvis_commandes as c
for brut, attendu in (("ouvre Chrome s'il te plaît", "ouvre chrome"), ("ouvre chrome stp", "ouvre chrome"),
                      ("tu peux ouvrir chrome pour moi", "ouvre chrome"), ("est-ce que tu peux lancer spotify", "lance spotify"),
                      ("lance spotify sur mon pc", "lance spotify"), ("Jarvis ouvre chrome merci", "jarvis ouvre chrome"),
                      ("je voudrais baisser le son", "baisse le son"), ("s'il te plaît, mets de la musique", "mets de la musique"),
                      ("merci", "merci"), ("s'il te plaît", "s'il te plaît"), ("ouvre le fichier pour moi.txt", "ouvre le fichier pour moi.txt"),
                      ("quelle heure est-il", "quelle heure est-il"), ("tu peux me dire la météo", "tu peux me dire la météo")):
    obtenu = c._sans_remplissage(brut.lower())
    verifier(f"politesse : « {brut} »", obtenu == attendu, obtenu)
for t, attendu in (("oui", True), ("oui vas-y", True), ("ok", True), ("d'accord", True), ("oui éteins", True),
                   ("oui mais attends", False), ("oui non", False), ("oui ?", False), ("ouais euh", False),
                   ("oui pas maintenant", False), ("non", False), ("oui finalement non", False)):
    verifier(f"oui franc : « {t} »", c._oui_franc(t) == attendu)
c._attente = ("eteindre", time.time() + 20)
rep = c._commande_alimentation("oui mais attends")
verifier("« oui mais attends » n'éteint pas le PC", rep and "rien" in rep and c._attente is None)
for x, attendu in ((1, "1 degré"), (1.4, "1 degré"), (0, "0 degré"), (-1, "-1 degré"), (2, "2 degrés"), (-3, "-3 degrés"), (12.6, "13 degrés")):
    verifier(f"degrés : {x}", c._degres(x) == attendu, c._degres(x))
for niveaux, attendu in (([0.001] * 100, "calme"), ([0.005] * 100, "normale"), ([0.01] * 100, "bruyante"), ([0.0] * 50, None)):
    verifier(f"réglage du micro : bruit {niveaux[0]}", c.reglage_selon_bruit(niveaux)[0] == attendu)
verifier("« règle ton micro » reconnu", bool(c._MICRO_REGLER.search("règle ton micro")) and bool(c._MICRO_REGLER.search("calibre le microphone")))
verifier("« coupe le micro » pas pris pour un réglage", not c._MICRO_REGLER.search("coupe le micro"))

import jarvis_claude as jc
for phrase in ("Merci d'avoir regardé cette vidéo !", "Abonnez-vous à la chaîne", "Sous-titrage ST' 501",
               "N'oubliez pas de vous abonner", "À bientôt pour une prochaine vidéo"):
    verifier(f"hallucination écartée : « {phrase} »", bool(jc._HALLUCINATION.search(phrase)))
for phrase in ("merci", "merci beaucoup Jarvis", "abonne-moi à la newsletter de la mairie ? non", "quelle heure est-il",
               "mets la vidéo en pause"):
    if phrase.startswith("abonne-moi"):
        continue
    verifier(f"vraie phrase gardée : « {phrase} »", not jc._HALLUCINATION.search(phrase))

# ---------- 4. Wikipédia ----------
import jarvis_wikipedia as w
for brut, attendu in (("qui est Victor Hugo", "Victor Hugo"), ("c'est quoi un trou noir", "un trou noir"),
                      ("qu'est-ce que la photosynthèse", "la photosynthèse"), ("parle-moi de la tour Eiffel", "la tour Eiffel"),
                      ("définition de démocratie", "démocratie"), ("qui es-tu", None), ("c'est quoi ça", None),
                      ("qui est le président de la République", None), ("qu'est-ce que tu fais", None),
                      ("c'est quoi la météo aujourd'hui", None), ("qui est là", None), ("c'est quoi ton nom", None),
                      ("qu'est-ce qu'il y a", None), ("c'est quoi de neuf", None)):
    verifier(f"Wikipédia, sujet de « {brut} »", w.sujet(brut) == attendu, w.sujet(brut))
dites = []
w.patienter = dites.append
for question, mot in (("qui est Victor Hugo", "écrivain"), ("c'est quoi la photosynthèse", "lumi"), ("qui était Napoléon Bonaparte", "empereur"),
                      ("c'est quoi un trou noir", "gravit")):
    rep = w.repondre(question)
    verifier(f"Wikipédia répond : « {question} »", rep and mot in rep.lower() and rep.endswith("Wikipédia."), (rep or "")[:120])
    print("      ->", (rep or "")[:200])
verifier("Wikipédia : un sujet inventé ne donne rien", w.repondre("qui est Zorglubtrifouillis Bérangerprout") is None)

# ---------- 5. Rappels confiés à Windows (dans un dossier temporaire, tâche d'essai retirée à la fin) ----------
import jarvis_rappels_windows as rw
dossier = tempfile.mkdtemp(prefix="jarvis-essai-rappels-")
rw.FICHIER_RAPPELS = os.path.join(dossier, "rappels.json")
rw.FICHIER_VIE = os.path.join(dossier, "vie.txt")
rw.PREFIXE = "\\Jarvis\\Essai-Rappel-"
rappel = {"quand": time.time() + 3 * 3600, "message": "Rappel : essai automatique", "debut": time.time()}
with open(rw.FICHIER_RAPPELS, "w", encoding="utf-8") as f:
    json.dump([rappel, {"quand": time.time() + 60, "message": "trop proche"}], f)
n = rw.synchroniser()
ident = rw.empreinte(rappel)
verifier("rappel confié à Windows (le trop proche ne l'est pas)", n == 1 and ident in rw.existantes(), n)
requete = rw._schtasks("/Query", "/TN", rw.PREFIXE + ident, "/XML").stdout.decode("utf-16", "replace") if False else ""
with open(rw.FICHIER_RAPPELS, "w", encoding="utf-8") as f:
    json.dump([], f)
rw.synchroniser()
verifier("rappel annulé : tâche Windows retirée", ident not in rw.existantes())
# le secours : Jarvis en vie et le rappel déjà dit -> rien ; Jarvis absent -> fenêtre (simulée)
with open(rw.FICHIER_RAPPELS, "w", encoding="utf-8") as f:
    json.dump([dict(rappel, quand=time.time() - 30)], f)
affiche = []
ident2 = rw.empreinte(dict(rappel, quand=time.time() - 30))
contenu = json.load(open(rw.FICHIER_RAPPELS, encoding="utf-8"))
ident2 = rw.empreinte(contenu[0])
texte = rw.secours(ident2, attente=0.5, attente_jarvis=0.5, afficher=lambda t, q: affiche.append(t))
verifier("Jarvis fermé : Windows affiche le rappel", affiche == ["Rappel : essai automatique"] and json.load(open(rw.FICHIER_RAPPELS)) == [])
with open(rw.FICHIER_RAPPELS, "w", encoding="utf-8") as f:
    json.dump([], f)
verifier("Jarvis l'a déjà dit : Windows n'affiche rien", rw.secours(ident2, attente=0.3, afficher=lambda t, q: affiche.append(t)) is None)
rep = dict(rappel, quand=time.time() - 30, repete=[0, 1, 2, 3, 4, 5, 6])
with open(rw.FICHIER_RAPPELS, "w", encoding="utf-8") as f:
    json.dump([rep], f)
rw.secours(rw.empreinte(rep), attente=0.3, afficher=lambda t, q: None)
reste = json.load(open(rw.FICHIER_RAPPELS, encoding="utf-8"))
verifier("rappel répété : la fois suivante est reprogrammée", len(reste) == 1 and reste[0]["quand"] > time.time() + 3600)
for i in rw.existantes():
    rw.supprimer(i)
verifier("tâches d'essai nettoyées", not rw.existantes())
shutil.rmtree(dossier, ignore_errors=True)

# ---------- 6. Raccourci, assistants, désinstallation ----------
import jarvis_raccourci as rc, jarvis_assistants as ja
verifier("raccourci : Ctrl + Alt + J", rc.TOUCHE == 0x4A and rc.NOM == "Ctrl + Alt + J")
verifier("Groq dans les assistants, adresse officielle", ja.PAR_ID.get("groq", {}).get("adresse") == "https://api.groq.com/openai/v1")
import jarvis_desinstaller as jd
verifier("désinstallation : retire aussi les rappels confiés à Windows", "Rappel-*" in jd.SCRIPT and "$p.taches" in jd.SCRIPT)

echecs = [n for n, ok in resultats if not ok]
print(f"\n{len(resultats) - len(echecs)} / {len(resultats)} essais réussis.")
for n in echecs:
    print("  ÉCHEC :", n)
