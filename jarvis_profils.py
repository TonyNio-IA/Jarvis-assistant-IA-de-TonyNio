"""
JARVIS - un profil par personne du foyer.

Chaque personne a sa propre mémoire (ce que Jarvis a retenu, ses derniers échanges) et ses propres notes.
Le profil principal est celui de la personne qui a installé Jarvis : ses fichiers ne changent pas de place.
Les autres profils sont rangés dans le dossier profils/ (gardé sur ce PC, jamais publié).
Restent communs à tout le foyer : les rappels et minuteurs, la liste de courses, la ville.
Les mails ne se lisent que sur le profil principal (ce sont les siens).

  « Jarvis, crée un profil pour Marie »            (ou « crée un profil enfant pour Léo » : mode enfant d'office)
  « Jarvis, c'est Marie », « je suis Marie », « passe sur le profil de Marie »
  « Jarvis, qui suis-je ? », « quels sont les profils ? »
  « Jarvis, supprime le profil de Marie »          (après confirmation ; ses fichiers sont mis de côté, pas effacés)

Au démarrage, Jarvis est sur le profil principal.
"""

import difflib
import json
import os
import re
import shutil
import time

import jarvis_config

FICHIER = jarvis_config.chemin("profils.json")
DOSSIER = jarvis_config.chemin("profils")
PRINCIPAL = {"prenom": jarvis_config.PRENOM, "nom": jarvis_config.NOM, "salut": jarvis_config.SALUT}

_choix_manuel = 0.0       # moment où quelqu'un a dit lui-même qui il est (« Jarvis, c'est Marie »)
DUREE_CHOIX_MANUEL = 15 * 60
_actif = None                    # identifiant du profil en cours (None = profil principal)
_enfant_avant = None             # état du mode enfant avant d'entrer dans un profil enfant
_origine = {}                    # chemins des fichiers du profil principal


def _simple(texte):
    texte = texte.lower().strip()
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            texte = texte.replace(lettre, b)
    return re.sub(r"[^a-z0-9]+", "-", texte).strip("-")


def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        profils = donnees.get("profils") if isinstance(donnees, dict) else None
        return profils if isinstance(profils, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(profils):
    try:                                          # les autres réglages du fichier sont gardés
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        if not isinstance(donnees, dict):
            donnees = {}
    except (OSError, ValueError):
        donnees = {}
    donnees["profils"] = profils
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=1)


def actif():
    """Identifiant du profil en cours, ou None pour le profil principal."""
    return _actif


def prenom_actif():
    if _actif is None:
        return PRINCIPAL["prenom"]
    return _lire().get(_actif, {}).get("prenom", "")


def consigne():
    """Ajoutée aux consignes de Claude quand ce n'est pas le profil principal."""
    if _actif is None:
        return ""
    prenom = prenom_actif()
    return (f" En ce moment, ce n'est pas {PRINCIPAL['nom']} qui te parle mais {prenom}, une autre personne "
            f"de son foyer : adresse-toi à {prenom}, et la mémoire ci-dessous est la sienne.")


def _son(texte):
    """Écriture approchée de la prononciation : « Mat et eau », « ma théo » et « Mathéo » se ressemblent."""
    t = _simple(texte).replace("-", "")
    for a, b in (("eau", "o"), ("au", "o"), ("ou", "u"), ("ph", "f"), ("qu", "k"), ("ch", "x"), ("ck", "k"),
                 ("y", "i"), ("h", ""), ("z", "s"), ("un", "an"), ("en", "an"), ("om", "on"), ("am", "an")):
        t = t.replace(a, b)
    t = re.sub(r"c(?=[ei])", "s", t).replace("c", "k")
    t = re.sub(r"(?<=\w\w)(?:es|e|s|t|x|d)$", "", t)     # finales muettes : « pôles » sonne comme « Paul »
    return re.sub(r"(.)\1+", r"\1", t)


