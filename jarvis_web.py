"""
JARVIS - le navigateur à la voix (Chrome, Edge, Firefox...).

  - « clique sur Connexion », « clique sur le bouton Accepter », « clique sur la deuxième vidéo » :
    Jarvis lit la page comme un lecteur d'écran (l'accessibilité de Windows, « UI Automation »),
    trouve le bouton ou le lien dont le nom ressemble le plus à ce que tu as dit, puis l'active ;
  - « fais défiler », « descends », « remonte », « tout en haut », « tout en bas » ;
  - « reviens en arrière », « page précédente », « page suivante » (le lien « Suivant » de la page
    s'il existe, sinon la page d'après dans l'historique) ;
  - « lis-moi cette page » (texte principal, sans les menus) ; « résume cette page » est confié à
    Claude avec le texte de la page (voir jarvis_ecran.complement) ;
  - « cherche … sur YouTube / Amazon / Google / Wikipédia / Leboncoin / Google Maps ».
Chaque fonction « commande_... » renvoie la phrase à dire, ou None si la demande ne la concerne pas.
"""

import ctypes
import ctypes.wintypes
import difflib
import os
import re
import threading
import time
import unicodedata
import urllib.parse

import jarvis_ecran
import jarvis_pratique

user32 = ctypes.windll.user32
NAVIGATEURS = ("chrome", "msedge", "firefox", "opera", "brave", "vivaldi", "iexplore")
TEXTE_LU_MAX = 1200            # caractères lus au plus par « lis-moi cette page »


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _norme(t):
    t = _sans_accents(t.lower().replace("’", "'").replace("œ", "oe"))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _programme_actif():
    """Nom du programme de la fenêtre au premier plan (« chrome »), ou ""."""
    try:
        import psutil
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower().removesuffix(".exe")
    except Exception:
        return ""


def navigateur_actif():
    return _programme_actif() in NAVIGATEURS


# ---------- Recherche sur un site ----------

_SITES = [
    (r"youtube", "YouTube", "https://www.youtube.com/results?search_query={}"),
    (r"amazon", "Amazon", "https://www.amazon.fr/s?k={}"),
    (r"google maps|maps|la carte|google map", "Google Maps", "https://www.google.com/maps/search/{}"),
    (r"google images|images", "Google Images", "https://www.google.com/search?tbm=isch&q={}"),
    (r"google|internet|le web|le net", "Google", "https://www.google.com/search?q={}"),
    (r"wikip[ée]dia", "Wikipédia", "https://fr.wikipedia.org/w/index.php?search={}"),
    (r"le ?bon ?coin|leboncoin", "Leboncoin", "https://www.leboncoin.fr/recherche?text={}"),
    (r"cdiscount", "Cdiscount", "https://www.cdiscount.com/search/10/{}.html"),
    (r"vinted", "Vinted", "https://www.vinted.fr/catalog?search_text={}"),
    (r"ebay", "eBay", "https://www.ebay.fr/sch/i.html?_nkw={}"),
]
_RECHERCHE = re.compile(r"^\W*(?:jarvis\W+)?(?:cherche|recherche|cherches|trouve|regarde|tape)(?:-moi)?\s+(?P<quoi>.+?)\s+"
                        r"(?:sur|dans|avec)\s+(?P<site>.+?)\W*$")


def commande_recherche(t):
    m = _RECHERCHE.match(t.replace("’", "'"))
    if not m:
        return None
    site = m.group("site").strip()
    for motif, nom, adresse in _SITES:
        if re.fullmatch(r"(?:le |la |l')?(?:site )?(?:" + motif + r")(?: \.fr| point fr)?", site):
            quoi = re.sub(r"^(?:des |de la |du |de l'|les |le |la |l'|un |une )", "", m.group("quoi").strip())
            if not quoi or re.fullmatch(r"(?:le |un )?fichiers?|documents?", quoi):
                return None
            os.startfile(adresse.format(urllib.parse.quote(quoi)))
            return f"Je cherche {quoi} sur {nom}."
    return None


