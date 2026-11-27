import sys, queue, time
sys.path.insert(0, r"C:\Jarvis")
import jarvis_claude as jc

echecs = 0


def verif(nom, ok, detail=""):
    global echecs
    print(("OK   " if ok else "ECHEC"), nom, "->", str(detail)[:140])
    echecs += not ok


journal = []
VRAI_RETABLIR = jc._retablir_micro          # remis en place après les faux de l'essai 5
jc.sous_titre = lambda texte="", *a, **k: journal.append(("texte", texte))
jc.etat = lambda nom: journal.append(("etat", nom))
jc.time.sleep = lambda s: None
jc.MICRO_MESSAGE_DUREE = 0.3          # 0,3 s au lieu de 2 minutes, pour l'essai
jc.MICRO_ABANDON = 0.3                # 0,3 s au lieu de 10 minutes
jc.derniere_activite = 0              # rien d'écrit récemment


class FauxMicro:
    """Remplace _MicroRobuste : 'reponses' = ce que rouvrir() renvoie, essai après essai."""
    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []
    def rouvrir(self, reinit, attente):
        self.appels.append((reinit, attente))
        return self.reponses.pop(0) if self.reponses else None


def avec(micro):
    journal.clear()
    jc._micro_actif = micro
    return jc._retablir_micro()


# 1. retrouvé au 2e essai : pas de message
m = FauxMicro([None, b"son"])
r = avec(m)
verif("retrouvé au 2e essai", r == b"son" and len(m.appels) == 2, m.appels)
verif("  sans message", not any(t == ("texte", jc.MICRO_MESSAGE) for t in journal), journal)
verif("  1er essai sans réinitialisation, le suivant avec", m.appels[0][0] is False and m.appels[1][0] is True, m.appels)

# 2. retrouvé au 3e essai
m = FauxMicro([None, None, b"x"])
r = avec(m)
verif("retrouvé au 3e essai, sans message", r == b"x" and ("texte", jc.MICRO_MESSAGE) not in journal, journal)

# 3. rien : 3 essais, puis le message, puis abandon (le gardien relancera Jarvis)
m = FauxMicro([])
r = avec(m)
verif("jamais retrouvé : renvoie None", r is None, r)
verif("  au moins 3 essais", len(m.appels) >= 3, len(m.appels))
verif("  message « Aucun micro détecté. » affiché", ("texte", jc.MICRO_MESSAGE) in journal, journal)
verif("  réacteur en erreur", ("etat", "erreur") in journal, journal)
verif("  message effacé à la fin", journal[-1] == ("texte", ""), journal[-1])
verif("  message affiché une seule fois", journal.count(("texte", jc.MICRO_MESSAGE)) == 1, journal)

# 4. retrouvé PENDANT le message : le message s'efface, le réacteur repasse en veille
m = FauxMicro([None, None, None, b"enfin"])
r = avec(m)
verif("retrouvé pendant le message", r == b"enfin", r)
verif("  message effacé et veille", journal[-2:] == [("texte", ""), ("etat", "veille")], journal[-3:])

# 5. _prochain_bloc : micro silencieux -> essais ; sinon l'erreur d'avant
jc.MICRO_MUET = 0.01
file = queue.Queue()
jc._retablir_micro = lambda: b"retrouve"
verif("_prochain_bloc : micro retrouvé", jc._prochain_bloc(file, time.time(), True) == (b"retrouve", True))
jc._retablir_micro = lambda: None
try:
    jc._prochain_bloc(file, time.time(), True)
    verif("_prochain_bloc : abandon", False, "pas d'erreur")
except RuntimeError as e:
    verif("_prochain_bloc : abandon avec l'erreur d'avant", "n'envoie plus de son" in str(e), e)
file.put(b"ok")
verif("_prochain_bloc : son normal", jc._prochain_bloc(file, time.time(), True) == (b"ok", True))

# 6. la vraie classe, avec un faux micro matériel
ouverts, termines = [], []


class FauxFlux:
    def __init__(self, donne):
        self.donne, self.ferme = donne, False
    def start(self):
        if self.donne:
            jc.audio_queue.put(b"bloc")
    def stop(self):
        pass
    def close(self):
        self.ferme = True


sequence = [False, False, False, True]   # ouverture du with + 2 réouvertures muettes, puis un micro qui envoie du son
jc._ouvrir_micro = lambda: (ouverts.append(1), FauxFlux(sequence.pop(0)))[1]
jc.sd._terminate = lambda: termines.append(1)
jc.sd._initialize = lambda: None
micro = jc._MicroRobuste()
with micro:
    jc.audio_queue.put(b"vieux")                        # un vieux bloc doit être jeté à la réouverture
    verif("rouvrir sans son : None", micro.rouvrir(False, 0.05) is None)
    verif("rouvrir avec réinitialisation PortAudio", micro.rouvrir(True, 0.05) is None and len(termines) == 1, termines)
    verif("rouvrir : son retrouvé, vieux bloc jeté", micro.rouvrir(True, 0.5) == b"bloc", None)
