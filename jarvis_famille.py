"""
JARVIS - la vie de famille : devoirs, coucher, résumé de la journée, musique du matin de chaque profil.

  Devoirs (profil enfant ou mode enfant) :
    « on fait les devoirs », « aide-moi à réviser les tables », « on fait une dictée »
    Jarvis pose une question à la fois, au niveau de la classe de l'enfant, donne un indice plutôt que la
    réponse, compte les points. « On arrête les devoirs » pour finir (sinon, ça s'arrête après 20 minutes
    sans question).
    « Léo est en CE1 », « je suis en CE2 » : la classe est retenue et passe toute seule à la classe
    suivante à chaque rentrée de septembre.
  Coucher (seulement sur un profil enfant) :
    « c'est l'heure du dodo » : une courte histoire calme, puis le réacteur se fait très doux et Jarvis répond
    par écrit. Dès qu'on repasse sur un autre profil (par la voix ou « Jarvis, c'est … »), il se réveille
    normalement. « Bonjour Jarvis » ou « réveille-toi » sur le profil enfant le réveille aussi.
  Résumé de la journée : « qu'est-ce qu'on a fait aujourd'hui ? », « fais-moi le résumé de la journée »
  Musique du matin : « ma musique du matin, c'est Kendji Girac » : « Jarvis, bonjour » la lance ensuite.
"""

import json
import re
import threading
import time

import jarvis_config
import jarvis_profils

CLASSES = ["CP", "CE1", "CE2", "CM1", "CM2", "6e", "5e", "4e", "3e", "seconde", "première", "terminale"]
DUREE_DEVOIRS = 20 * 60          # secondes sans question avant que les devoirs s'arrêtent tout seuls
FICHIER_RAPPELS_FAITS = jarvis_config.chemin("rappels_faits.json")

_devoirs = {"profil": None, "dernier": 0.0}
dodo = {"actif": False, "profil": None, "nuit_avant": None}
_verrou = threading.Lock()


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t


# ---------- Réglages propres à chaque profil (rangés dans profils.json ou config.json) ----------

def _reglage(cle):
    ident = jarvis_profils.actif()
    if ident is None:
        return _principal().get(cle)
    return jarvis_profils._lire().get(ident, {}).get(cle)


def _principal():
    try:
        with open(jarvis_profils.FICHIER, encoding="utf-8") as f:
            return (json.load(f).get("principal") or {})
    except (OSError, ValueError, AttributeError):
        return {}


def _regler(ident, **valeurs):
    """Enregistre des réglages pour un profil (None = profil principal), sans toucher au reste du fichier."""
    with _verrou:
        try:
            with open(jarvis_profils.FICHIER, encoding="utf-8") as f:
                donnees = json.load(f)
            if not isinstance(donnees, dict):
                donnees = {}
        except (OSError, ValueError):
            donnees = {}
        if ident is None:
            donnees.setdefault("principal", {}).update(valeurs)
        else:
            donnees.setdefault("profils", {}).setdefault(ident, {}).update(valeurs)
        with open(jarvis_profils.FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)


def enfant_actif():
    ident = jarvis_profils.actif()
    return ident is not None and bool(jarvis_profils._lire().get(ident, {}).get("enfant"))


# ---------- Classe de l'enfant ----------

def _annee_scolaire():
    t = time.localtime()
    return t.tm_year if t.tm_mon >= 9 else t.tm_year - 1


def classe():
    """La classe du profil en cours cette année (elle avance d'une classe à chaque rentrée), ou None."""
    return _classe_de(jarvis_profils.actif())


def _classe_de(ident):
    """La classe de ce profil (None = profil principal) cette année, ou None."""
    reglages = _principal() if not ident else jarvis_profils._lire().get(ident, {})
    nom, annee = reglages.get("classe"), reglages.get("annee_scolaire")
    if not nom or nom not in CLASSES:
        return None
    try:
        rang = CLASSES.index(nom) + (_annee_scolaire() - int(annee or _annee_scolaire()))
    except (TypeError, ValueError):
        rang = CLASSES.index(nom)
    return CLASSES[min(max(rang, 0), len(CLASSES) - 1)]


_CLASSE = re.compile(r"\b(?:est|suis|es|il est|elle est)\s+(?:en|au)\s+(cp|ce1|ce 1|ce2|ce 2|cm1|cm 1|cm2|cm 2|"
                     r"6e|6ème|sixième|5e|5ème|cinquième|4e|4ème|quatrième|3e|3ème|troisième|seconde|première|terminale)\b")