def _trouver(nom):
    """Identifiant du profil dont le prénom ressemble à ce nom ("" = profil principal, None = aucun).
    Tolère les prénoms mal entendus (« Mat et eau », « ma théo » pour « Mathéo »)."""
    nom = re.sub(r"(?i)^([ld])'(?=\w)", r"\1", nom.strip())   # « c'est l'éo » : « Léo »
    cherche = _simple(nom)
    if not cherche:
        return None
    candidats = {ident: _simple(p.get("prenom", "")) for ident, p in _lire().items()}
    if PRINCIPAL["prenom"]:
        candidats[""] = _simple(PRINCIPAL["prenom"])
    if cherche in candidats.values():
        return next(i for i, n in candidats.items() if n == cherche)
    meilleur, note = None, 0.0
    son = _son(nom)
    for ident, n in candidats.items():
        r = max(difflib.SequenceMatcher(None, cherche, n).ratio(),
                difflib.SequenceMatcher(None, son, _son(n)).ratio())
        if r > note:
            meilleur, note = ident, r
    return meilleur if note >= 0.78 else None


def activer(ident):
    """Passe sur un profil (None ou "" = profil principal). Renvoie le prénom."""
    global _actif, _enfant_avant
    import jarvis_commandes
    import jarvis_enfant
    import jarvis_extras
    import jarvis_memoire
    ident = ident or None
    profils = _lire()
    if ident is not None and ident not in profils:
        raise KeyError(ident)
    if not _origine:
        _origine.update(memoire=jarvis_memoire.FICHIER, notes=jarvis_commandes.FICHIER_NOTES)
    if ident is None:
        memoire, notes = _origine["memoire"], _origine["notes"]
        prenom = PRINCIPAL["prenom"]
        jarvis_config.PRENOM, jarvis_config.NOM, jarvis_config.SALUT = (PRINCIPAL["prenom"], PRINCIPAL["nom"],
                                                                       PRINCIPAL["salut"])
    else:
        dossier = os.path.join(DOSSIER, ident)
        os.makedirs(dossier, exist_ok=True)
        memoire, notes = os.path.join(dossier, "memoire.json"), os.path.join(dossier, "notes.txt")
        prenom = profils[ident].get("prenom", "")
        jarvis_config.PRENOM, jarvis_config.NOM, jarvis_config.SALUT = prenom, prenom, " " + prenom
    with jarvis_memoire._verrou:                    # la mémoire suit le profil
        jarvis_memoire.FICHIER = memoire
        jarvis_memoire._donnees = None
        jarvis_memoire._non_transmis.clear()
    jarvis_commandes.FICHIER_NOTES = notes
    # Profil enfant : le mode enfant s'active tout seul, et revient à son état d'avant en quittant le profil
    enfant = ident is not None and bool(profils[ident].get("enfant"))
    if enfant and _enfant_avant is None:
        _enfant_avant = jarvis_enfant.actif()
        jarvis_enfant._regler(True)
    elif not enfant and _enfant_avant is not None:
        jarvis_enfant._regler(_enfant_avant)
        _enfant_avant = None
    changement = ident != _actif
    _actif = ident
    try:                                             # coucher, devoirs : propres au profil qu'on quitte
        import jarvis_famille
        jarvis_famille.profil_change(ident)
    except Exception as erreur:
        print("Profil :", erreur)
    if changement:
        jarvis_extras.redemarrer_claude = True      # nouvelle conversation, avec la mémoire de cette personne
    return prenom


def _creer(prenom, enfant):
    profils = _lire()
    ident = _simple(prenom)
    if not ident:
        return None
    if ident not in profils:
        profils[ident] = {"prenom": prenom, "enfant": bool(enfant), "cree": time.strftime("%Y-%m-%d")}
        _ecrire(profils)
        os.makedirs(os.path.join(DOSSIER, ident), exist_ok=True)
    return ident


