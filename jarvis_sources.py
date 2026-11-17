"""
JARVIS - les sources du point du jour, relevées directement depuis ce PC.

Pourquoi : l'outil de lecture de pages de Claude (WebFetch) passe par les serveurs d'Anthropic, et certains
sites refusent ces connexions (Logic-Sunrise, par exemple : « erreur en lisant la page »). Les recherches
web, elles, ne donnent pas toujours la date des articles, et Claude préférait alors ne rien dire.
Jarvis lit donc lui-même, depuis le PC :
  - les titres du jour de grands médias (flux RSS de franceinfo et du Monde, réglables dans config.json :
    "actualites": ["https://...rss", ...]) ;
  - la page d'accueil du site suivi (config.json, "site"), réduite à son texte avec les dates.
Ces relevés sont joints à la demande du point du jour ; Claude n'a plus qu'à choisir et raconter.
"""

import email.utils
import http.cookiejar
import html
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

import jarvis_config

ACTUALITES = jarvis_config._lu.get("actualites") or [
    "https://www.francetvinfo.fr/titres.rss",
    "https://www.lemonde.fr/rss/une.xml",
]
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DELAI = 15                 # secondes par page
HEURES_ACTU = 30           # titres publiés depuis moins de 30 heures
MAX_TITRES = 15            # par média
MAX_SITE = 5000            # caractères de la page du site suivi


def lire(url):
    """Contenu texte d'une adresse (avec le bon encodage)."""
    if not re.match(r"https?://", url):
        url = "https://" + url
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "fr-FR,fr;q=0.9"})
    # avec les cookies : certains sites renvoient sinon sans fin vers la même page (« redirect loop »)
    ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with ouvreur.open(requete, timeout=DELAI) as reponse:
        brut = reponse.read()
        codage = reponse.headers.get_content_charset()
    if not codage:
        m = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", brut[:3000], re.I) or \
            re.search(rb"""encoding=["']([\w-]+)""", brut[:200])
        codage = m.group(1).decode() if m else "utf-8"
    try:
        return brut.decode(codage, "replace")
    except LookupError:
        return brut.decode("utf-8", "replace")


def _propre(texte):
    texte = html.unescape(re.sub(r"<[^>]+>", " ", texte or ""))
    return " ".join(texte.split())


def titres_rss(url):
    """Les titres récents d'un flux RSS : « HH:MM titre : résumé court »."""
    racine = ET.fromstring(lire(url).encode("utf-8"))
    limite = time.time() - HEURES_ACTU * 3600
    lignes = []
    for item in racine.iter("item"):
        titre = _propre(item.findtext("title"))
        if not titre:
            continue
        date = item.findtext("pubDate")
        quand = ""
        try:
            moment = email.utils.parsedate_to_datetime(date).timestamp()
            if moment < limite:
                continue
            quand = time.strftime("%d/%m %H:%M", time.localtime(moment)) + " "
        except (TypeError, ValueError, AttributeError):
            pass
        resume = _propre(item.findtext("description"))
        if resume and resume != titre:
            resume = resume[:160].rsplit(" ", 1)[0] + "…" if len(resume) > 160 else resume
            titre += " : " + resume
        lignes.append("- " + quand + titre)
        if len(lignes) >= MAX_TITRES:
            break
    return lignes


def actualites():
    """Texte à joindre au point du jour, ou « » si aucun média n'a pu être lu."""
    blocs = []
    for url in ACTUALITES:
        try:
            lignes = titres_rss(url)
        except Exception as erreur:
            print("Actualités illisibles :", url, erreur)
            continue
        if lignes:
            nom = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
            blocs.append(f"Titres de {nom} :\n" + "\n".join(lignes))
    return "\n\n".join(blocs)


def page_du_site(adresse):
    """Le texte de la page d'accueil du site suivi (titres et dates), ou « » si elle ne répond pas."""
    try:
        page = lire(adresse)
    except Exception as erreur:
        print("Site du point du jour illisible :", adresse, erreur)
        return ""
    page = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<(?:/li|/p|/div|/h\d|br|/tr|/article)\b[^>]*>", "\n", page)
    lignes, vues = [], set()
    for ligne in _propre_lignes(page):
        if len(ligne) >= 12 and ligne not in vues:
            vues.add(ligne)
            lignes.append(ligne)
    texte = "\n".join(lignes)
    return texte[:MAX_SITE]


def _propre_lignes(page):
    for ligne in page.split("\n"):
        yield _propre(ligne)