def commande_classe(t):
    m = _CLASSE.search(t)
    if not m or not re.search(r"\b(classe|cp|ce1|ce 1|ce2|ce 2|cm1|cm 1|cm2|cm 2|6e|5e|4e|3e|sixième|cinquième|quatrième|"
                              r"troisième|seconde|première|terminale|ème)\b", t):
        return None
    brut = m.group(1).replace(" ", "")
    nom = {"6ème": "6e", "sixième": "6e", "5ème": "5e", "cinquième": "5e", "4ème": "4e", "quatrième": "4e",
           "3ème": "3e", "troisième": "3e"}.get(brut, brut.upper() if brut[:2] in ("cp", "ce", "cm") else brut)
    # « Léo est en CE1 » : le profil nommé ; « je suis en CE1 » : le profil en cours
    ident = jarvis_profils.actif()
    debut = t[:m.start()].strip()
    if debut and not re.search(r"\b(je|j')\b", debut):
        nomme = jarvis_profils._trouver(debut.split()[-1])
        if nomme is None:
            return None
        ident = nomme or None
    _regler(ident, classe=nom, annee_scolaire=_annee_scolaire())
    qui = jarvis_profils._lire().get(ident, {}).get("prenom") if ident else jarvis_profils.PRINCIPAL["prenom"]
    return f"C'est noté : {qui + ' est' if qui else 'tu es'} en {nom}. Je passerai à la classe suivante à la rentrée."


# ---------- Devoirs ----------

_DEVOIRS = re.compile(r"\b(devoirs?|r[ée]viser|r[ée]vision|on r[ée]vise|tables? de multiplication|la table de|"
                      r"dict[ée]e|exercices? de (?:maths|math|calcul|lecture|fran[çc]ais)|"
                      r"on fait des (?:maths|calculs|additions|soustractions))\b")
_FIN_DEVOIRS = re.compile(r"\b(arr[eê]te|arr[eê]tons|fini|finis|termin[ée]|stop|fin)\b.*\b(devoirs?|r[ée]visions?|exercices?|dict[ée]e)\b"
                          r"|\bj'ai fini\b|\bc'est fini\b")


def _devoirs_possibles():
    try:
        import jarvis_enfant
        return enfant_actif() or jarvis_enfant.actif()
    except Exception:
        return enfant_actif()


def commande_fin_devoirs(t):
    if _devoirs["profil"] is not None or _devoirs["dernier"]:
        if _FIN_DEVOIRS.search(t) and time.time() - _devoirs["dernier"] < DUREE_DEVOIRS:
            _devoirs.update(profil=None, dernier=0.0)
            return "Bravo pour ce travail ! Les devoirs sont finis, tu as bien mérité une pause."
    return None


def note_devoirs(demande):
    """Consignes pour Claude pendant les devoirs (sinon « »)."""
    t = demande.lower()
    actif = _devoirs["dernier"] and time.time() - _devoirs["dernier"] < DUREE_DEVOIRS \
        and _devoirs["profil"] == (jarvis_profils.actif() or "")
    if not actif:
        if not (_DEVOIRS.search(t) and _devoirs_possibles()):
            return ""
        _devoirs["profil"] = jarvis_profils.actif() or ""
    _devoirs["dernier"] = time.time()
    niveau = classe()
    prenom = jarvis_profils.prenom_actif() or "l'enfant"
    if niveau:
        cadre = (f"{prenom} est en {niveau} : choisis les exercices dans le programme officiel français du {niveau} "
                 f"(calcul, nombres, tables, lecture, orthographe), ni trop faciles ni trop durs. ")
    else:
        cadre = (f"Tu ne connais pas encore la classe de {prenom} : commence facile et adapte-toi à ses réponses. ")
    return ("(Mode devoirs : tu aides " + prenom + " à réviser, comme un maître patient et joyeux. " + cadre +
            "Pose une seule question à la fois et termine toujours ta réponse par la question. "
            "Ne donne jamais la réponse tout de suite : s'il se trompe, dis-le gentiment et donne un indice "
            "(par exemple compter sur ses doigts, décomposer le calcul) ; s'il se trompe une deuxième fois, explique "
            "la bonne réponse simplement, puis passe à la suivante. Félicite-le quand c'est juste et compte ses "
            "points. Pour une dictée : dis un mot ou une courte phrase deux fois lentement, demande-lui de l'écrire "
            "sur une feuille, attends qu'il dise qu'il a fini, puis épelle la bonne orthographe lettre par lettre "
            "pour qu'il vérifie. S'il veut arrêter, félicite-le pour son travail.)\n")


# ---------- Coucher (profil enfant seulement) ----------

_DODO = re.compile(r"\b(?:l'heure (?:du|de) (?:dodo|coucher|dormir|aller au lit|se coucher)|au dodo|je vais (?:au dodo|"
                   r"me coucher|dormir)|bonne nuit|on va dormir|histoire pour (?:dormir|s'endormir))\b")


