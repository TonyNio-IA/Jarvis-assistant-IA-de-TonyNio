# -*- coding: utf-8 -*-
"""
JARVIS - autres assistants IA (BÊTA) : un repli quand Claude n'est pas là ou a atteint sa limite.

Claude Code reste l'assistant principal. Ce module ne sert que si Claude est absent, déconnecté ou à court de quota :
la demande passe alors au premier assistant connecté de la liste, puis au suivant s'il atteint à son tour sa limite.

Principes :
- un seul connecteur « compatible OpenAI » (adresse + clé + modèle) couvre Gemini, Grok, DeepSeek, Mistral, Qwen,
  Amazon Nova, Muse Spark, OpenRouter, Mammouth, Ollama (sur le PC), OpenAI... ;
- ce sont des réponses TEXTE : aucune action sur le PC (les actions restent à Claude Code) ;
- la clé API est chiffrée par Windows (DPAPI, liée à la session Windows de l'utilisateur) et gardée dans
  assistants.json, un fichier propre à ce PC qui n'est jamais envoyé sur GitHub ni dans les rapports ;
- rien ne part chez un tiers tant que l'utilisateur n'a pas accepté (« consentement ») ;
- aucun mot de passe : on utilise des clés API, créées par l'utilisateur sur le site du fournisseur ;
- toute erreur est rattrapée : ce module ne doit jamais faire planter Jarvis.
"""

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import jarvis_config

FICHIER = jarvis_config.chemin("assistants.json")
DELAI_REPONSE_S = 60
PAUSE_QUOTA_S = 3600          # un compte à court de quota est mis de côté une heure
PAUSE_PANNE_S = 300           # un fournisseur qui ne répond pas : 5 minutes
MAX_REPONSE = 4000            # caractères gardés d'une réponse (Jarvis la lit à voix haute)
_verrou = threading.RLock()

