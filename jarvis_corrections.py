# -*- coding: utf-8 -*-
"""
Jarvis - corrections des phrases mal comprises.

La reconnaissance vocale se trompe toujours de la même façon (« mes mots » pour « mets-moi »,
« youtube kit » pour « YouTube Kids »...). Ce module rétablit la bonne phrase avant que les
commandes ne la lisent. Deux listes :
  - une liste intégrée, courte et sûre, livrée avec Jarvis ;
  - une liste personnelle (corrections.json, jamais publiée) qui grandit toute seule avec l'usage :
    « Jarvis, quand tu entends mes mots, c'est mets-moi ».
Une correction ne s'applique que sur des mots entiers, et jamais sur la phrase qui sert à l'apprendre.
"""
import json
import os
import re
import threading

import jarvis_config

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER = jarvis_config.chemin("corrections.json")
ACTIVE = True
MAX_PERSONNELLES = 100

# (motif, remplacement) : seulement des erreurs sans ambiguïté
INTEGREES = (
    # « mets-moi » entendu « mes mots », « mes mois » en début de demande
    (r"^(\W*(?:jarvis\W+)?)(?:mes|mais|mai|may|met|m'est)[- ](?:mots?|mois)\b(?! de passe)", r"\1mets-moi"),
    # « YouTube Kids »
    (r"\byoutube (?:kit|kits|kid|quid|quizz|quittes?)\b", "youtube kids"),
    # « Fahrenheit » entendu « farinite », « farenheit », « farinette »
    (r"\bfa(?:h)?r(?:inite|inette|enheit|enaïte|enait|ennite|anite|inight)s?\b", "fahrenheit"),
    # « annule mes rappels » entendu « annule mais rappelle »
    (r"\bannule (?:mais|mes|met|mai) rappel(?:le|les|s)?\b", "annule mes rappels"),
    # « quels sont mes rappels » entendu « quels sont mes rappelle »
    (r"\b(quels? sont (?:mes|les) )rappelles?\b", r"\1rappels"),
    # « lis mes notes » entendu « les menottes », « limit note » (toute la demande)
    (r"^(\W*(?:jarvis\W+)?)(?:les menottes|limite? notes?|lit mes notes|li mes notes|lis mais notes|mes notes|liminate|limi notes?)(\W*)$", r"\1lis mes notes\2"),
    # « lis-moi » entendu « limois »
    (r"\blimois\b", "lis-moi"),
    # « parle à vitesse normale » entendu « pas la vitesse normale »
    (r"^(\W*(?:jarvis\W+)?)(?:pas|par|parle) (?:la|à la|a la|à) vitesse normale\b", r"\1parle à vitesse normale"),
    # « Vice City » entendu « vie cité », « envie city »
    (r"\benvie (?:city|cité|citée|citique|sity|siti)\b", "en vice city"),
    (r"\b(?:vie|vis|vise|visse|vice) (?:city|cité|citée|citique|sity|siti)\b", "vice city"),
    # « lis ce que j'ai copié » entendu « lise / lit ce que… », « lis ça » entendu « Lisa »
    (r"^(\W*(?:jarvis\W+)?)(?:lise|lit|lie|lys|lisse) (ce que|ça|ca|sa)\b", r"\1lis \2"),
    (r"^(\W*(?:jarvis\W+)?)(?:lisa|lissa|lit sa|lis sa)(\W*)$", r"\1lis ça\2"),
    (r"^(\W*(?:jarvis\W+)?)(?:lise|lisse|lys) que (j'ai|tu)\b", r"\1lis ce que \2"),
    # « annule ça » entendu « annule sa », « Anusa »
    (r"^(\W*(?:jarvis\W+)?)(?:annule sa|anusa|annulez ça|annule ca)(\W*)$", r"\1annule ça\2"),
    # « colle » entendu « call », « col » (toute la demande)
    (r"^(\W*(?:jarvis\W+)?)(?:call|col|cole|kol|colle-le)(\W*)$", r"\1colle\2"),
    # « mets le son de Chrome à 100 » entendu « … chrome hassan »
    (r"\b(son (?:de |du |d')\w+) (?:hassan|à sans|a sans|à cent|a cent|sans|cent)(\W*)$", r"\1 à 100\2"),
    # « lis-moi cette page » entendu « limoisse et page », « laisse-moi pages »
    (r"^(\W*(?:jarvis\W+)?)(?:limoisse|limoise|limois|laisse-moi|laisse moi|lis-moi|lis moi)(?: et| cette| c'est| ces| ses)? pages?\b",
     r"\1lis-moi cette page"),
    # « où j'en étais ? » entendu « bonjour n'étais », « ou j'en été »
    (r"^(\W*(?:jarvis\W+)?)(?:bonjour|ou|où|o) (?:n'|j'en |j'an |jean |j'|)(?:étais|était|été|étai)(\W*)$", r"\1où j'en étais\2"),
    # « étape suivante / précédente » entendu « et tapes suivantes », « et ta précédente »
    (r"^(\W*(?:jarvis\W+)?)et (?:ta|tape|tapes|t'as|tap) (suivante|précédente|precedente)s?\b", r"\1étape \2"),
    # « lis-moi mes mails » entendu « lis-moi m'aimait », « lis-moi n'est-mais »
    (r"^(\W*(?:jarvis\W+)?)(?:lis|lit|lie)[- ]moi (?:n'est[- ]mais|m'aimait|m'aimais|mémés?|mes mels?|mais mails?|mes mail|mes mèls?)(\W*)$",
     r"\1lis-moi mes mails\2"),
    # « profil » écrit « profit » ; « mails » entendu « mains », « mais »
    (r"\b(?:le|du|au|un|ce|mon|ton) profit\b", lambda m: m.group(0)[:-6] + "profil"),
    (r"\b(nouveaux|des|mes|les) (?:mains|mels|mèls)\b", r"\1 mails"),
    (r"\b(j'ai des nouveaux) mais\b", r"\1 mails"),
    # « rappelle-moi » écrit « rappele-moi », « rappel-moi », « appelle-moi » devant une heure ou un délai
    (r"^(\W*(?:jarvis\W+)?)(?:rappele|rappel|rapelle|rappelles?)[- ]moi\b", r"\1rappelle-moi"),
    # « 21h58, d'appeler » : la virgule après l'heure gêne la lecture
    (r"(\d{1,2} ?h ?\d{0,2}),\s+(?=d'|de )", r"\1 "),
    # « annule » écrit « un hule », « anul », « anoule » par Whisper (en début de demande)
    (r"^(\W*(?:jarvis\W+)?)(?:un hule|unulme|anul|anoule|anulle|annul)\b[,]?\s*", r"\1annule "),
    # « pause » entendu « pouche », « poche », « pose » (toute la demande, souvent pendant une vidéo)
    (r"^(\W*(?:jarvis\W+)?)(?:pouche|poche|pose|pauses|pôse|paws)(\W*)$", r"\1pause\2"),
    # « est en CE1 » entendu « est en signe », « est enseignée »
    (r"\b(?:est|et) (?:en signe|enseign[ée]e?|en ce un|en cé un|en c e un|en seins?)\b", "est en ce1"),
    # « combien j'ai d'étoiles » entendu « combien j'ai des toiles », « des toi »
    (r"\b(combien (?:j'ai|ai-je|tu as|il a|elle a)) (?:des|d')\s?(?:toiles?|toil|toi|étoile)\b", r"\1 d'étoiles"),
    # « supprime » écrit « suprime » par Whisper
    (r"\bsuprime\b", "supprime"),
    # « crée » entendu « craig » devant une demande de création
    (r"^(\W*(?:jarvis\W+)?)(?:craig|crée-le|cré|krek)\b(?=\s+(?:déjà|le|un|une|mon|ma)\s)", r"\1crée"),
    # « quelle heure est-il » entendu « quelle aurait-il » (toute la demande)
    (r"^(\W*(?:jarvis\W+)?)(?:quelle?s?|qu'elle) (?:aurait|aurais|auraient|orée?)[- ]t?-?ils?(\W*)$", r"\1quelle heure est-il\2"),
    # « donne-moi la météo » entendu « donne-moi la MTA » (toute la demande)
    (r"^(\W*(?:jarvis\W+)?)((?:donne|dis)[- ]moi|c'est quoi|quelle est) la (?:mta|m\.t\.a\.?|méta|métao)(\W*)$", r"\1\2 la météo\3"),
    # « connexion » écrit « connection »
    (r"\bconnection(s?)\b", r"connexion\1"),
)