def dodo_demande(demande):
    return enfant_actif() and not dodo["actif"] and bool(_DODO.search(demande.lower().replace("’", "'")))


def note_dodo():
    prenom = jarvis_profils.prenom_actif() or ""
    return ("(Heure du coucher de " + prenom + " : raconte une courte histoire du soir, très calme et douce, "
            "d'environ 300 mots (deux minutes à voix haute), sans aventure qui excite ni rien qui fasse peur, "
            "avec des phrases lentes et apaisantes. " + _deux_voix() + "Termine par « Bonne nuit " + prenom + ", fais de beaux "
            "rêves. » N'écris aucune ligne HISTOIRE: cette fois.)\n")


def _deux_voix():
    try:
        import jarvis_enfant
        return jarvis_enfant.consigne_deux_voix()
    except Exception:
        return ""


def entrer_dodo():
    import jarvis_voix
    if dodo["actif"]:
        return
    dodo.update(actif=True, profil=jarvis_profils.actif(), nuit_avant=jarvis_voix.mode_nuit())
    jarvis_voix.forcer_nuit(True)


def sortir_dodo():
    """Quitte le coucher : Jarvis reprend sa voix et son réacteur habituels."""
    if not dodo["actif"]:
        return False
    import jarvis_voix
    jarvis_voix.forcer_nuit(bool(dodo["nuit_avant"]))
    dodo.update(actif=False, profil=None, nuit_avant=None)
    return True


def commande_reveil(t):
    """Sur le profil enfant endormi : « bonjour Jarvis », « réveille-toi », « c'est le matin »."""
    if dodo["actif"] and re.search(r"\b(r[ée]veille[- ]toi|c'est le matin|bonjour|debout|je suis r[ée]veill[ée])\b", t):
        sortir_dodo()
        prenom = jarvis_profils.prenom_actif()
        return f"Bonjour{(' ' + prenom) if prenom else ''} ! J'espère que tu as bien dormi."
    return None


def profil_change(ident):
    """Appelé à chaque changement de profil : un autre profil réveille Jarvis."""
    if dodo["actif"] and ident != dodo["profil"]:
        sortir_dodo()
    if _devoirs["profil"] is not None and (ident or "") != _devoirs["profil"]:
        _devoirs.update(profil=None, dernier=0.0)


# ---------- Résumé de la journée ----------

_RESUME = re.compile(r"\b(?:r[ée]sum[ée]|r[ée]sume|bilan)\b.*\b(?:journ[ée]e|aujourd'hui)\b|"
                     r"\bqu'est-ce qu(?:'on|e j'ai|e nous avons|'on a) (?:a )?fait aujourd'hui\b|"
                     r"\bqu'(?:est-ce qu')?on a fait aujourd'hui\b|\bcomment s'est pass[ée]e (?:la|ma|notre) journ[ée]e\b")


def resume_demande(demande):
    return bool(_RESUME.search(demande.lower().replace("’", "'")))


def noter_rappel_fait(rappel):
    """Garde la trace des rappels et minuteurs qui ont sonné (pour le résumé de la journée)."""
    try:
        with _verrou:
            try:
                with open(FICHIER_RAPPELS_FAITS, encoding="utf-8") as f:
                    faits = json.load(f)
            except (OSError, ValueError):
                faits = []
            faits.append({"quand": rappel.get("quand"), "message": rappel.get("message"), "pour": rappel.get("pour")})
            with open(FICHIER_RAPPELS_FAITS, "w", encoding="utf-8") as f:
                json.dump(faits[-60:], f, ensure_ascii=False)
    except Exception as erreur:
        print("Rappels faits :", erreur)


def note_resume(rappels_demain):
    """Ce que Claude reçoit pour résumer la journée : échanges du jour (du profil en cours), rappels sonnés
    aujourd'hui et rappels de demain."""
    import jarvis_memoire
    aujourdhui = time.strftime("%Y-%m-%d")
    prenom = jarvis_profils.prenom_actif()
    with jarvis_memoire._verrou:
        echanges = [e for e in jarvis_memoire._charger()["echanges"] if str(e.get("date", "")).startswith(aujourdhui)]
    lignes = [f"- {e['date'][11:]} : {e['demande'][:160]} -> {e['reponse'][:160]}" for e in echanges[-25:]]
    try:
        with open(FICHIER_RAPPELS_FAITS, encoding="utf-8") as f:
            faits = json.load(f)
    except (OSError, ValueError):
        faits = []
    debut = time.mktime(time.strptime(aujourdhui, "%Y-%m-%d"))
    sonnes = [f"- {time.strftime('%H:%M', time.localtime(r['quand']))} : {r['message']}"
              for r in faits if (r.get("quand") or 0) >= debut and (not r.get("pour") or r.get("pour") == prenom)]
    demain = [f"- {time.strftime('%H:%M', time.localtime(r['quand']))} : {r['message']}" for r in rappels_demain
              if not r.get("pour") or r.get("pour") == prenom]
    return ("(Résumé de la journée demandé. Fais un résumé chaleureux et naturel en quatre à six phrases, sans "
            "liste : ce que vous avez fait ensemble aujourd'hui (regroupe, ne cite pas tout), les rappels qui ont "
            "sonné, puis ce qui est prévu demain. S'il n'y a presque rien, dis-le simplement. "
            "Échanges d'aujourd'hui :\n" + ("\n".join(lignes) or "(aucun)") +
            "\nRappels qui ont sonné aujourd'hui :\n" + ("\n".join(sonnes) or "(aucun)") +
            "\nRappels prévus demain :\n" + ("\n".join(demain) or "(aucun)") + ")\n")


