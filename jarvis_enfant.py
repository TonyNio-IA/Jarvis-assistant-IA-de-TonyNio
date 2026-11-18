"""
JARVIS - mode enfant.

« Jarvis, active le mode enfant » / « désactive le mode enfant » / « est-ce que le mode enfant est activé ? »

Quand il est actif, tout ce qui passe par Jarvis est adapté à un enfant :
  - les vidéos et la musique s'ouvrent sur YouTube Kids (« mets une vidéo de dinosaures ») ;
  - les recherches Google passent par le filtre SafeSearch ; les sites d'achat ne sont pas ouverts ;
  - Claude répond avec des mots simples, gentiment, sans contenu qui fait peur ou qui n'est pas de son âge,
    et ne fait aucune action sur le PC ;
  - quiz et devinettes : une question à la fois, Jarvis attend la réponse ;
  - longues histoires (environ 10 minutes), avec la suite le lendemain (« raconte la suite »).

Limite : Jarvis ne contrôle que ce qu'on lui demande. Si l'enfant tape lui-même une adresse dans le
navigateur, Jarvis ne peut pas l'en empêcher (c'est le rôle du contrôle parental de Windows).

Le choix (actif ou non) et l'histoire en cours restent sur ce PC, dans enfant.json.
"""

import json
import os
import re
import threading
import time
import urllib.parse

import jarvis_config

FICHIER = jarvis_config.chemin("enfant.json")
_verrou = threading.Lock()

YOUTUBE_KIDS = "https://www.youtubekids.com"
RECHERCHE_YOUTUBE_KIDS = "https://www.youtubekids.com/search?q={}"
RECHERCHE_GOOGLE_PROTEGEE = "https://www.google.com/search?safe=active&q={}"
IMAGES_GOOGLE_PROTEGEES = "https://www.google.com/search?safe=active&tbm=isch&q={}"
SITES_INTERDITS = r"amazon|le ?bon ?coin|leboncoin|cdiscount|vinted|ebay|aliexpress|temu|shein|fnac"


def _lire():
    try:
        with open(FICHIER, encoding="utf-8-sig") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    except OSError as erreur:
        print("Mode enfant non enregistré :", erreur)


def actif():
    with _verrou:
        return bool(_lire().get("actif"))


def _regler(valeur):
    with _verrou:
        donnees = _lire()
        donnees["actif"] = bool(valeur)
        _ecrire(donnees)


def _ouvrir(adresse):
    import jarvis_web
    jarvis_web.ouvrir_devant(adresse)             # le navigateur passe devant la fenêtre active


LANCER_PREMIERE_VIDEO = True     # après une recherche sur YouTube Kids, la première vidéo se lance toute seule
FRANCAIS_SEULEMENT = True        # …et c'est la première vidéo dont le titre est en français
annoncer = None                  # fonction (texte) -> None, donnée par jarvis_claude : Jarvis parle sans qu'on lui demande

_MOTS_FR = frozenset("""le la les des du de un une et en pour avec dans sur au aux qui que est sont ce ces son sa ses mon ma mes
    nos vos chez où il elle ils nous vous je tu pas plus tout tous très bébé bébés chanson chansons dessin animé animés
    épisode épisodes saison saisons français française francais comptine comptines histoire histoires aventure aventures
    conte contes apprendre amis ami petit petite petits petites grand grande drôle drôles nouveau nouvelle meilleur meilleurs
    maison école vacances noël fête ensemble aussi mais comme quand sans sous entre vers""".split())
_MOTS_EN = frozenset("""the and with of to for in is are you your my our we at from by all song songs learn learning nursery
    rhymes rhyme cartoons full funny best new official english spanish español hindi hello morning little ready let's
    lets their his her they when what who how why this that these those""".split())