# seulement dans une phrase de minuteur
MINUTEURS = (
    (r"\b(minuteurs? )(?:pas|pattes?|pâte)\b", r"\1pâtes"),
    (r"\b((?:pour|des|les|du) (?:les )?)(?:pattes?|pâte)\b", r"\1pâtes"),
    (r"\b((?:pour|du) (?:le )?)(?:faux|faut|fou|fours)\b", r"\1four"),
    (r"\b(minuteurs? )(?:faux|faut|fou)\b", r"\1four"),
)

# mots trop courants pour être appris comme erreur : « quand tu entends oui, c'est non » serait désastreux
INTERDITS = {"oui", "non", "jarvis", "stop", "arrête", "arrete", "ok", "merci", "bonjour", "salut", "si", "ça", "ca",
             "le", "la", "les", "un", "une", "et", "ou", "je", "tu", "il", "elle", "on", "de", "du", "des", "pas"}

_verrou = threading.Lock()
_cache = {"date": None, "liste": []}
_ENSEIGNER = re.compile(r"^\W*(?:jarvis\W+)?(?:quand|si|lorsque) tu (?:entends|comprends|as entendu|écoutes) "
                        r"(?P<a>.+?)[, ]+(?:c'est|ça veut dire|ça signifie|je dis|je voulais dire|je veux dire|cela veut dire) "
                        r"(?P<b>.+?)\W*$")
_OUBLIER = re.compile(r"^\W*(?:jarvis\W+)?(?:oublie|supprime|retire|enlève|enleve) la correction (?:de |pour |sur )?(?P<a>.+?)\W*$")
_LISTER = re.compile(r"\b(?:quel(?:le)?s?|quelques|combien de|liste (?:des|de))\b.{0,25}\bcorrections?\b|\bcorrections? (?:que )?(?:tu )?(?:connais|retenues|apprises)\b")