def _supprimer(ident):
    profils = _lire()
    prenom = profils.get(ident, {}).get("prenom", "")
    if _actif == ident:
        activer(None)
    profils.pop(ident, None)
    _ecrire(profils)
    dossier = os.path.join(DOSSIER, ident)
    if os.path.isdir(dossier):                      # les fichiers sont mis de côté, jamais effacés
        cote = os.path.join(DOSSIER, "_supprimes")
        os.makedirs(cote, exist_ok=True)
        shutil.move(dossier, os.path.join(cote, ident + "-" + time.strftime("%Y%m%d-%H%M%S")))
    return f"Le profil de {prenom} est supprimé."


def _prenom_propre(nom):
    nom = re.sub(r"\b(s'il te pla[iî]t|stp|merci|jarvis)\b", "", nom).strip(" .!?,;:«»\"'")
    nom = re.sub(r"(?i)^([ld])'(?=\w)", r"\1", nom)     # « l'éo » : c'est « Léo » mal découpé
    return " ".join(m.capitalize() for m in nom.split())


_CREER = re.compile(r"\b(?:cr[ée]e|cr[ée]er|cr[ée]es|ajoute|ajouter|fais|nouveau)\b.*?\bprofil\b(?P<enfant> enfant)?"
                    r"\s+(?:pour |de |d'|au nom de |nomm[ée] |qui s'appelle |appel[ée] )+(?P<nom>[\w\-' ]+)")
_CHANGER = re.compile(r"\b(?:passe|passer|repasse|repasser|repas|reviens|retourne|mets|va|bascule|change|prends|utilise|"
                      r"active)\b.*?\bprofil\b"
                      r"(?:\s+(?:de |d'|pour |à |a ))?\s*(?P<nom>[\w\- ]*)")
_CEST = re.compile(r"^\W*(?:jarvis\W+)?(?:(?:bonjour|salut|coucou|bonsoir)\W+(?:jarvis\W+)?)?"
                   r"(?:c'est moi|moi c'est|c'est|c'é|cet|ces|ses|je suis|ici)\s*(?P<nom>[\w\-']+(?: [\w\-]+){0,2})\W*$")
_SUPPRIMER = re.compile(r"\b(?:su+p+rime[rs]?|efface|effacer|enl[eè]ve|retire)\b.*?\bprofil\b"
                        r"\s+(?:de |d'|pour )?(?P<nom>[\w\- ]+)")


def _noms():
    noms = [p.get("prenom", "") for p in _lire().values()]
    return ([PRINCIPAL["prenom"]] if PRINCIPAL["prenom"] else []) + noms


