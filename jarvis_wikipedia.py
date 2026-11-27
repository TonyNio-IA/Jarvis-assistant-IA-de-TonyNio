# -*- coding: utf-8 -*-
"""
JARVIS - réponses tirées de Wikipédia, pour les PC sans Claude ni autre assistant.

« qui est Victor Hugo », « c'est quoi un trou noir », « définition de photosynthèse », « parle-moi de la tour Eiffel » :
Jarvis lit le début de l'article de Wikipédia en français. Une seule demande à Wikipédia, cinq secondes au plus ;
si rien de sûr n'est trouvé, la fonction renvoie None et Jarvis propose sa recherche Google habituelle.
Ne sont pas traitées ici : les questions sur l'utilisateur ou sur Jarvis (« qui es-tu », « c'est quoi ça »),
celles qui dépendent du moment (« qui est le président », « aujourd'hui »...) : un article ne dit pas qui occupe un poste.
"""

import json
import re
import threading
import unicodedata
import urllib.parse
import urllib.request

DELAI = 5
AGENT = "Jarvis-assistant-vocal (https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio)"
ADRESSE = "https://fr.wikipedia.org/w/api.php"
MAX_CARACTERES = 380
SOURCE = " C'est ce que dit Wikipédia."
DELAI_AVANT_PATIENCE = 1.5          # Wikipédia tarde : Jarvis dit qu'il cherche, pour ne pas rester muet
PHRASE_PATIENCE = "Je regarde sur Wikipédia."
patienter = None                    # fonction qui dit une phrase (branchée par jarvis_claude), ou None

_QUI = r"qui (?:est|était|etait|sont|étaient|etaient|a été|a ete|fut)(?: donc)?|c'est qui"
_QUOI = (r"c'est quoi|qu'est[- ]ce que c'est(?: qu(?:e |'))?|qu'est[- ]ce qu(?:e |')|que (?:signifie|veut dire)|"
         r"(?:donne[- ]moi |quelle est )?(?:la )?d[ée]finition (?:de |du |des |d')|"
         r"parle[- ]moi (?:de |du |des |d')|que sais[- ]tu (?:sur |de |du |des |d')|"
         r"(?:est[- ]ce que )?tu connais|connais[- ]tu")
_DEMANDE = re.compile(r"^\W*(?:jarvis\W+)?(?:dis[- ]moi\s+)?(?:(?P<qui>" + _QUI + r")|(?:" + _QUOI + r"))\s*(?P<sujet>.+?)\W*$",
                      re.I)
# Sujets qui ne sont pas pour une encyclopédie : la personne, Jarvis, un objet montré, le moment présent
_PAS_UN_SUJET = re.compile(r"^(?:je|j'|tu|t'|il|elle|on|nous|vous|ils|elles|ça|ca|cela|ceci|ce|c'|cet|cette|ces|y|là|la$|"
                           r"mon|ma|mes|ton|ta|tes|son|sa|ses|notre|nos|votre|vos|leur|leurs|moi|toi|lui|"
                           r"de neuf|neuf|quoi|qui|que|ton nom|jarvis)\b", re.I)
_MOMENT = re.compile(r"\b(?:aujourd'hui|demain|hier|ce soir|ce matin|maintenant|actuel|actuelle|actuellement|en ce moment|"
                     r"cette année|cette semaine|à la télé|a la tele|ici|chez moi|dehors)\b", re.I)
_ARTICLE = re.compile(r"^(?:le |la |les |l'|un |une |des |du |d')", re.I)
_VIDES = {"le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "en", "au", "aux", "a", "sur", "dans", "pour"}


def _simple(texte):
    t = unicodedata.normalize("NFD", str(texte).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def sujet(brut):
    """Le sujet à chercher (« Victor Hugo »), ou None si la phrase n'est pas une question pour une encyclopédie."""
    m = _DEMANDE.match(str(brut or "").replace("’", "'").strip())
    if not m:
        return None
    s = " ".join(m.group("sujet").split()).strip(" ?!.,;:«»\"")
    if not s or len(s) < 2 or len(s.split()) > 7 or _PAS_UN_SUJET.match(s) or _MOMENT.search(s):
        return None
    if m.group("qui") and _ARTICLE.match(s):      # « qui est le maire de... » : un poste, pas une personne
        return None
    return s


def _resume(extrait):
    t = re.sub(r"\[[^\]]{0,12}\]", "", str(extrait or ""))
    for _ in range(3):                                         # parenthèses (prononciation, sigles...), même imbriquées
        t = re.sub(r"\s*\([^()]*\)", "", t)
    t = " ".join(t.split())
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    if not t:
        return ""
    phrases, total = [], 0
    for phrase in re.split(r"(?<=[.!?])\s+(?=[A-ZÉÈÊÀÂÎÔÛÇ0-9«])", t):
        if phrases and total + len(phrase) > MAX_CARACTERES:
            break
        phrases.append(phrase)
        total += len(phrase) + 1
        if len(phrases) >= 2:
            break
    resultat = " ".join(phrases)
    if len(resultat) > MAX_CARACTERES + 120:                   # une seule phrase, très longue : coupée proprement
        resultat = resultat[:MAX_CARACTERES].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return resultat


def chercher(s):
    """(titre, résumé) du meilleur article pour ce sujet, ou None."""
    parametres = {"action": "query", "format": "json", "generator": "search", "gsrsearch": s, "gsrlimit": "1",
                  "gsrnamespace": "0", "prop": "extracts|pageprops", "exintro": "1", "explaintext": "1",
                  "exsentences": "4", "redirects": "1", "ppprop": "disambiguation"}
    requete = urllib.request.Request(ADRESSE + "?" + urllib.parse.urlencode(parametres), headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=DELAI) as r:
        donnees = json.load(r)
    pages = list((donnees.get("query") or {}).get("pages", {}).values())
    if not pages:
        return None
    page = pages[0]
    if "disambiguation" in (page.get("pageprops") or {}):      # page d'homonymie : rien de sûr à lire
        return None
    titre, texte = str(page.get("title") or ""), _resume(page.get("extract"))
    if not titre or len(texte) < 40:
        return None
    voulu = [m for m in _simple(s).split() if m not in _VIDES and len(m) > 1]
    trouve = set((_simple(titre) + " " + _simple(texte)).split())
    if not voulu or sum(1 for m in voulu if m in trouve) * 2 < len(voulu):     # l'article ne parle pas du sujet demandé
        return None
    if not any(m in set(_simple(titre).split()) for m in voulu):
        return None
    return titre, texte


def repondre(brut):
    """La phrase à dire, ou None (pas une question de ce genre, rien trouvé, pas d'Internet)."""
    s = sujet(brut)
    if not s:
        return None
    retour = {}

    def travail():
        try:
            retour["r"] = chercher(s)
        except Exception as erreur:
            print("Wikipédia :", type(erreur).__name__, erreur)

    fil = threading.Thread(target=travail, daemon=True, name="wikipedia")
    fil.start()
    fil.join(DELAI_AVANT_PATIENCE)
    if fil.is_alive() and patienter:                # Internet lent : une phrase d'attente, une seule fois
        try:
            patienter(PHRASE_PATIENCE)
        except Exception:
            pass
    fil.join(DELAI + 1)
    resultat = retour.get("r")
    if not resultat:
        return None
    print("(Wikipédia : article «", resultat[0], "».)")
    return resultat[1] + SOURCE