def _norm(texte):
    return " ".join(texte.lower().replace("’", "'").strip(" .!?,;").split())


def _lire():
    """Corrections personnelles : liste de [entendu, voulu]. Relue seulement si le fichier a changé."""
    try:
        date = os.path.getmtime(FICHIER)
    except OSError:
        _cache.update(date=None, liste=[])
        return []
    if date != _cache["date"]:
        try:
            with open(FICHIER, encoding="utf-8-sig") as f:
                donnees = json.load(f)
            liste = [(_norm(a), _norm(b)) for a, b in donnees if isinstance(a, str) and isinstance(b, str)]
        except (OSError, ValueError, TypeError):
            liste = []
        _cache.update(date=date, liste=liste)
    return _cache["liste"]


def _ecrire(liste):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump([list(x) for x in liste], f, ensure_ascii=False, indent=1)
        # mémoire à jour tout de suite : deux écritures rapprochées peuvent garder la même date de fichier
        _cache.update(date=os.path.getmtime(FICHIER), liste=[(_norm(a), _norm(b)) for a, b in liste])
        return True
    except OSError as erreur:
        print("Corrections :", erreur)
        return False


def corriger(texte):
    """Renvoie la phrase corrigée (la même si rien n'est à corriger). Ne lève jamais d'erreur."""
    if not ACTIVE or not texte:
        return texte
    try:
        if _ENSEIGNER.match(texte) or _OUBLIER.match(texte):
            return texte
        t = texte
        for motif, remplacement in INTEGREES:
            t = re.sub(motif, remplacement, t, flags=re.I)
        if re.search(r"\bminuteurs?\b|\bcombien de temps\b|\bo[uù] en sont\b", t, re.I):
            # minuteurs de cuisine : noms souvent mal entendus (« minuteur pas » pour « minuteur pâtes »)
            for motif, remplacement in MINUTEURS:
                t = re.sub(motif, remplacement, t, flags=re.I)
        for entendu, voulu in _lire():
            t = re.sub(r"(?<!\w)" + re.escape(entendu) + r"(?!\w)", voulu, t)
        if t != texte:
            print(f"(Corrigé : « {texte} » → « {t} »)")
        return t
    except Exception as erreur:
        print("Corrections :", erreur)
        return texte


def apprendre(entendu, voulu):
    """Ajoute une correction personnelle. Renvoie la phrase à dire."""
    a, b = _norm(entendu), _norm(voulu)
    if not a or not b or a == b:
        return "Ces deux phrases sont identiques, il n'y a rien à corriger."
    if len(a) < 4 or a in INTERDITS or all(m in INTERDITS for m in a.split()):
        return "Ce mot est trop courant pour que je le remplace : je risquerais de me tromper ailleurs."
    if len(a) > 60 or len(b) > 80 or re.search(r"\bjarvis\b", a):
        return "Cette correction est trop longue ou touche à mon nom, je préfère ne pas la retenir."
    with _verrou:
        liste = [(x, y) for x, y in _lire() if x != a]
        if len(liste) >= MAX_PERSONNELLES:
            return "J'ai déjà retenu cent corrections. Supprime-en une avant d'en ajouter."
        liste.append((a, b))
        if not _ecrire(liste):
            return "Je n'ai pas pu enregistrer cette correction."
        _lire()
    return f"C'est noté : quand j'entends {a}, je comprendrai {b}."


def oublier(entendu):
    a = _norm(entendu)
    with _verrou:
        liste = _lire()
        if liste and a not in [x for x, _ in liste]:
            # le mot lui-même peut être mal entendu (« chamoire » pour « chat noir ») : le plus ressemblant
            import difflib
            proche = max(liste, key=lambda c: difflib.SequenceMatcher(None, a, c[0]).ratio())
            if difflib.SequenceMatcher(None, a, proche[0]).ratio() >= 0.6:
                a = proche[0]
        reste = [(x, y) for x, y in liste if x != a]
        if len(reste) == len(liste):
            return f"Je n'ai pas de correction pour {a}."
        _ecrire(reste)
        _lire()
    return f"J'ai oublié la correction de {a}."


def nombre():
    return len(_lire())


def commande(t):
    """« Quand tu entends X, c'est Y », « oublie la correction X », « quelles corrections connais-tu »."""
    m = _ENSEIGNER.match(t.replace("’", "'"))
    if m:
        return apprendre(m.group("a"), m.group("b"))
    m = _OUBLIER.match(t.replace("’", "'"))
    if m:
        return oublier(m.group("a"))
    if _LISTER.search(t):
        n = nombre()
        if not n:
            return "Je n'ai retenu aucune correction personnelle pour l'instant."
        liste = _lire()[-5:]
        exemples = " ; ".join(f"{a} devient {b}" for a, b in liste)
        return f"J'ai retenu {n} correction{'s' if n > 1 else ''}. Les dernières : {exemples}."
    return None