# ---------- Musique du matin de chaque profil ----------

_MUSIQUE = re.compile(r"\bma musique (?:pr[ée]f[ée]r[ée]e|du matin|du r[ée]veil)\b,?\s*(?:c'est|est|sera|ce sera)\s+(?P<quoi>.+)$")


def commande_musique_profil(t):
    m = _MUSIQUE.search(t.replace("’", "'"))
    if not m:
        if re.search(r"\b(oublie|enl[eè]ve|supprime|plus de)\b.*\bma musique (?:pr[ée]f[ée]r[ée]e|du matin|du r[ée]veil)\b", t):
            _regler(jarvis_profils.actif(), musique=None)
            return "D'accord, plus de musique le matin."
        return None
    quoi = m.group("quoi").strip(" .!?")
    if not quoi or len(quoi.split()) > 10:
        return None
    _regler(jarvis_profils.actif(), musique=quoi)
    return f"C'est noté : quand tu me diras bonjour, je te mettrai {quoi}."


_VIDE_TITRE = re.compile(r"\s*[\(\[][^\)\]]*\b(?:official|officiel(?:le)?|clip|audio|vid[ée]o|lyrics?|paroles|hd|4k|"
                         r"remaster\w*|visuali[sz]er)\b[^\)\]]*[\)\]]", re.I)
_PETITS_MOTS = {"de", "du", "des", "le", "la", "les", "the", "and", "et", "feat", "ft", "un", "une", "a"}


def _mots(texte):
    import unicodedata
    texte = "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")
    return [m for m in re.split(r"[^a-z0-9]+", texte) if len(m) >= 2 and m not in _PETITS_MOTS]


def _accord(entendu, titre):
    """Part des mots entendus qu'on retrouve (même à peu près) dans le titre de la vidéo."""
    import difflib
    demandes, trouves = _mots(entendu), _mots(titre)
    if not demandes or not trouves:
        return 0.0
    bons = sum(1 for m in demandes if max(difflib.SequenceMatcher(None, m, x).ratio() for x in trouves) >= 0.75)
    return bons / len(demandes)


def musique_parmi(textes):
    """« Ma musique du matin, c'est … » : les titres anglais sont souvent mal retranscrits (« Guette-Lucy de
    Daffte-Pinck »). Chaque retranscription est cherchée sur YouTube, et Jarvis garde le vrai titre de la vidéo qui
    correspond le mieux, plutôt que le texte mal entendu. Sans réseau ou sans résultat sûr : None (commande habituelle)."""
    import jarvis_commandes
    entendus = []
    for brut in textes:
        if not brut:
            continue
        m = _MUSIQUE.search(jarvis_commandes._propre(brut).replace("’", "'"))
        if m:
            quoi = m.group("quoi").strip(" .!?")
            if quoi and len(quoi.split()) <= 10 and quoi not in entendus:
                entendus.append(quoi)
    if not entendus:
        return None
    resultats = {}

    def chercher(quoi):
        try:
            trouve = jarvis_commandes._youtube(quoi)
            if trouve:
                resultats[quoi] = trouve[1]
        except Exception as erreur:
            print("Musique du matin (recherche) :", erreur)
    fils = [threading.Thread(target=chercher, args=(q,), daemon=True) for q in entendus]
    for f in fils:
        f.start()
    for f in fils:
        f.join(10)
    choix = sorted(((_accord(q, titre), titre) for q, titre in resultats.items()), reverse=True)
    if not choix or choix[0][0] < 0.5:
        return None
    titre = " ".join(_VIDE_TITRE.sub("", choix[0][1]).split(" | ")[0].split())
    _regler(jarvis_profils.actif(), musique=titre)
    return (f"C'est noté : quand tu me diras bonjour, je te mettrai {titre}. "
            "Si ce n'est pas le bon morceau, redis-le autrement.")


def musique_du_profil():
    musique = _reglage("musique")
    return str(musique).strip() if musique else None