def commande(t, demander_confirmation):
    """Renvoie la phrase à dire, ou None si la demande ne concerne pas les profils."""
    t = t.replace("’", "'").lower()
    parle_de_profil = re.search(r"\bprofils?\b", t)
    if parle_de_profil:
        m = _SUPPRIMER.search(t)
        if m:
            ident = _trouver(m.group("nom"))
            if ident == "":
                return "Le profil principal ne peut pas être supprimé."
            if ident is None:
                return f"Je ne connais pas de profil au nom de {_prenom_propre(m.group('nom'))}."
            prenom = _lire()[ident].get("prenom", "")
            demander_confirmation(lambda: _supprimer(ident))
            return f"Tu veux vraiment supprimer le profil de {prenom} ? Dis oui pour confirmer."
        m = _CREER.search(t)
        if m:
            prenom = _prenom_propre(m.group("nom"))
            if not prenom or len(prenom.split()) > 3 or len(prenom.replace(" ", "")) < 2:
                return "Dis-moi le prénom : par exemple, crée un profil pour Marie."
            deja = _trouver(prenom)
            if deja is not None:
                return f"Il y a déjà un profil pour {prenom}. Pour l'utiliser, dis : Jarvis, c'est {prenom}."
            ident = _creer(prenom, bool(m.group("enfant")) or bool(re.search(r"\benfants?\b", t)))
            if ident is None:
                return "Je n'ai pas compris le prénom. Dis par exemple : crée un profil pour Marie."
            enfant = " enfant" if _lire()[ident].get("enfant") else ""
            return (f"Le profil{enfant} de {prenom} est créé, avec sa propre mémoire. "
                    f"Pour l'utiliser, dis : Jarvis, c'est {prenom}.")
        if re.search(r"\b(quels?|liste|combien|montre|dis-moi)\b.*\bprofils\b|\bprofils\b.*\b(existent|disponibles)\b", t):
            noms = _noms()
            if len(noms) <= 1:
                return "Il n'y a que le profil principal. Pour en ajouter un, dis : crée un profil pour Marie."
            return "Les profils sont : " + ", ".join(noms[:-1]) + " et " + noms[-1] + "."
        if re.search(r"\b(quel|sur quel|c'est quel)\b.*\bprofil\b", t):
            return _qui()
        m = _CHANGER.search(t)
        if m:
            nom = m.group("nom").strip()
            if re.search(r"\bprincipal\b", t):
                return _passer("")
            if not nom:
                noms = _noms()
                return ("Sur quel profil ? " + ", ".join(noms) + "." if len(noms) > 1
                        else "Il n'y a que le profil principal pour l'instant.")
            ident = _trouver(nom)
            if ident is None:
                return f"Je ne connais pas de profil au nom de {_prenom_propre(nom)}."
            return _passer(ident)
        return None
    if re.search(r"^\W*(?:jarvis\W+)?(?:qui suis[- ]je|tu sais qui je suis|à qui (?:tu parles|parles[- ]tu)|"
                 r"tu parles à qui|c'est qui qui te parle)\W*$", t):
        return _qui()
    m = _CEST.match(t)
    if m:                                            # « c'est Marie » : seulement pour un prénom connu
        ident = _trouver(m.group("nom"))
        if ident is not None:
            return _passer(ident, voix_confirmee=True)
    return None


def _qui():
    prenom = prenom_actif()
    if not prenom:
        return "Je suis sur le profil principal."
    return f"Je parle avec {prenom}." if _actif is not None else f"Je parle avec {prenom}, sur le profil principal."


def choix_recent():
    """Vrai pendant 15 minutes après « Jarvis, c'est … » : la voix ne fait alors pas changer de profil."""
    return time.time() - _choix_manuel < DUREE_CHOIX_MANUEL


def _passer(ident, voix_confirmee=False):
    """voix_confirmee : seulement pour « c'est Marie » (la personne dit qui ELLE est). « Passe sur le profil
    de Marie » peut être dit par quelqu'un d'autre : sa voix ne doit jamais aller dans l'empreinte de Marie."""
    global _choix_manuel
    _choix_manuel = time.time()
    if (ident or None) == _actif:
        prenom = prenom_actif()
        return f"Je suis déjà sur le profil de {prenom}." if prenom else "Je suis déjà sur le profil principal."
    prenom = activer(ident)
    try:                                             # sa voix vient d'être entendue : l'empreinte s'affine
        import jarvis_locuteur
        if voix_confirmee:
            jarvis_locuteur.confirmer(ident)
        else:
            jarvis_locuteur.oublier_confirmable()
    except Exception as erreur:
        print("Empreinte de voix :", erreur)
    enfant = ident and _lire().get(ident, {}).get("enfant")
    return f"Bonjour {prenom} ! Je passe sur ton profil" + (", en mode enfant." if enfant else ".")


def refus(t):
    """Les mails sont ceux du profil principal."""
    if _actif is not None and re.search(r"\b(mails?|e-mails?|courriels?)\b", t):
        qui = PRINCIPAL["prenom"] or "la personne du profil principal"
        return f"Les mails sont ceux de {qui} : je ne les lis que sur son profil."
    return None