verif("sortie du with : micro fermé et plus actif", jc._micro_actif is None)

jc._retablir_micro = VRAI_RETABLIR
# 6b. sans micro, la fenêtre de discussion (demandes écrites, rappels, alertes) est traitée pendant l'attente
appels = []
jc._sans_micro_traiter = lambda: appels.append(1)
journal.clear()
r = jc._retablir_micro.__globals__["_micro_actif"] = FauxMicro([])
jc._micro_actif = FauxMicro([])
verif("sans micro : Jarvis finit par se relancer (None)", jc._retablir_micro() is None)
verif("  la fenêtre de discussion est traitée pendant l'attente", len(appels) >= 10, len(appels))
jc._sans_micro_traiter = lambda: 1 / 0                  # un traitement qui plante ne casse pas l'attente
jc._micro_actif = FauxMicro([None, None, None, b"ok"])
verif("  un traitement qui plante n'arrête pas l'attente", jc._retablir_micro() == b"ok")
jc._sans_micro_traiter = None
jc.derniere_activite = vrai_time_pour_activite = __import__("time").time()       # quelqu'un vient d'écrire
jc.MICRO_ABANDON = 0.1
jc._micro_actif = FauxMicro([])
debut = __import__("time").time()
jc.MICRO_MESSAGE_DUREE = 0.1
resultat = []
import threading
fil = threading.Thread(target=lambda: resultat.append(jc._retablir_micro()), daemon=True)
fil.start(); fil.join(1.0)
verif("  quelqu'un vient d'écrire : Jarvis ne se relance pas", fil.is_alive() and not resultat, resultat)
jc.derniere_activite = 0                                  # plus rien d'écrit : il peut se relancer
fil.join(3.0)
verif("  puis il se relance quand plus rien n'est écrit", not fil.is_alive() and resultat == [None], resultat)
jc.MICRO_MESSAGE_DUREE = 0.3
jc.MICRO_ABANDON = 0.3

# 7. démarrage sans micro : 3 essais puis message, effacé après la durée, puis micro trouvé
essais = {"n": 0}
horloge = {"t": 1000.0}
vrai_time = jc.time.time


def faux_info(kind=None):
    essais["n"] += 1
    horloge["t"] += 100
    if essais["n"] <= 6:
        raise RuntimeError("aucun micro")
    return {"name": "Micro test"}


jc.sd.query_devices = faux_info
jc.sd._terminate = lambda: None
journal.clear()
jc.time.time = lambda: horloge["t"]
jc.MICRO_MESSAGE_DUREE = 150
jc.attendre_micro()
jc.time.time = vrai_time
textes = [t for k, t in journal if k == "texte"]
verif("démarrage : message après 3 essais", textes[0].startswith("Aucun micro détecté"), textes)
verif("  effacé après la durée, puis à la fin", textes.count("") >= 1 and len(textes) <= 3, textes)
verif("  ne s'affiche pas avant le 3e essai", essais["n"] == 7, essais)

# 8. démarrage : micro trouvé au 2e essai -> aucun message
essais["n"] = 5
journal.clear()
jc.attendre_micro()
verif("démarrage : micro trouvé vite, aucun message", not [1 for k, t in journal if k == "texte" and t], journal)

# 9. attendre_micro : la fenêtre de discussion fonctionne pendant l'attente du démarrage
essais["n"] = 0
appels = []
journal.clear()
jc.MICRO_MESSAGE_DUREE = 99999


def faux_info2(kind=None):
    essais["n"] += 1
    if essais["n"] <= 4:
        raise RuntimeError("aucun micro")
    return {"name": "Micro test"}


jc.sd.query_devices = faux_info2
jc.attendre_micro(lambda: appels.append(1))
verif("démarrage sans micro : demandes écrites traitées pendant l'attente", len(appels) >= 30, len(appels))
jc.attendre_micro(lambda: 1 / 0) if False else None
essais["n"] = 0
jc.attendre_micro(lambda: 1 / 0)
verif("démarrage : un traitement qui plante n'empêche pas de trouver le micro", True)

print("=== %d ÉCHEC(S) ===" % echecs)
sys.stdout.flush()
import os
os._exit(1 if echecs else 0)       # un thread de jarvis_claude (spectre) empêcherait sinon de quitter