# ---------- Clavier dans la page ----------

def _touche_plus_tard(*codes, repetitions=1):
    threading.Timer(0.3, jarvis_pratique.touches, args=codes, kwargs={"repetitions": repetitions}).start()


_NAVIGATION = [
    # « fait défiler », « c'est défilé », « ces défilés » : façons dont « fais défiler » est souvent entendu
    (r"(?:fais |fait |faire |c'est |ces |ses |sais |s'est )?(?:défiler|défile|defile|defiler|défilé|défilés|défilée)"
     r"(?: la page| encore| un peu)?(?: vers le bas| en bas)?|descends|descend|descends la page|plus bas|"
     r"page vers le bas|(?:fais|fait) descendre(?: la page)?", (0x22,), "C'est fait."),
    # « remont », « re monte », « romande », « romante » : façons dont « remonte » est souvent entendu
    (r"(?:fais |fait |faire )?(?:défiler|défile|defile|défilé)(?: la page)? vers le haut|remonte|remontes|remont|"
     r"re monte|romande|romante|remonte la page|remonte un peu|plus haut|page vers le haut|"
     r"(?:fais|fait) remonter(?: la page)?", (0x21,), "C'est fait."),
    (r"(?:va |remonte |retourne )?(?:tout en haut|en haut de la page|au début de la page|au debut de la page)",
     (0x24,), "Je remonte en haut."),
    (r"(?:va |descends )?(?:tout en bas|en bas de la page|à la fin de la page|a la fin de la page)", (0x23,),
     "Je descends tout en bas."),
    (r"(?:reviens|revenir|reviennent|retourne|retourner|va|reviens-en)(?: en arrière| à l'arrière| a l'arriere|"
     r" à la page précédente| a la page precedente)|"
     r"page précédente|page precedente|retour(?: en arrière)?|précédent|precedent", (jarvis_pratique.ALT, 0x25),
     "Je reviens à la page précédente."),
]


def commande_navigation(t):
    phrase = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    for motif, codes, reponse in _NAVIGATION:
        if re.fullmatch(motif, phrase):
            _touche_plus_tard(*codes)
            return reponse
    if re.fullmatch(r"(?:va |passe )?(?:à |a )?(?:la )?page suivante|(?:les )?résultats suivants|suivant", phrase):
        if navigateur_actif():
            try:
                cible = _meilleur(["page suivante", "suivant", "suivante", "next", "plus de résultats", ">"], seuil=0.85)
            except Exception as erreur:
                print("Page suivante :", erreur)
                cible = None
            if cible is not None:
                _activer(cible)
                return "Page suivante."
        _touche_plus_tard(jarvis_pratique.ALT, 0x27)
        return "Page suivante."
    return None


# ---------- Clic sur un bouton ou un lien (UI Automation) ----------

_uia = None
_UIA = None
_TYPES = {50000: "bouton", 50002: "case", 50003: "liste", 50004: "champ", 50005: "lien", 50007: "élément",
          50011: "menu", 50013: "option", 50019: "onglet", 50020: "texte", 50026: "groupe"}
_CLIQUABLES = (50000, 50002, 50003, 50004, 50005, 50007, 50011, 50013, 50019)


def _automation():
    global _uia, _UIA
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    if _uia is None:
        import comtypes.client
        _UIA = comtypes.client.GetModule("UIAutomationCore.dll")
        _uia = comtypes.client.CreateObject(_UIA.CUIAutomation, interface=_UIA.IUIAutomation)
    return _uia


class _Element:
    def __init__(self, brut, nom, rect, genre, dans_page=True):
        self.brut, self.nom, self.genre, self.dans_page = brut, nom, genre, dans_page
        self.gauche, self.haut, self.droite, self.bas = rect.left, rect.top, rect.right, rect.bottom