def est_francais(titre):
    """True si le titre est clairement français, False s'il est clairement dans une autre langue,
    None si on ne peut pas savoir (un simple nom : « Peppa Pig »)."""
    mots = re.findall(r"[^\W\d_]+", titre.lower().replace("’", "'"))
    fr = sum(1 for m in mots if m in _MOTS_FR)
    en = sum(1 for m in mots if m in _MOTS_EN and m not in _MOTS_FR)
    if re.search(r"[éèêàçùâîôûœ]", titre.lower()):
        fr += 2
    if fr > en and fr >= 1:
        return True
    if en >= 1:
        return False
    return None


def _videos_de_la_page():
    """Les vidéos affichées par YouTube Kids, dans l'ordre de la page : [(titre, élément)]."""
    import jarvis_web
    elements = jarvis_web._elements_visibles(hors_ecran=True)
    trouvees = [e for e in elements if e.dans_page and e.genre == 50005 and re.match(r"(?i)vid[ée]o\s", e.nom)]
    trouvees.sort(key=lambda e: (e.haut // 40, e.gauche))
    vus, liste = set(), []
    for e in trouvees:
        titre = re.sub(r"(?i)^vid[ée]o\s+", "", jarvis_web._DUREE.sub("", e.nom)).strip()
        if titre and titre not in vus:
            vus.add(titre)
            liste.append((titre, e))
    return liste


def _lancer_premiere_video(quoi=""):
    """Attend que la page des résultats de YouTube Kids soit affichée, puis lance la première vidéo
    (en français si FRANCAIS_SEULEMENT) : une vidéo choisie par YouTube Kids lui-même, rien d'autre n'est ouvert."""
    import jarvis_fenetres
    import jarvis_web
    debut = time.time()
    premiere_liste = None
    ramenee = 0
    time.sleep(2.5)
    while time.time() - debut < 20:
        try:
            fenetre = jarvis_fenetres.active()
            titre = jarvis_fenetres._texte(fenetre).replace("\xa0", " ").lower() if fenetre else ""
            if not (jarvis_web.navigateur_actif() and "youtube kids" in titre) and ramenee < 2:
                # l'onglet s'est ouvert derrière une autre fenêtre : Jarvis le ramène devant (deux fois au plus)
                for hwnd, nom, _ in jarvis_fenetres.fenetres():
                    if "youtube kids" in (nom or "").replace("\xa0", " ").lower():
                        jarvis_fenetres.premier_plan(hwnd)
                        ramenee += 1
                        time.sleep(1.0)
                        fenetre = jarvis_fenetres.active()
                        titre = jarvis_fenetres._texte(fenetre).replace("\xa0", " ").lower() if fenetre else ""
                        break
            if jarvis_web.navigateur_actif() and "youtube kids" in titre:
                if not FRANCAIS_SEULEMENT:
                    reponse = jarvis_web.commande_clic("clique sur la première vidéo")
                    if reponse and not reponse.startswith("Je ne trouve pas") and not reponse.startswith("Je n'arrive"):
                        print("(YouTube Kids :", reponse, ")")
                        return
                else:
                    videos = _videos_de_la_page()
                    if videos and premiere_liste is None:
                        premiere_liste = time.time()
                    for nom, e in videos:
                        if est_francais(nom):
                            jarvis_web._activer(e)
                            print(f"(YouTube Kids : j'ouvre « {nom[:80]} ».)")
                            return
                    # aucune vidéo française : on attend que la page soit bien remplie avant de renoncer
                    if videos and (len(videos) >= 6 or time.time() - premiere_liste > 6):
                        print("(YouTube Kids : aucune vidéo en français parmi", [n[:40] for n, _ in videos[:8]], ")")
                        if annoncer:
                            annoncer("Je n'ai pas trouvé de vidéo en français" + (f" pour {quoi}" if quoi else "")
                                     + ". Tu veux que je cherche autre chose ?")
                        return
        except Exception as erreur:
            print("YouTube Kids :", erreur)
        time.sleep(1.5)
    print("(YouTube Kids : la première vidéo n'a pas pu être lancée toute seule.)")


# ---------- Activer, désactiver ----------

_MODE = re.compile(r"\bmode (?:enfants?|enfance|en fan|enfin|en face|gamins?|kids?|junior)\b")


def commande(t):
    """Active, désactive ou donne l'état du mode enfant."""
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    if not _MODE.search(t):
        return None
    # une question (« est-ce que le mode enfant est activé ? », écrit parfois « … est active ») ne change jamais rien
    if (re.search(r"\b(?:est-ce que|es-tu|tu es|t'es|c'est)\b", t) and not re.search(
            r"\b(?:active|désactive|desactive|mets|passe|enlève|enleve|coupe|arrête|arrete|quitte|sors)\b", t)
                 and not re.search(r"\b(?:peux|pourrais|veux|voudrais)\b", t)) \
            or (re.search(r"\bmode enfants? (?:est|il est)\s+(?:activ[ée]e?|actif|allumé|en marche|mis)\b", t)
                and not re.search(r"\b(?:peux|pourrais|veux|voudrais|faut)\b", t)):
        return "Le mode enfant est activé." if actif() else "Le mode enfant n'est pas activé."
    if re.search(r"\b(?:désactive|desactive|enlève|enleve|retire|arrête|arrete|coupe|quitte|sors du|stop|fin du)\b", t):
        _regler(False)
        return "Mode enfant désactivé."
    if re.search(r"\b(?:active|mets|passe|lance|démarre|demarre)\b|\ben mode\b", t):
        _regler(True)
        return ("Mode enfant activé. Les vidéos passent par YouTube Kids, les recherches sont filtrées, "
                "et je réponds comme à un enfant. Je peux aussi faire un quiz, des devinettes "
                "ou raconter une longue histoire.")
    return "Tu veux que j'active ou que je désactive le mode enfant ?"


# ---------- Vidéos, musique, recherches : version enfant ----------

def commande_web(t):
    """En mode enfant, remplace YouTube par YouTube Kids, filtre Google et refuse les sites d'achat.
    Renvoie la réponse à dire, ou None si la demande ne concerne pas le web."""
    if not actif():
        return None
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    t = t.replace(",", " ")
    # « mets-moi » est souvent entendu « mes mots », « mes mois », « mais moi » ; « mets » : « mais », « may »
    t = re.sub(r"^(?:mets|mes|mais|mai|may|met|m'est)[- ](?:mots?|mois|moi)\b", "mets-moi", t)
    t = re.sub(r"^(?:mais|mes|mai|may|m'est)\b(?=.*\b(?:vidéos?|video|youtube|dessins? animés?|musiques?|chansons?)\b)", "mets", t)
    t = re.sub(r"\byoutube (?:quittes?|kit|kits|kid|quid|qui)\b", "youtube kids", t)
    t = " ".join(t.split())
    if re.search(r"\b(?:" + SITES_INTERDITS + r")\b", t):
        return "En mode enfant, je n'ouvre pas les sites d'achat."
    # « retourne à l'accueil » (souvent entendu « à la cueille ») : la page d'accueil de YouTube Kids
    if re.search(r"\b(?:retourne|reviens|revenir|retourner|va|remets)\b.{0,12}\b(?:accueil|cueille|l'accueil|début)\b", t):
        _ouvrir(YOUTUBE_KIDS)
        return "Je retourne à l'accueil de YouTube Kids."
    # « ouvre YouTube »
    if re.fullmatch(r"(?:ouvre|lance|va sur|mets)(?:-moi)? (?:le site )?youtube(?: kids)?", t):
        _ouvrir(YOUTUBE_KIDS)
        return "J'ouvre YouTube Kids."
    # « cherche des dinosaures sur Google », « cherche des images de chats »
    m = re.match(r"(?:cherche|recherche|trouve|regarde)(?:-moi)? (?P<quoi>.+?) (?:sur|dans|avec) "
                 r"(?:google images|les images|images)$", t)
    if m:
        _ouvrir(IMAGES_GOOGLE_PROTEGEES.format(urllib.parse.quote(_nettoyer(m.group("quoi")))))
        return f"Je cherche des images de {_nettoyer(m.group('quoi'))}, avec le filtre pour les enfants."
    m = re.match(r"(?:cherche|recherche|trouve|regarde)(?:-moi)? (?P<quoi>.+?) (?:sur|dans|avec) "
                 r"(?:google|internet|le web|le net)$", t)
    if m:
        _ouvrir(RECHERCHE_GOOGLE_PROTEGEE.format(urllib.parse.quote(_nettoyer(m.group("quoi")))))
        return f"Je cherche {_nettoyer(m.group('quoi'))} sur Google, avec le filtre pour les enfants."
    # « lance la deuxième vidéo » : un clic dans la page ouverte, pas une nouvelle recherche
    if re.search(r"\b(?:premi[eè]re?|1[eè]?re?|deuxi[eè]me|second[e]?|troisi[eè]me|quatri[eè]me|cinqui[eè]me|"
                 r"\d+e|\d+ème|dernière|derniere) (?:vidéo|video)\b", t):
        return None
    # Vidéos et musique : « mets une vidéo de dinosaures », « cherche Peppa Pig sur YouTube »,
    # « mets la musique de la Reine des neiges »
    video = re.search(r"\b(?:vidéos?|video|youtube|dessins? animés?|musiques?|chansons?|clips?|épisodes?)\b", t)
    verbes = (r"(?:mets|met|mais|mes|joue|lance|passe|cherche|recherche|trouve|montre|ouvre|ouvrez|regarde|"
              r"je veux(?: voir| regarder)?|j'aimerais(?: voir| regarder)?|je voudrais(?: voir| regarder)?|"
              r"tu peux(?: me)? (?:mettre|trouver|montrer|ouvrir))(?:-moi| moi)?\b")
    action = re.match(verbes, t) or re.match(r"(?:une|des|la|les|un) (?:vidéos?|video|dessins? animés?|chansons?|"
                                              r"musiques?|épisodes?)\b", t)   # « une vidéo de dinosaures » (suite)
    if video and action:
        quoi = re.sub("^" + verbes, "", t)
        quoi = re.sub(r"\b(?:(?:est |qui est )?sur youtube(?: kids)?|youtube(?: kids)?|s'il te plaît|stp)\b", " ", quoi)
        quoi = re.sub(r"^\s*(?:moi\s+)?(?:une |des |la |les |le |un |en )?(?:vidéos?|video|musiques?|chansons?|clips?|"
                      r"épisodes?)?\s*(?:de la |de l'|des |du |de |d'|sur les |sur le |sur la |sur )?", "", quoi)
        quoi = _nettoyer(re.sub(r"\s+(?:est|qui est)\s*$", "", quoi.strip(" .,!?")))
        if not quoi:
            _ouvrir(YOUTUBE_KIDS)
            return "J'ouvre YouTube Kids."
        recherche = quoi + " en français" if FRANCAIS_SEULEMENT and not re.search(r"fran[cç]ais|vf\b", quoi) else quoi
        _ouvrir(RECHERCHE_YOUTUBE_KIDS.format(urllib.parse.quote(recherche)))
        if LANCER_PREMIERE_VIDEO:
            threading.Thread(target=_lancer_premiere_video, args=(quoi,), daemon=True).start()
            return f"Je lance une vidéo de {quoi} sur YouTube Kids."
        return f"Je cherche {quoi} sur YouTube Kids."
    return None


def _nettoyer(quoi):
    quoi = " ".join(quoi.split())
    quoi = re.sub(r"^(?:sur |de |à propos de |avec )?(?:des |de la |du |de l'|les |le |la |l'|un |une )?", "", quoi)
    return " ".join(quoi.split()).strip(" .,!?")


# ---------- Ce que Claude reçoit en mode enfant ----------

DEUX_VOIX = True               # histoires à deux voix (Henri et Denise)
LONGUEUR_HISTOIRE = 1500        # mots, environ 10 minutes de lecture à voix haute
_HISTOIRE = re.compile(r"\b(?:histoire|conte|la suite|raconte)\b")
_BALISE = re.compile(r"^\s*HISTOIRE\s*:\s*(.+)$", re.M)


def note(demande):
    """Consignes ajoutées devant la demande quand le mode enfant est actif (sinon « »)."""
    if not actif():
        return ""
    texte = ("(Mode enfant : tu parles à un enfant. Réponds avec des mots simples, gentiment et avec "
             "enthousiasme, sans rien qui fasse peur, de violent ou qui ne soit pas de son âge. "
             "Ne fais aucune action sur le PC et n'ouvre aucun site ; pour une vidéo, dis-lui de "
             "demander « mets une vidéo de… ». Pour un quiz ou des devinettes : pose une seule question "
             "à la fois, termine par la question, puis attends sa réponse ; dis-lui gentiment si c'est "
             "juste ou non, donne la bonne réponse, compte les points et pose la suivante, jusqu'à ce "
             "qu'il veuille arrêter. ")
    if _HISTOIRE.search(demande.lower()):
        texte += (f"Pour une histoire, oublie la limite de trois phrases : raconte une longue histoire "
                  f"d'au moins {LONGUEUR_HISTOIRE} mots (dix minutes à voix haute, jamais moins : prends le temps "
                  f"des descriptions, des dialogues et de plusieurs péripéties), avec un titre dit au "
                  f"début, des personnages attachants, et une fin de chapitre qui donne envie de connaître "
                  f"la suite. Écris seulement le texte à lire, sans titre de section ni mise en forme. "
                  f"{consigne_deux_voix()}"
                  f"Termine toujours par une ligne « HISTOIRE: » suivie d'un résumé de toute l'histoire "
                  f"jusqu'ici (personnages, lieux, ce qui s'est passé) en quatre phrases au plus : "
                  f"cette ligne n'est pas lue, elle sert à raconter la suite plus tard. ")
        with _verrou:
            histoire = _lire().get("histoire")
        if histoire and re.search(r"\bsuite\b|\bcontinue\b|\bdernier chapitre\b|\bchapitre suivant\b",
                                  demande.lower()):
            texte += ("Il demande la suite de l'histoire déjà commencée, dont voici le résumé : "
                      + histoire + " Raconte le chapitre suivant, avec les mêmes personnages. ")
    return texte + ")\n"


def consigne_deux_voix():
    """Histoires à deux voix : les répliques des personnages de l'autre voix sont écrites entre ⟨ et ⟩."""
    import jarvis_voix
    if not DEUX_VOIX:
        return ""
    qui = ("féminins (une fille, une maman, une reine, une renarde...)" if jarvis_voix.VOIX == jarvis_voix.VOIXS["henri"]
           else "masculins (un garçon, un papa, un roi, un renard...)")
    return ("Deux voix lisent l'histoire : écris les paroles des personnages " + qui + " entre ⟨ et ⟩, seulement "
            "leurs paroles, par exemple : ⟨Viens vite !⟩ cria la petite renarde. Le reste du texte, et les paroles "
            "des autres personnages, s'écrivent normalement. ")


def appliquer(reponse):
    """Retire la ligne « HISTOIRE: … » de la réponse de Claude et garde le résumé pour la suite."""
    resumes = _BALISE.findall(reponse or "")
    if not resumes:
        return reponse
    with _verrou:
        donnees = _lire()
        donnees["histoire"] = resumes[-1].strip()[:1500]
        donnees["histoire_le"] = time.strftime("%d/%m/%Y %H:%M")
        _ecrire(donnees)
    return _BALISE.sub("", reponse).strip()


def histoire_demandee(demande):
    return actif() and bool(_HISTOIRE.search(demande.lower()))
