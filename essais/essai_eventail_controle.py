# -*- coding: utf-8 -*-
"""Contrôles de jarvis_eventail : (1) des phrases qui ne le concernent PAS doivent le laisser muet (pas de fausse réponse),
(2) des résultats vérifiés à la main, (3) les mêmes demandes mal entendues ou dites autrement."""
import datetime, os, sys
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
import jarvis_commandes as jc
import jarvis_eventail as ev

echecs = 0


def verifier(titre, ok, detail=""):
    global echecs
    echecs += not ok
    if not ok:
        print("ECHEC " + titre + ("  ->  " + str(detail) if detail != "" else ""))


J = datetime.date(2026, 11, 27)
MUET = [
    "ouvre chrome", "mets la table de nuit en vente", "quelle heure est-il", "mets un minuteur de 10 minutes",
    "quel est le département des ressources humaines", "lance la table de mixage", "il reste 20 pour cent de batterie",
    "monte le son à 30 pour cent", "mets la luminosité à 50 pour cent", "baisse le volume de 20 pour cent",
    "qui est le premier ministre", "est-ce que le premier ministre a parlé", "rappelle-moi dans 3 heures",
    "c'est quoi le 15", "c'est quoi le 31", "c'est quoi mm", "que vaut mi", "combien vaut le dollar", "que vaut un bitcoin",
    "dis bonjour", "dis à Marie que je rentre tard", "partage l'écran en 2", "quelle région choisir pour les vacances",
    "bonne nuit", "au revoir", "à demain", "mets de la musique", "mets pause", "quelle est la météo", "ferme la fenêtre",
    "raconte-moi une histoire", "lis mes mails", "ajoute du pain à la liste", "note que j'ai rendez-vous mardi",
    "le plus grand pays d'Europe c'est lequel déjà je crois que c'est la France mais je ne suis pas sûr du tout",
    "combien de joueurs en ligne sur Fortnite", "combien de côtés a ma maison", "quel est le symbole de la paix",
    "mets la table", "à table", "la moyenne de la classe", "c'est quoi la moyenne", "arrondis les angles",
    "je suis dans le Tarn", "il fait beau dans le Lot", "la préfecture a appelé", "va dans le département d'à côté",
    "combien de lettres j'ai reçues", "écris une lettre", "écris en lettres capitales", "mets le texte à l'envers",
    "50 euros", "plus 20 pour cent", "80 pour cent", "ça fait combien", "combien de jours", "entre midi et deux",
    "combien de jours entre mes deux rendez-vous", "change l'heure", "c'est l'heure", "le week-end dernier",
    "cherche une table basse sur Amazon", "prix TTC", "la TVA", "un gigaoctet", "3 heures", "divise l'écran",
]
for p in MUET:
    r = ev.commande(jc._propre(p), p, J) or ev.entre_deux_dates(jc._propre(p), J)
    verifier("doit rester muet : " + repr(p), r is None, r)