def _elements_visibles(hors_ecran=False):
    """Boutons, liens, onglets... visibles dans la fenêtre au premier plan.
    hors_ecran=True : aussi ceux de la page situés plus bas ou plus haut (pour « le troisième résultat »)."""
    uia = _automation()
    hwnd = user32.GetForegroundWindow()
    racine = uia.ElementFromHandle(hwnd)
    condition = None
    for genre in _CLIQUABLES:
        c = uia.CreatePropertyCondition(30003, genre)          # 30003 = type de contrôle
        condition = c if condition is None else uia.CreateOrCondition(condition, c)
    cache = uia.CreateCacheRequest()
    for propriete in (30005, 30001, 30003, 30022):             # nom, rectangle, type, hors de l'écran
        cache.AddProperty(propriete)
    trouves = racine.FindAllBuildCache(4, condition, cache)     # 4 = tous les descendants
    # Les éléments de la page elle-même (dans le « document ») passent avant ceux du navigateur (barre d'adresse...)
    page = set()
    try:
        documents = racine.FindAll(4, uia.CreatePropertyCondition(30003, 50030))
        for d in range(documents.Length):
            dans = documents.GetElement(d).FindAllBuildCache(4, condition, cache)
            for i in range(dans.Length):
                e = dans.GetElement(i)
                r = e.CachedBoundingRectangle
                page.add((e.CachedName, r.left, r.top, r.right, r.bottom))
    except Exception:
        page = None
    fen = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(fen))
    elements = []
    for i in range(trouves.Length):
        e = trouves.GetElement(i)
        try:
            nom = (e.CachedName or "").strip()
            rect = e.CachedBoundingRectangle
            if not nom or rect.right - rect.left < 2 or rect.bottom - rect.top < 2:
                continue
            if not hors_ecran and (e.CachedIsOffscreen or rect.bottom < fen.top or rect.top > fen.bottom
                                   or rect.right < fen.left or rect.left > fen.right):
                continue
            dans_page = page is None or (e.CachedName, rect.left, rect.top, rect.right, rect.bottom) in page
            elements.append(_Element(e, nom, rect, e.CachedControlType, dans_page))
        except Exception:
            continue
    return elements