# Fournisseurs connus. « adresse » : la base de l'API (les adresses sont celles des documentations officielles).
# « modele » : modèle conseillé si on le connaît ; sinon le modèle est choisi dans la liste que le fournisseur donne.
# « cle_url » : page où l'utilisateur crée sa clé. « gratuit » : ce qu'on sait du gratuit (jamais une promesse).
FOURNISSEURS = [
    {"id": "gemini", "nom": "Google Gemini",
     "adresse": "https://generativelanguage.googleapis.com/v1beta/openai",
     "modele": "", "cle_url": "https://aistudio.google.com/apikey",
     "gratuit": "Un niveau gratuit existe avec une clé Google AI Studio (limité).",
     "aide": "Connecte-toi avec ton compte Google, clique sur « Create API key », copie la clé."},
    {"id": "mistral", "nom": "Mistral (français)",
     "adresse": "https://api.mistral.ai/v1", "modele": "", "cle_url": "https://console.mistral.ai/api-keys",
     "gratuit": "Un forfait gratuit « Experiment » existe (vérification par téléphone demandée).",
     "aide": "Crée un compte sur console.mistral.ai, choisis le forfait Experiment, puis « API keys » > créer."},
    {"id": "deepseek", "nom": "DeepSeek", "adresse": "https://api.deepseek.com", "modele": "deepseek-flash",
     "cle_url": "https://platform.deepseek.com/api_keys",
     "gratuit": "Payant à l'usage (de petites sommes). Pas de gratuit garanti.",
     "aide": "Crée un compte, ajoute un petit crédit, puis « API keys » > créer une clé."},
    {"id": "kimi", "nom": "Kimi (Moonshot AI)", "adresse": "https://api.moonshot.ai/v1", "modele": "",
     "cle_url": "https://platform.moonshot.ai/console/api-keys",
     "gratuit": "Payant à l'usage : il faut recharger au moins 1 $ avant que l'API réponde. Le chat gratuit de kimi.com ne marche pas ici.",
     "aide": "Crée un compte sur platform.moonshot.ai, recharge au moins 1 $, puis « API Keys » > créer une clé. Une clé de platform.moonshot.cn (Chine) demande l'adresse https://api.moonshot.cn/v1 dans « Adresse avancée »."},
    {"id": "grok", "nom": "Grok (xAI)", "adresse": "https://api.x.ai/v1", "modele": "",
     "cle_url": "https://console.x.ai",
     "gratuit": "Payant à l'usage. Pas de gratuit garanti.",
     "aide": "Crée un compte sur console.x.ai, puis crée une clé API (elle commence par xai-)."},
    {"id": "qwen", "nom": "Qwen (Alibaba)", "adresse": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
     "modele": "", "cle_url": "https://modelstudio.console.alibabacloud.com",
     "gratuit": "Selon l'offre en cours chez Alibaba.",
     "aide": "Crée un compte Alibaba Cloud, active Model Studio, crée une clé. Selon ta région, l'adresse peut "
             "changer : modifie-la dans « Adresse avancée » si le test échoue."},
    {"id": "nova", "nom": "Amazon Nova", "adresse": "https://api.nova.amazon.com/v1", "modele": "",
     "cle_url": "https://nova.amazon.com/dev",
     "gratuit": "L'API Nova a un niveau gratuit avec limites de débit.",
     "aide": "Va sur nova.amazon.com/dev, connecte-toi avec ton compte Amazon et génère une clé API."},
    {"id": "muse", "nom": "Muse Spark (Meta)", "adresse": "https://api.meta.ai/v1", "modele": "muse-spark-1.1",
     "cle_url": "https://dev.meta.ai/api-keys/",
     "gratuit": "Service payant (aperçu pour développeurs) : des crédits de départ peuvent être offerts, et l'accès peut être limité selon le pays.",
     "aide": "Connecte-toi sur dev.meta.ai avec ton compte Meta, puis crée une clé dans « API keys ». Si le test échoue, l'accès n'est peut-être pas ouvert dans ton pays, ou ton compte n'a pas de crédit."},
    {"id": "openrouter", "nom": "OpenRouter (des centaines de modèles)", "adresse": "https://openrouter.ai/api/v1",
     "modele": "", "cle_url": "https://openrouter.ai/keys",
     "gratuit": "Une partie des modèles est gratuite (nom terminé par « :free »), avec des limites.",
     "aide": "Crée un compte sur openrouter.ai, puis « Keys » > créer une clé."},
    {"id": "mammouth", "nom": "Mammouth AI (français)", "adresse": "https://api.mammouth.ai/v1", "modele": "",
     "cle_url": "https://mammouth.ai/app/account/settings/api",
     "gratuit": "Il faut un abonnement Mammouth ; des crédits d'API y sont inclus.",
     "aide": "Connecte-toi à Mammouth, ouvre Compte > Réglages > API et génère une clé."},
    {"id": "openai", "nom": "ChatGPT (OpenAI)", "adresse": "https://api.openai.com/v1", "modele": "",
     "cle_url": "https://platform.openai.com/api-keys",
     "gratuit": "Payant à l'usage, séparé de l'abonnement ChatGPT.",
     "aide": "Crée un compte sur platform.openai.com, ajoute un crédit, puis « API keys » > créer une clé."},
    {"id": "ollama", "nom": "Ollama (sur ton PC, gratuit)", "adresse": "http://localhost:11434/v1", "modele": "",
     "cle_url": "https://ollama.com/download", "sans_cle": True,
     "gratuit": "Gratuit et sans limite : l'IA tourne sur ton PC, rien ne sort. Demande un PC assez puissant.",
     "aide": "Installe Ollama, télécharge un modèle (« ollama pull » suivi du nom), laisse Ollama ouvert."},
    {"id": "autre", "nom": "Autre (compatible OpenAI)", "adresse": "", "modele": "", "cle_url": "",
     "gratuit": "Selon le service.",
     "aide": "Pour un service qui accepte le format OpenAI : indique son adresse, sa clé et son modèle."},
]
PAR_ID = {f["id"]: f for f in FOURNISSEURS}

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
         "décembre"]