EXACT = [
    ("écris 71 en lettres", "soixante et onze"), ("écris 80 en lettres", "quatre-vingts"), ("écris 81 en lettres", "quatre-vingt-un"),
    ("écris 91 en lettres", "quatre-vingt-onze"), ("écris 200 en lettres", "deux cents"), ("écris 201 en lettres", "deux cent un"),
    ("écris 1000 en lettres", ": mille."), ("écris 2000 en lettres", "deux mille"), ("écris 80000 en lettres", "quatre-vingt mille"),
    ("écris 1000000 en lettres", "un million"), ("écris 2500000 en lettres", "deux millions cinq cent mille"),
    ("écris 21 en lettres", "vingt et un"), ("écris 0 en lettres", "zéro"), ("écris 300 en lettres", "trois cents"),
    ("écris 1980 en lettres", "mille neuf cent quatre-vingts"), ("écris 99 en lettres", "quatre-vingt-dix-neuf"),
    ("1994 en chiffres romains", "M, C, M, X, C, I, V"), ("4 en chiffres romains", "I, V"), ("3999 en chiffres romains", "M, M, M, C, M, X, C, I, X"),
    ("que vaut MMXXVI en chiffres romains", "2026"), ("combien vaut XLII", "42"),
    ("est-ce que 91 est un nombre premier", "divisible par 7"), ("est-ce que 2 est un nombre premier", "Oui"),
    ("est-ce que 1 est un nombre premier", "Non"), ("7 est pair ou impair", "impair"),
    ("quel est le ppcm de 4 et 6", "12"), ("quel est le pgcd de 17 et 5", "est 1."), ("factorielle de 10", "3628800"),
    ("quels sont les diviseurs de 13", ": 1, 13."), ("arrondis 2,5 à l'unité", "3"), ("arrondis 3,14159 au centième", "3,14"),
    ("3 quarts moins un demi", "1 quart"), ("un demi plus un demi", "Ça fait 1."), ("deux tiers fois trois", None),
    ("15 % de 80", "12"), ("17,5 pour cent de 200", "35"), ("80 euros moins 25 pour cent", "60 euros"),
    ("30 pour cent de réduction sur 49 euros 90", None), ("combien fait 100 euros hors taxe en TTC avec une tva à 10 pour cent", "110 euros"),
    ("combien fait 100 euros hors taxes en ttc avec une tva à 5,5 pour cent", "105 euros 50"),
    ("partage 100 euros entre 3 personnes", "33 euros 33"), ("quel pourcentage représente 1 sur 3", "33,33"),
    ("combien de jours entre le 1er mars et le 1er avril", "31 jours"), ("combien de jours entre le 25 décembre et le 1er janvier", "7 jours"),
    ("combien de jours entre le 14 juillet 1789 et le 14 juillet 2026", "86562"),
    ("combien de semaines entre le 1er janvier et le 12 février", "6 semaines"),
    ("combien de jours reste-t-il dans l'année", "34 jours"), ("combien de jours avant la fin du mois", "3 jours"),
    ("on est à quel trimestre", "quatrième"), ("on est quelle semaine", "semaine 48"),
    ("quand est le changement d'heure", "28 mars 2027"), ("c'est quand le passage à l'heure d'hiver", "octobre 2027"),
    ("dans combien de jours le week-end", "demain"),
    ("quel est le département 2A", "Corse-du-Sud"), ("quel est le département 1", "Ain"), ("quel est le département 974", "Réunion"),
    ("quel est le département 99", "Je ne connais pas"), ("quelle est la préfecture de la Haute-Garonne", "Toulouse"),
    ("quel est le numéro de la Haute-Garonne", "31"), ("quel est le numéro du Lot-et-Garonne", "47"), ("quel est le numéro du Lot", "46"),
    ("dans quelle région est le département du Nord", "Hauts-de-France"), ("quel est le chef-lieu des Landes", "Mont-de-Marsan"),
    ("combien de côtés a un octogone", "8"), ("combien de joueurs dans une équipe de rugby", "15"),
    ("combien de joueurs au handball", "7"), ("quel est le symbole chimique du fer", "F, e"),
    ("combien font 90 minutes en heures", "1,5 heure"), ("combien font 3 heures en minutes", "180 minutes"),
    ("2 jours en heures", "48 heures"), ("combien de mégaoctets dans un gigaoctet", "1000 mégaoctets"),
    ("combien de millilitres dans une cuillère à café", "5 millilitres"),
    ("comment s'écrit le mot éléphant", "E accent aigu, L, E accent aigu, P, H, A, N, T"),
    ("combien de lettres dans le mot anticonstitutionnellement", "25 lettres"), ("mets radar à l'envers", "radar"),
    ("dis bonjour à Marie", "Bonjour Marie"), ("combien de zéros dans mille", "3 zéros"),
    ("table de 12", "12 fois 10, 120"), ("2 puissance 8", "256"), ("dix puissance six", "1000000"),
    ("quelle est la moyenne de 10, 12 et 17", "13"),
]
for p, attendu in EXACT:
    t = jc._propre(p)
    r = ev.entre_deux_dates(t, J) or ev.commande(t, p, J)
    if attendu is None:
        verifier("réponse sensée ou silence : " + repr(p), r is None or "ERREUR" not in r, r)
    else:
        verifier(repr(p) + " doit contenir " + repr(attendu), bool(r) and attendu in r, r)

for n, attendu in ((16, "seize"), (70, "soixante-dix"), (72, "soixante-douze"), (100, "cent"), (101, "cent un"), (180, "cent quatre-vingts"),
                   (181, "cent quatre-vingt-un"), (1100, "mille cent"), (1001, "mille un"), (200000, "deux cent mille"),
                   (1000000000, "un milliard"), (999999, "neuf cent quatre-vingt-dix-neuf mille neuf cent quatre-vingt-dix-neuf")):
    verifier(f"en_lettres({n})", ev.en_lettres(n) == attendu, ev.en_lettres(n))
for n in range(1, 4000):
    if ev.de_romain(ev.en_romain(n)) != n:
        verifier(f"chiffres romains aller-retour {n}", False)
        break
print("phrases muettes :", len(MUET), "| résultats vérifiés :", len(EXACT), "| ECHECS :", echecs)
