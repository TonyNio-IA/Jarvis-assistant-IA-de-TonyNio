# -*- coding: utf-8 -*-
"""Éventail des questions auxquelles Jarvis répond SANS Claude. Seules les fonctions de connaissance sont appelées (heure,
calendrier, savoir, calculs, conversions) : aucune action sur le PC, rien n'est ouvert ni modifié.
  python essai_eventail_local.py           -> résumé par famille
  python essai_eventail_local.py tout      -> chaque phrase et sa réponse"""
import os, re, sys
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
import jarvis_commandes as jc
import jarvis_local, jarvis_savoir, jarvis_pratique, jarvis_extras
try:
    import jarvis_eventail
except ImportError:
    jarvis_eventail = None


def repondre(phrase):
    t = jc._propre(phrase)
    for f in (lambda: jc._heure() if re.search(r"\bquelle heure\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t) else None,
              lambda: jarvis_eventail.entre_deux_dates(t) if jarvis_eventail else None,
              lambda: jarvis_local.calendrier(t),
              lambda: jarvis_savoir.commande(t, phrase),
              lambda: jarvis_eventail.commande(t, phrase) if jarvis_eventail else None,
              lambda: jc._date() if re.search(r"\b(quel jour|quelle date|on est le combien|nous sommes le combien)\b", t)
              and not re.search(r"\b(sera|était|demain|hier)\b", t) else None,
              lambda: jarvis_extras.commande_heure_ailleurs(t),
              lambda: jarvis_local._hasard(jarvis_local._phrase(t), jarvis_local._phrase(t, accents=True)),
              lambda: jarvis_local._conversation(jarvis_local._phrase(t)),
              lambda: jarvis_local._calendrier(jarvis_local._phrase(t)),
              lambda: jarvis_pratique.commande_conversion(t),
              lambda: jarvis_pratique.commande_calcul(t)):
        try:
            r = f()
        except Exception as e:
            r = "ERREUR " + type(e).__name__ + " : " + str(e)
        if r:
            return r
    return None


FAMILLES = {
 "pourcentages et argent": [
    "combien font 20 pour cent de 150", "15 % de 80", "quel est 30 pour cent de 200", "calcule 5 pour cent de 1200",
    "un article à 80 euros avec 30 pour cent de réduction", "80 euros moins 20 pour cent", "50 euros plus 20 pour cent",
    "combien fait 100 euros hors taxe en TTC", "quel est le prix TTC de 250 euros hors taxes", "120 euros TTC ça fait combien hors taxe",
    "quel pourcentage représente 30 sur 120", "30 sur 120 ça fait quel pourcentage", "partage 90 euros en 4",
    "combien de pourboire pour 60 euros à 10 pour cent"],
 "calculs": [
    "combien font 12 fois 12", "combien font 144 divisé par 12", "7 plus 8", "combien font 3 puissance 4", "2 puissance 10",
    "racine carrée de 144", "le carré de 15", "la moitié de 250", "le double de 37", "combien font 1000 moins 387",
    "combien font 2 virgule 5 fois 4", "quelle est la table de 7", "récite la table de 9", "table de multiplication de 8",
    "est-ce que 97 est un nombre premier", "17 est-il premier", "est-ce que 42 est pair", "48 est pair ou impair",
    "quels sont les diviseurs de 36", "quel est le pgcd de 48 et 36", "factorielle de 5", "arrondis 3,14159 à deux décimales",
    "quelle est la moyenne de 12 15 et 18", "combien font un tiers plus un quart"],
 "nombres": [
    "écris 2024 en chiffres romains", "2024 en chiffres romains", "que vaut XIV en chiffres romains", "combien vaut MCMXC",
    "comment s'écrit 80 en lettres", "écris 1999 en lettres", "combien de zéros dans un million", "combien de zéros dans un milliard"],
 "dates": [
    "quel jour serons-nous dans 10 jours", "quelle date serons-nous dans 3 semaines", "quel jour était-on il y a 15 jours",
    "quelle date dans 100 jours", "combien de jours entre le 1er janvier et le 14 juillet", "combien de jours avant Noël",
    "combien de semaines avant Noël", "combien de jours avant les vacances d'été", "quel est le numéro de la semaine",
    "on est quelle semaine", "est-ce que 2028 est une année bissextile", "2024 est-elle bissextile",
    "combien de jours reste-t-il dans l'année", "combien de jours restent avant la fin de l'année", "on est à quel trimestre",
    "quel jour tombe Noël cette année", "c'est quand Pâques l'année prochaine", "quand est le changement d'heure",
    "c'est quand le prochain jour férié", "quel est le prochain jour férié", "combien de jours fériés en mai",
    "quel jour de la semaine est le 1er mai", "dans combien de jours le week-end", "combien de jours avant la fin du mois",
    "quel jour est-on", "on est quel mois", "en quelle année sommes-nous", "quelle saison sommes-nous"],
 "départements et régions": [
    "quel est le département 82", "c'est quoi le département 31", "quel est le numéro du département du Tarn",
    "quel est le numéro de la Haute-Garonne", "quelle est la préfecture du Tarn-et-Garonne", "quel est le chef-lieu du Lot",
    "dans quelle région est le Tarn-et-Garonne", "dans quel département est Toulouse", "quelle région pour le département 33",
    "combien de départements en France", "combien y a-t-il de régions en France", "quels sont les départements d'Occitanie"],
 "culture générale stable": [
    "quelle est la capitale de l'Italie", "quelle est la capitale de l'Allemagne", "capitale du Brésil",
    "combien y a-t-il de continents", "combien de planètes dans le système solaire", "quelle est la plus grande planète",
    "combien de jours dans une année", "combien d'heures dans une semaine", "combien de minutes dans une journée",
    "combien de secondes dans une heure", "combien de côtés a un hexagone", "combien de joueurs dans une équipe de foot",
    "quelle est la vitesse de la lumière", "à quelle température l'eau bout", "à quelle température l'eau gèle",
    "combien de lettres dans l'alphabet", "combien de touches sur un piano", "quelles sont les couleurs de l'arc-en-ciel",
    "combien d'os dans le corps humain", "quelle est la formule de l'eau", "quel est le symbole chimique de l'or",
    "quelle est la plus haute montagne du monde", "quel est le plus long fleuve de France", "quel est le plus grand océan"],
 "conversions": [
    "combien font 10 miles en kilomètres", "convertis 5 pieds en mètres", "100 degrés fahrenheit en celsius",
    "combien de grammes dans une livre", "2 litres en centilitres", "combien font 3 heures en minutes",
    "combien font 90 minutes en heures", "combien de kilos font 150 livres", "un pouce en centimètres",
    "combien de centimètres dans un mètre", "combien de millilitres dans une cuillère à soupe", "200 grammes de farine en tasses",
    "combien font 50 euros en dollars", "convertis 1 gigaoctet en mégaoctets", "combien de mètres dans un mile",
    "30 nœuds en kilomètres heure", "combien font 5000 pas en kilomètres"],
 "épeler et mots": [
    "épelle le mot anticonstitutionnellement", "comment s'écrit le mot rythme", "combien de lettres dans le mot ordinateur",
    "combien de syllabes dans chocolat", "mets bonjour à l'envers", "quel est le pluriel de cheval"],
 "Jarvis lui-même": [
    "comment tu t'appelles", "qui es-tu", "qui t'a créé", "quel âge as-tu", "tu es en quelle version", "que sais-tu faire",
    "comment ça va", "merci", "bonne nuit", "tu es là", "est-ce que tu m'entends", "raconte-moi une blague",
    "dis-moi quelque chose de gentil", "pile ou face", "lance un dé", "donne-moi un nombre entre 1 et 100",
    "choisis entre pizza et sushi", "dis bonjour à Marie"],
}

tout = len(sys.argv) > 1 and sys.argv[1] == "tout"
total = bons = 0
manques = []
for famille, phrases in FAMILLES.items():
    ok = 0
    for p in phrases:
        r = repondre(p)
        total += 1
        if r and not str(r).startswith("ERREUR"):
            ok += 1
            bons += 1
        else:
            manques.append((famille, p, r))
        if tout:
            print(("   OK  " if r and not str(r).startswith("ERREUR") else "   --  ") + p + "  ->  " + str(r)[:140])
    print("%-28s %3d / %-3d" % (famille, ok, len(phrases)))
print("TOTAL %d / %d (%d %%)" % (bons, total, round(100 * bons / total)))
if not tout:
    print("SANS RÉPONSE LOCALE :")
    for famille, p, r in manques:
        print("   [%s] %s%s" % (famille, p, ("  ->  " + r) if r else ""))