def consigne(longue=False):
    """Ce qu'on dit à l'assistant avant la question : qui il est, à qui il parle, quel jour on est, ce qu'il ne peut pas."""
    tm = time.localtime()
    nom = (getattr(jarvis_config, "NOM", "") or "").strip()
    texte = ("Tu es Jarvis, un assistant vocal en français" + (f", et tu parles à {nom}" if nom else "") + ". "
             f"Nous sommes {_JOURS[tm.tm_wday]} {tm.tm_mday} {_MOIS[tm.tm_mon - 1]} {tm.tm_year}, "
             f"il est {tm.tm_hour} h {tm.tm_min:02d}. ")
    if longue:
        texte += ("Écris un texte continu, sans titres, sans listes, sans mise en forme et sans émojis, agréable à "
                  "écouter à voix haute. ")
    else:
        texte += ("Réponds en 1 à 4 phrases courtes, simples, faciles à écouter : pas de listes, pas de tableaux, "
                  "pas de mise en forme, pas d'émojis. ")
    texte += ("Réponds directement, sans dire bonjour, sans répéter la question, et n'emploie le prénom que très rarement. ")
    texte += ("Tu n'as pas accès à Internet ni à l'ordinateur : si on te demande une information très récente "
              "(actualités, météo, scores) ou une action sur l'ordinateur (modifier ou chercher un fichier, par exemple), "
              "dis simplement et gentiment que cette demande-là n'est pas possible pour le moment. Ne dis jamais que tu "
              "ne sais pas ouvrir ou lancer des applications : Jarvis le fait lui-même.")
    return texte


# ------------------------------------------------------------------ stockage

_OUVRIR = re.compile(r"^\W*(?:jarvis\W+)?(?:s'il te pla[iî]t\W+)?(?:est-ce que tu peux |tu peux |peux[- ]tu |"
                     r"pourrais[- ]tu |tu pourrais )?(?:m'|me )?"
                     r"(?:(?P<verbe>ouvre|ouvrir|ouvres|ouvrez|lance|lancer|lances|lancez|démarre|démarrer|demarre|demarrer)"
                     r"(?:[- ]moi)?\b\s*(?P<reste>.*)"
                     r"|(?:lors|lorse|lorses|lorce|lorces|los|l'os|lanse|lanses)?\s*"
                     r"(?P<seul>(?:l'application|l'appli|le logiciel|le programme)\s+[\w'.-]+(?:\s+[\w'.-]+){0,2}))\W*$", re.I)


def reponse_action(demande, claude_present=True):
    """Demande d'ouvrir une application que Jarvis n'a pas pu satisfaire lui-même : renvoie la phrase à dire, au lieu
    d'interroger l'assistant de secours (qui n'a pas accès au PC et répondrait « je ne peux pas lancer d'application »).
    Renvoie None pour toute autre demande. Ne lève jamais d'erreur."""
    try:
        m = _OUVRIR.match(str(demande or "").strip())
        if not m:
            return None
        reste = (m.group("reste") if m.group("verbe") else m.group("seul")) or ""
        reste = reste.strip(" .!?,;:…")
        if not reste or "?" in str(demande) or len(reste.split()) > 12:
            return None
        if not m.group("verbe") and re.search(
                r"\b(est|sont|a|ont|ne|n'|qui|que|qu'|se|s'|c'est|marche\w*|fonctionne\w*|bug\w*|plante\w*|rame\w*|"
                r"ferme\w*|quitte\w*|pas|plus|comment|pourquoi)\b", reste, re.I):
            return None
        debut = "Claude n'est pas disponible, et sans lui " if claude_present else ""
        if re.search(r"\b(et|puis|pour|avec|sur|dans)\b", reste, re.I):
            phrase = (debut + "je ne peux pas faire cette demande en plusieurs étapes. "
                      "Demande-moi une seule chose à la fois, par exemple : ouvre Chrome.")
        else:
            nom = re.sub(r"^(?:(?:le|la|les|l'|mon|ma|mes|un|une|moi)\s*)+", "", reste, flags=re.I)
            nom = re.sub(r"^(?:logiciel|application|appli|programme|jeu)\s+", "", nom, flags=re.I).strip() or reste
            phrase = (debut + f"je n'ai pas trouvé « {nom} » parmi les applications de ce PC. "
                      "Redis-moi son nom, ou vérifie qu'elle est bien installée.")
        return phrase[0].upper() + phrase[1:]
    except Exception as erreur:
        print("Assistants, action locale :", erreur)
        return None