_PETITS_MOTS = {"le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "en", "et", "a", "au", "aux", "sur", "pour"}
_DUREE = re.compile(r"\s*\d+\s+(?:heures?|minutes?|secondes?)(?:\s+et\s+\d+\s+(?:minutes?|secondes?))?\s*$")   # \s : aussi l'espace insécable


def _couverture(a, b):
    """Part des mots importants dits (a) que l'on retrouve, même mal prononcés, dans le nom (b)."""
    importants = [m for m in a.split() if m not in _PETITS_MOTS] or a.split()
    mots_b = b.split()
    trouves = sum(1 for m in importants if m in mots_b or difflib.get_close_matches(m, mots_b, n=1, cutoff=0.8))
    return trouves / len(importants), len(importants)


def _note(cherche, nom):
    """Ressemblance entre ce qui a été dit et le nom d'un élément (0 à 1)."""
    nom = _DUREE.sub("", nom)                       # YouTube ajoute la durée au nom des vidéos
    a, b = _norme(cherche), _norme(nom)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    mots_b = b.split()
    if a in b and (b.startswith(a) or f" {a}" in f" {b}"):
        return 0.93 - min(0.1, 0.004 * (len(b) - len(a)))
    n = len(a.split())
    meilleur = difflib.SequenceMatcher(None, a, b).ratio()
    for i in range(len(mots_b)):                                  # le passage du nom qui ressemble le plus
        morceau = " ".join(mots_b[i:i + n])
        meilleur = max(meilleur, difflib.SequenceMatcher(None, a, morceau).ratio() - 0.05)
    part, nombre = _couverture(a, b)                              # tous les mots importants sont là
    if part == 1 and nombre >= 2:
        meilleur = max(meilleur, 0.86 - min(0.06, 0.002 * len(mots_b)))
    elif part >= 0.75 and nombre >= 3:
        meilleur = max(meilleur, 0.79)
    return meilleur


def _meilleur(cherches, seuil=0.78, elements=None):
    elements = _elements_visibles() if elements is None else elements
    # D'abord dans la page, ensuite seulement dans le navigateur lui-même
    dans_la_page = [e for e in elements if e.dans_page]
    if dans_la_page and len(dans_la_page) < len(elements):
        trouve = _meilleur(cherches, seuil, dans_la_page)
        if trouve is not None:
            return trouve
    choix = None
    for e in elements:
        note = max(_note(c, e.nom) for c in cherches)
        if note >= seuil and (choix is None or note > choix[0] + 0.01
                              or (abs(note - choix[0]) <= 0.01 and (e.haut, e.gauche) < (choix[1].haut, choix[1].gauche))):
            choix = (note, e)
    return choix[1] if choix else None


def _activer(e):
    """Active l'élément : par l'accessibilité (sans bouger la souris), sinon par un vrai clic en son centre."""
    if e.genre == 50004:                                          # un champ de saisie : on y place le curseur
        try:
            e.brut.SetFocus()
            return
        except Exception:
            pass
    try:
        motif = e.brut.GetCurrentPattern(10000)                  # 10000 = « Invoke » (activer)
        if motif:
            motif.QueryInterface(_UIA.IUIAutomationInvokePattern).Invoke()
            return
    except Exception:
        pass
    x, y = (e.gauche + e.droite) // 2, (e.haut + e.bas) // 2
    ancien = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(ancien))
    user32.SetCursorPos(x, y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.SetCursorPos(ancien.x, ancien.y)


_ORDINAUX = {"premier": 1, "première": 1, "premiere": 1, "1er": 1, "1re": 1, "deuxième": 2, "deuxieme": 2,
             "second": 2, "seconde": 2, "2e": 2, "troisième": 3, "troisieme": 3, "3e": 3, "quatrième": 4,
             "quatrieme": 4, "4e": 4, "cinquième": 5, "cinquieme": 5, "5e": 5, "dernier": -1, "dernière": -1,
             "derniere": -1}
_CLIC = re.compile(r"^\W*(?:jarvis\W+)?(?:clique|cliques|clic|clik|cliquer|appuie|appuies|appuyer|sélectionne|selectionne|"
                   r"choisis|ouvre)\s+(?:sur |dans )?(?P<cible>.+?)\W*$")


# « lance la deuxième vidéo », « mets la troisième vidéo », « la deuxième vidéo » (dans un navigateur) ;
# « lance » est souvent entendu « Lille » ou « Lila »
_ORDINAL_SANS_CLIC = re.compile(r"^\W*(?:jarvis\W+)?(?:(?:lance|lances|lancer|mets|met|mais|joue|regarde|montre|"
                                r"prends|prend|lille|lila|lis|lit)(?:-moi| moi)?\s+)?(?:sur\s+)?"
                                r"(?P<cible>(?:le |la |l')?\S+ (?:vidéo|video|résultat|resultat|lien))\W*$")


def commande_clic(t):
    o = _ORDINAL_SANS_CLIC.match(t.replace("’", "'").lower())
    if o and o.group("cible").split()[-2] in _ORDINAUX and navigateur_actif():
        t = "clique sur " + o.group("cible")
    m = _CLIC.match(t.replace("’", "'"))
    if not m:
        return None
    cible = m.group("cible").strip(" «»\"'")
    ouvre = re.match(r"^\W*(?:jarvis\W+)?ouvre\b", t)
    # « ouvre » ne concerne la page que pour « ouvre le lien… » ou « ouvre la deuxième vidéo » dans un navigateur
    if ouvre and not (navigateur_actif() and re.match(r"(?:le |la |l')?(?:lien|vidéo|video|résultat|article)\b|"
                                                     r"(?:le |la )?(?:\S+) (?:lien|vidéo|video|résultat|article)\b", cible)):
        return None
    if re.fullmatch(r"entrée|entree|la touche entrée|tout|ça|ca|ici", cible):
        return None
    if not navigateur_actif() and not re.match(r"^\W*(?:jarvis\W+)?(?:clique|cliques|clic|clik|cliquer)\b", t):
        return None
    try:
        elements = _elements_visibles()
        if not elements:                     # Chrome n'active sa description de la page qu'à la première demande
            time.sleep(1.0)
            elements = _elements_visibles()
    except Exception as erreur:
        print("Lecture de la page impossible :", erreur)
        return "Je n'arrive pas à lire les boutons de cette fenêtre."
    # « la deuxième vidéo », « le premier lien », « le troisième résultat »
    o = re.fullmatch(r"(?:sur )?(?:le |la |l')?(?P<rang>\S+) (?P<quoi>vidéo|video|lien|résultat|resultat|article|"
                     r"élément|element|bouton)s?", cible)
    if o and o.group("rang") in _ORDINAUX:
        rang = _ORDINAUX[o.group("rang")]
        quoi = o.group("quoi")
        genres = (50000,) if quoi == "bouton" else (50005,)
        long_titre = quoi in ("vidéo", "video", "résultat", "resultat", "article")
        elements = _elements_visibles(hors_ecran=True)       # « le troisième » peut être plus bas dans la page
        if not any(e.dans_page for e in elements):          # Chrome décrit la page à la première demande
            time.sleep(1.0)
            elements = _elements_visibles(hors_ecran=True)
        dans_page = [e for e in elements if e.dans_page]
        if quoi in ("vidéo", "video"):
            videos = [e for e in dans_page if e.genre == 50005 and _DUREE.search(e.nom)]
            if videos:                                        # YouTube : les titres finissent par la durée
                dans_page = videos
        elif quoi in ("résultat", "resultat", "lien", "article"):
            sites = [e for e in dans_page if e.genre == 50005 and re.search(r"https?://|www\.|›", e.nom)]
            if sites:                                         # Google, Bing... : le titre d'un résultat contient son adresse
                dans_page = sites
        vus, liste = set(), []
        for e in sorted(dans_page, key=lambda e: (e.haut // 40, e.gauche)):   # ligne par ligne, puis de gauche à droite
            if e.genre not in genres or e.nom in vus:
                continue
            # un titre de vidéo ou de résultat : au moins 6 mots, et pas un lien d'information (« À propos de ces résultats »)
            if long_titre and (len(e.nom.split()) < 6 or re.match(r"(?i)(?:à propos|a propos|en savoir plus|"
                                                                   r"plus d'infos|paramètres|aide)\b", e.nom)):
                continue
            vus.add(e.nom)
            liste.append(e)
        if not liste or abs(rang) > len(liste) or (rang > 0 and rang > len(liste)):
            return f"Je ne trouve pas de {quoi} numéro {abs(rang)} sur la page."
        choisi = liste[rang - 1] if rang > 0 else liste[-1]
        _activer(choisi)
        nom = re.split(r"\s+(?:https?://|www\.)", _DUREE.sub("", choisi.nom))[0]     # sans l'adresse du site
        nom = re.sub(r"^(?:Vidéo|Video)\s+", "", nom)          # YouTube Kids : « Vidéo <titre> »
        return f"J'ouvre « {nom[:80]} »."
    cible = re.sub(r"^(?:le |la |l'|les |un |une )?(?:bouton|lien|onglet|case|menu|option|champ|icône|icone|zone)"
                   r"(?: de| du| des| d'| à| a)?\s+", "", cible)
    cible = re.sub(r"^(?:le |la |l'|les |un |une )", "", cible).strip(" «»\"'")
    if re.fullmatch(r"(?:barre|zone|champ|case) (?:de |d')?(?:recherche|rechercher)|recherche", cible):
        cible = "rechercher"
    if not cible:
        return None
    choisi = _meilleur([cible], elements=elements)
    if choisi is None:                       # la page vient peut-être d'être décrite pour la première fois
        time.sleep(1.0)
        try:
            choisi = _meilleur([cible])
        except Exception:
            choisi = None
    if choisi is None:
        return f"Je ne trouve pas « {cible} » sur l'écran."
    _activer(choisi)
    return f"Je clique sur « {_DUREE.sub('', choisi.nom)[:60]} »."


# ---------- Le texte de la page ----------

def texte_de_la_page():
    """Copie le texte de la page (Ctrl+A puis Ctrl+C), sans perdre ce que le presse-papiers contenait."""
    ancien = jarvis_ecran.lire_presse_papiers()
    jarvis_ecran.ecrire_presse_papiers("")
    jarvis_pratique.touches(jarvis_pratique.CTRL, 0x41)
    time.sleep(0.2)
    jarvis_pratique.touches(jarvis_pratique.CTRL, 0x43)
    texte = ""
    for _ in range(10):
        time.sleep(0.15)
        texte = jarvis_ecran.lire_presse_papiers()
        if texte:
            break
    jarvis_pratique.touches(0x24)              # fin de la sélection (la page remonte au début)
    if ancien:
        jarvis_ecran.ecrire_presse_papiers(ancien)
    return texte


def texte_principal(texte):
    """Garde les vraies phrases (au moins 8 mots) : les menus, boutons et liens courts sont laissés de côté."""
    lignes = [" ".join(l.split()) for l in texte.splitlines()]
    return "\n".join(l for l in lignes if len(l.split()) >= 8)


_LIRE_PAGE = re.compile(r"^\W*(?:jarvis\W+)?(?:lis|lis-moi|lit|lire|relis)(?:-moi| moi)?\s+(?:cette |la |l'|cet )"
                        r"(?:page|article|site|texte de la page)\W*$")
PAGE_POUR_CLAUDE = re.compile(r"\b(?:résume|resume|résumer|résument|résumé|resumé|explique|traduis|traduire|analyse|que dit|de quoi parle|"
                              r"c'est quoi|qu'est-ce que dit)\b.*\b(?:cette page|la page|cet article|l'article|ce site)\b")


def commande_lire_page(t):
    if not _LIRE_PAGE.match(t.replace("’", "'")):
        return None
    if not navigateur_actif():
        return "Mets d'abord la page à lire au premier plan, dans ton navigateur."
    texte = texte_principal(texte_de_la_page())
    if not texte:
        return "Je ne trouve pas de texte à lire sur cette page."
    texte = " ".join(texte.split())
    if len(texte) > TEXTE_LU_MAX:
        texte = texte[:TEXTE_LU_MAX].rsplit(". ", 1)[0] + ". Le texte continue ; dis : résume cette page, pour la suite en bref."
    return texte


def clic_parmi(textes):
    """« clique sur … » : essaie chaque retranscription (Whisper puis Vosk) ; la première trouvée sur la page l'emporte."""
    echec = None
    for brut in textes:
        if not brut:
            continue
        t = brut.lower().replace("’", "'").strip(" .!?")
        try:
            reponse = commande_clic(t)
        except Exception as erreur:
            print("Clic impossible :", erreur)
            reponse = None
        if reponse and not reponse.startswith("Je ne trouve pas"):
            return reponse
        echec = echec or reponse
    return echec


def rapide(t):
    """Vrai pour un ordre de navigation compris sans la retranscription précise (Whisper)."""
    phrase = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    return any(re.fullmatch(motif, phrase) for motif, _, _ in _NAVIGATION)