def _vide():
    return {"consentement": False, "comptes": []}


def charger():
    """Les réglages (consentement + comptes). Un fichier absent ou abîmé donne des réglages vides, sans erreur."""
    with _verrou:
        try:
            with open(FICHIER, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or not isinstance(d.get("comptes"), list):
                return _vide()
            d.setdefault("consentement", False)
            d["comptes"] = [c for c in d["comptes"] if isinstance(c, dict) and c.get("id")]
            return d
        except Exception:
            return _vide()


def sauver(d):
    """Écrit les réglages d'un coup (fichier temporaire puis remplacement : jamais de fichier à moitié écrit)."""
    with _verrou:
        try:
            tmp = FICHIER + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, FICHIER)
            return True
        except Exception as e:
            print("Assistants (sauvegarde) :", e)
            return False


# ------------------------------------------------------------------ clé chiffrée (DPAPI Windows)

def _dpapi(donnees, chiffrer):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    tampon = ctypes.create_string_buffer(donnees, len(donnees))
    entree = BLOB(len(donnees), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))
    sortie = BLOB()
    f = ctypes.windll.crypt32.CryptProtectData if chiffrer else ctypes.windll.crypt32.CryptUnprotectData
    ok = f(ctypes.byref(entree), None, None, None, None, 0, ctypes.byref(sortie))
    if not ok:
        raise OSError("chiffrement Windows impossible")
    try:
        return ctypes.string_at(sortie.pbData, sortie.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(sortie.pbData)


def chiffrer_cle(cle):
    """La clé en texte -> texte chiffré (base64). Lève une erreur si Windows ne peut pas la chiffrer."""
    return base64.b64encode(_dpapi(cle.encode("utf-8"), True)).decode("ascii")


def dechiffrer_cle(texte):
    try:
        return _dpapi(base64.b64decode(texte), False).decode("utf-8")
    except Exception:
        return ""


def masquer(cle):
    """« sk-…ab12 » : de quoi reconnaître une clé sans l'afficher."""
    cle = (cle or "").strip()
    return "" if not cle else (cle[:3] + "…" + cle[-4:] if len(cle) > 10 else "•••")


# ------------------------------------------------------------------ comptes

def nettoyer_cle(cle):
    """Enlève espaces, retours à la ligne, guillemets et « Bearer » qu'un copier-coller ramène souvent."""
    cle = (cle or "").strip().strip("\"'`").strip()
    cle = re.sub(r"^(?i:bearer)\s+", "", cle)
    return re.sub(r"\s+", "", cle)


def nettoyer_adresse(adresse):
    a = (adresse or "").strip().rstrip("/")
    for fin in ("/chat/completions", "/models"):
        if a.endswith(fin):
            a = a[: -len(fin)].rstrip("/")
    return a


def adresse_valide(adresse):
    return bool(re.match(r"^https?://[^\s/]+(:\d+)?(/\S*)?$", adresse or "")) and (
        adresse.startswith("https://") or re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", adresse))


def ajouter_compte(fournisseur, cle, modele="", adresse="", etiquette=""):
    """Ajoute un compte à la fin de la liste. Renvoie (réussi, message simple, id du compte)."""
    f = PAR_ID.get(fournisseur)
    if not f:
        return False, "Je ne connais pas ce fournisseur.", None
    cle = nettoyer_cle(cle)
    adresse = nettoyer_adresse(adresse or f["adresse"])
    if not f.get("sans_cle") and len(cle) < 8:
        return False, "La clé semble vide ou trop courte. Copie-la en entier depuis le site du fournisseur.", None
    if not adresse_valide(adresse):
        return False, "L'adresse doit commencer par https:// (ou http://localhost pour un assistant sur ce PC).", None
    try:
        chiffree = chiffrer_cle(cle) if cle else ""
    except Exception:
        return False, "Windows n'a pas pu protéger la clé : je ne la garde pas.", None
    with _verrou:
        d = charger()
        n = 1 + sum(1 for c in d["comptes"] if c.get("fournisseur") == fournisseur)
        cid = f"{fournisseur}-{int(time.time())}-{n}"
        d["comptes"].append({"id": cid, "fournisseur": fournisseur, "etiquette": (etiquette or "").strip()[:40],
                             "adresse": adresse, "modele": (modele or f["modele"]).strip(), "cle": chiffree,
                             "actif": True, "pause_jusqua": 0, "derniere_erreur": ""})
        ok = sauver(d)
    return (True, "Compte ajouté.", cid) if ok else (False, "Je n'ai pas pu enregistrer le compte.", None)


def compte(cid):
    for c in charger()["comptes"]:
        if c["id"] == cid:
            return c
    return None


def modifier_compte(cid, **champs):
    with _verrou:
        d = charger()
        for c in d["comptes"]:
            if c["id"] == cid:
                for k, v in champs.items():
                    if k == "cle":
                        v = chiffrer_cle(nettoyer_cle(v)) if nettoyer_cle(v) else ""
                    c[k] = v
                return sauver(d)
    return False


def supprimer_compte(cid):
    with _verrou:
        d = charger()
        d["comptes"] = [c for c in d["comptes"] if c["id"] != cid]
        return sauver(d)


def deplacer_compte(cid, sens):
    """sens = -1 (monter) ou +1 (descendre) dans la liste de priorité."""
    with _verrou:
        d = charger()
        liste = d["comptes"]
        i = next((k for k, c in enumerate(liste) if c["id"] == cid), None)
        j = None if i is None else i + sens
        if i is None or j < 0 or j >= len(liste):
            return False
        liste[i], liste[j] = liste[j], liste[i]
        return sauver(d)


def accepter_consentement(oui=True):
    with _verrou:
        d = charger()
        d["consentement"] = bool(oui)
        return sauver(d)


def nom_affiche(c):
    f = PAR_ID.get(c.get("fournisseur"), {})
    base = f.get("nom", c.get("fournisseur", "?"))
    return base + (f" ({c['etiquette']})" if c.get("etiquette") else "")


def _utilisables(d=None):
    d = d or charger()
    maintenant = time.time()
    return [c for c in d["comptes"] if c.get("actif", True) and c.get("pause_jusqua", 0) <= maintenant
            and (c.get("cle") or PAR_ID.get(c.get("fournisseur"), {}).get("sans_cle"))]


def disponible():
    """Vrai s'il y a au moins un compte prêt ET que l'utilisateur a accepté l'envoi chez un tiers."""
    try:
        d = charger()
        return bool(d.get("consentement")) and bool(_utilisables(d))
    except Exception:
        return False


# ------------------------------------------------------------------ appels réseau

class Erreur(Exception):
    def __init__(self, genre, message):
        super().__init__(message)
        self.genre = genre            # « cle », « quota », « panne », « adresse », « modele », « autre »


def _requete(c, chemin, corps=None, delai=DELAI_REPONSE_S):
    adresse = nettoyer_adresse(c.get("adresse", "")) + chemin
    cle = dechiffrer_cle(c.get("cle", "")) if c.get("cle") else ""
    en_tetes = {"Content-Type": "application/json", "User-Agent": "Jarvis-assistant"}
    if cle:
        en_tetes["Authorization"] = "Bearer " + cle
    donnees = None if corps is None else json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(adresse, data=donnees, headers=en_tetes, method="POST" if donnees else "GET")
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            detail = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = ""
        if code in (401, 403):
            raise Erreur("cle", "La clé est refusée (fausse, expirée ou sans droit).")
        if code in (402, 429):
            raise Erreur("quota", "La limite d'utilisation est atteinte (ou le crédit est épuisé).")
        if code == 404:
            raise Erreur("modele", "Adresse ou modèle introuvable. " + detail[:120])
        if code >= 500:
            raise Erreur("panne", "Le service a un problème en ce moment.")
        raise Erreur("autre", f"Le service a refusé la demande (code {code}). {detail[:120]}")
    except urllib.error.URLError as e:
        raise Erreur("adresse", "Impossible de joindre le service : vérifie ta connexion Internet "
                                "(ou, pour Ollama, qu'il est bien ouvert).")
    except TimeoutError:
        raise Erreur("panne", "Le service met trop de temps à répondre.")
    except (ValueError, OSError):
        raise Erreur("autre", "Réponse illisible du service.")


_MOTS_PREFERES = ("flash", "mini", "small", "lite", "haiku", "fast", "instant")
_MOTS_EXCLUS = ("embed", "embedding", "image", "vision", "tts", "whisper", "audio", "moderation", "rerank",
                "imagen", "veo", "dall", "video", "ocr", "transcribe", "live", "preview-tts",
                "computer-use", "robotics", "magistral", "thinking", "reasoner", "codestral", "devstral", "coder",
                "guard", "safety", "realtime", "search-preview", "deep-research", "aqa", "learnlm", "gemma",
                "customtools", "-exp")
# Modèles habituels, simples et rapides, essayés en premier (le premier qui existe chez le fournisseur gagne).
MODELES_CONSEILLES = {
    "gemini": ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.5-flash"),
    "mistral": ("mistral-small-latest", "mistral-medium-latest"),
    "deepseek": ("deepseek-chat",),
    "kimi": ("kimi-k2.6", "kimi-k3"),
    "openai": ("gpt-4.1-mini", "gpt-4o-mini"),
}


def lister_modeles(c):
    """Les modèles proposés par le fournisseur (texte seulement), les plus adaptés d'abord."""
    r = _requete(c, "/models", delai=20)
    liste = r.get("data") if isinstance(r, dict) else r
    noms = []
    for m in liste or []:
        n = m.get("id") if isinstance(m, dict) else str(m)
        n = (n or "").replace("models/", "", 1)
        if n and not any(x in n.lower() for x in _MOTS_EXCLUS):
            noms.append(n)
    noms = sorted(set(noms))
    noms.sort(key=lambda n: (0 if any(w in n.lower() for w in _MOTS_PREFERES) else 1))
    conseilles = [m for m in MODELES_CONSEILLES.get(c.get("fournisseur"), ()) if m in noms]
    return conseilles + [n for n in noms if n not in conseilles]


def tester(cid):
    """Essaie le compte pour de vrai. Renvoie (réussi, message simple)."""
    ok, message, _ = tester_detail(cid)
    return ok, message


def tester_detail(cid):
    """Comme tester, avec en plus le genre d'erreur (« cle », « quota », « panne », « adresse », « modele », « autre »,
    ou « » si tout va bien). Choisit un modèle si aucun n'est réglé."""
    c = compte(cid)
    if not c:
        return False, "Compte introuvable.", "autre"
    try:
        if not c.get("modele"):
            modeles = lister_modeles(c)
            if not modeles:
                return False, "Le service ne propose aucun modèle de texte : indique-le à la main (réglages avancés).", "modele"
            c["modele"] = modeles[0]
            modifier_compte(cid, modele=modeles[0])
        r = _poser(c, "Réponds seulement par le mot : bonjour")
        if not r:
            return False, "Le service répond, mais sans texte. Essaie un autre modèle.", "modele"
        modifier_compte(cid, pause_jusqua=0, derniere_erreur="", actif=True)
        return True, f"Ça marche ! Modèle utilisé : {c['modele']}.", ""
    except Erreur as e:
        modifier_compte(cid, derniere_erreur=str(e))
        return False, str(e), e.genre
    except Exception as e:
        return False, f"Test impossible ({e}).", "autre"


def _poser(c, texte, longue=False, historique=()):
    messages = [{"role": "system", "content": consigne(longue)}]
    for question, reponse in historique:
        messages += [{"role": "user", "content": question}, {"role": "assistant", "content": reponse}]
    messages.append({"role": "user", "content": texte})
    corps = {"model": c["modele"], "max_tokens": 2000 if longue else 600, "messages": messages}
    r = _requete(c, "/chat/completions", corps, delai=120 if longue else DELAI_REPONSE_S)
    try:
        sortie = (r["choices"][0]["message"].get("content") or "").strip()
    except Exception:
        raise Erreur("autre", "Réponse inattendue du service.")
    sortie = re.sub(r"<think>.*?</think>", "", sortie, flags=re.S).strip()
    sortie = re.sub(r"[*_#`]+", "", sortie)
    return sortie[:MAX_REPONSE]


# Mémoire de la conversation : seulement en mémoire vive (jamais écrite sur le disque), pour que « et demain ? »
# ou « explique mieux » marchent. Elle s'efface seule après 15 minutes sans question.
_historique = []
_derniere_question = []          # [question nettoyée, réponse, heure, nom de l'assistant]
MAX_ECHANGES = 4                # peu d'historique = peu de quota consommé
MEME_QUESTION_S = 180           # même question redite dans les 3 minutes : on rejoue la réponse, sans rappeler le service
OUBLI_APRES_S = 15 * 60


def oublier():
    with _verrou:
        _historique.clear()
        _derniere_question.clear()


def _recent():
    with _verrou:
        if _historique and time.time() - _historique[-1][2] > OUBLI_APRES_S:
            _historique.clear()
        return [(q, r) for q, r, _ in _historique[-MAX_ECHANGES:]]


def _retenir(question, reponse):
    with _verrou:
        _historique.append((question[:300], reponse[:300], time.time()))
        del _historique[:-MAX_ECHANGES]


def utilisable_maintenant():
    """Vrai si un autre assistant peut répondre à l'instant : compte prêt, accord donné, et ni mode enfant ni invité."""
    try:
        if not disponible():
            return False
        import jarvis_enfant
        import jarvis_extras
        return not (jarvis_enfant.actif() or jarvis_extras.invite())
    except Exception:
        return False


def demander(texte, longue=False):
    """Pose la question au premier assistant prêt, puis au suivant en cas de limite ou de panne.
    longue=True : un texte long (histoire). Renvoie (réponse, nom de l'assistant, erreur)."""
    try:
        d = charger()
        if not d.get("consentement"):
            return "", "", "Les autres assistants ne sont pas activés."
        propre = re.sub(r"\W+", " ", (texte or "").lower()).strip()
        if len(propre) < 4 or len(propre.split()) < 2 and len(propre) < 8:      # un bruit mal compris ne consomme rien
            return "", "", "Je n'ai pas bien compris la question."
        with _verrou:
            vu = _derniere_question
            if vu and vu[0] == propre and not longue and time.time() - vu[2] < MEME_QUESTION_S:
                return vu[1], vu[3], ""
        essais = _utilisables(d)
        if not essais:
            return "", "", "Aucun autre assistant n'est disponible pour le moment."
        historique = _recent()
        derniere = ""
        for c in essais:
            try:
                if not c.get("modele"):
                    modeles = lister_modeles(c)
                    if not modeles:
                        continue
                    c["modele"] = modeles[0]
                    modifier_compte(c["id"], modele=c["modele"])
                debut = time.time()
                reponse = _poser(c, texte, longue, historique)
                journaliser(c, texte, reponse, "" if reponse else "réponse vide", time.time() - debut,
                            "histoire" if longue else "normal")
                if reponse:
                    _retenir(texte, reponse)
                    if not longue:
                        with _verrou:
                            _derniere_question[:] = [propre, reponse, time.time(), nom_affiche(c)]
                    return reponse, nom_affiche(c), ""
            except Erreur as e:
                derniere = str(e)
                journaliser(c, texte, "", f"{e.genre} : {e}", time.time() - debut if "debut" in dir() else 0)
                duree = {"quota": PAUSE_QUOTA_S, "panne": PAUSE_PANNE_S, "adresse": PAUSE_PANNE_S}.get(e.genre, 0)
                if e.genre == "cle":
                    modifier_compte(c["id"], actif=False, derniere_erreur=str(e))
                else:
                    modifier_compte(c["id"], pause_jusqua=time.time() + duree, derniere_erreur=str(e))
            except Exception as e:
                derniere = str(e)
                journaliser(c, texte, "", f"exception : {e}", 0)
        return "", "", derniere or "Les autres assistants n'ont pas répondu."
    except Exception as e:
        return "", "", f"Erreur inattendue ({e})."


# ------------------------------------------------------------------ journal des réponses
FICHIER_JOURNAL = jarvis_config.chemin("assistants_journal.jsonl")
MAX_LIGNES_JOURNAL = 1000


def journaliser(c, question, reponse, erreur, duree, mode="normal"):
    """Une ligne par essai dans assistants_journal.jsonl (fichier de CE PC : ignoré par git, jamais envoyé dans les
    rapports) et une ligne lisible dans jarvis.log. Ne doit jamais gêner Jarvis."""
    try:
        ligne = {"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "assistant": nom_affiche(c),
                 "fournisseur": c.get("fournisseur"), "modele": c.get("modele") or "", "mode": mode,
                 "duree_s": round(duree, 2), "question": (question or "")[:500],
                 "reponse": (reponse or "")[:MAX_REPONSE], "erreur": (erreur or "")[:300],
                 "mots_reponse": len((reponse or "").split())}
        with _verrou:
            with io.open(FICHIER_JOURNAL, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            try:
                if os.path.getsize(FICHIER_JOURNAL) > 600_000:          # on garde les plus récentes
                    with io.open(FICHIER_JOURNAL, encoding="utf-8") as f:
                        lignes = f.read().splitlines()[-MAX_LIGNES_JOURNAL:]
                    with io.open(FICHIER_JOURNAL, "w", encoding="utf-8") as f:
                        f.write("\n".join(lignes) + "\n")
            except Exception:
                pass
        if erreur:
            print(f"Assistant {ligne['assistant']} ({ligne['modele']}) : ÉCHEC en {ligne['duree_s']} s : {erreur[:120]}")
        else:
            print(f"Assistant {ligne['assistant']} ({ligne['modele']}) en {ligne['duree_s']} s, "
                  f"{ligne['mots_reponse']} mots : {reponse[:400]}")
    except Exception:
        pass


# ------------------------------------------------------------------ essai oral (tour de rôle)
FLAG_ESSAI = jarvis_config.chemin("test_assistants.flag")


def essai_actif():
    return os.path.exists(FLAG_ESSAI)


def tour_de_essai(texte):
    """Mode d'essai : la question va à UN seul assistant (le suivant dans la liste), sans bascule, pour entendre la
    réponse de chacun. Renvoie le texte à dire, ou None si le mode n'est pas utilisable."""
    try:
        d = charger()
        comptes = [c for c in d.get("comptes", []) if c.get("cle") or PAR_ID.get(c.get("fournisseur"), {}).get("sans_cle")]
        if not d.get("consentement") or not comptes:
            return None
        try:
            i = int(io.open(FLAG_ESSAI, encoding="utf-8").read().strip() or 0)
        except Exception:
            i = 0
        c = comptes[i % len(comptes)]
        suivant = comptes[(i + 1) % len(comptes)]
        io.open(FLAG_ESSAI, "w", encoding="utf-8").write(str(i + 1))
        nom = nom_affiche(c)
        try:
            if not c.get("modele"):
                modeles = lister_modeles(c)
                if modeles:
                    c["modele"] = modeles[0]
                    modifier_compte(c["id"], modele=c["modele"])
            debut = time.time()
            reponse = _poser(c, texte)
            journaliser(c, texte, reponse, "" if reponse else "réponse vide", time.time() - debut, "essai")
            dit = f"{nom} répond. {reponse}" if reponse else f"{nom} n'a rien répondu."
        except Erreur as e:
            journaliser(c, texte, "", f"{e.genre} : {e}", time.time() - debut if "debut" in dir() else 0, "essai")
            dit = f"{nom} n'a pas pu répondre : {e}"
        except Exception as e:
            journaliser(c, texte, "", f"exception : {e}", 0, "essai")
            dit = f"{nom} n'a pas pu répondre ({e})."
        print("Essai assistants :", nom)
        return f"{dit} Prochain assistant : {nom_affiche(suivant)}."
    except Exception as e:
        print("Essai assistants :", e)
        return None
