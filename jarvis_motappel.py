"""
JARVIS - détecteur du mot d'appel « Jarvis » entraîné exprès (openWakeWord), en complément de Vosk.

Vosk transcrit tout ce qu'il entend ; quand il comprend mal « Jarvis » (« jardin », « j'arrive »...), la
demande est perdue. Ce détecteur écoute le même son et donne, toutes les 80 ms, une note de 0 à 1 :
au-dessus du seuil, Jarvis considère qu'on l'a appelé, même si Vosk a mal transcrit le mot.

Les trois modèles sont dans le dossier mot_appel :
  melspectrogram.onnx et embedding_model.onnx   préparation du son (openWakeWord, licence Apache 2.0)
  jarvis.onnx                                    le mot « Jarvis », entraîné avec des voix françaises de synthèse
Sans ces fichiers (ou sans onnxruntime), le détecteur se désactive tout seul et Jarvis marche comme avant.
Le calcul reprend celui d'openWakeWord (github.com/dscripka/openWakeWord, Apache 2.0), sans ses dépendances.
"""

import os
import threading

import numpy as np

import jarvis_config

DOSSIER = jarvis_config.chemin("mot_appel")
SEUIL = 0.3                    # note minimale pour considérer que « Jarvis » a été dit (Whisper vérifie ensuite) ;
                               # 21/11 : à 0,3 au lieu de 0,5, 95 « Jarvis » sur 104 au lieu de 93, sans fausse alerte de plus
BLOC = 1280                    # 80 ms à 16 kHz : la cadence du modèle


class Detecteur:
    def __init__(self, dossier=DOSSIER):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        charger = lambda nom: ort.InferenceSession(os.path.join(dossier, nom), sess_options=options,
                                                   providers=["CPUExecutionProvider"])
        self._mel = charger("melspectrogram.onnx")
        self._emb = charger("embedding_model.onnx")
        self._mot = charger("jarvis.onnx")
        self._entree_mot = self._mot.get_inputs()[0].name
        self._trames = int(self._mot.get_inputs()[0].shape[1])        # 16 en général
        self._verrou = threading.Lock()
        bruit = np.random.RandomState(0).randint(-1000, 1000, 16000 * 4).astype(np.int16)
        self._traits_depart = self._embeddings_clip(bruit)              # comme openWakeWord au démarrage
        self.reinitialiser()

    def reinitialiser(self):
        with self._verrou:
            self._brut = np.zeros(0, dtype=np.int16)                   # son pas encore traité
            self._passe = np.zeros(160 * 3, dtype=np.int16)            # recouvrement pour le spectrogramme
            self._spectre = np.ones((76, 32), dtype=np.float32)
            self._traits = self._traits_depart.copy()
            self._notes = 0                                             # les 5 premières notes valent 0

    def _spectrogramme(self, son):
        sortie = self._mel.run(None, {"input": son.astype(np.float32)[None, :]})[0]
        return np.squeeze(sortie) / 10 + 2

    def _embeddings_clip(self, son):
        spectre = self._spectrogramme(son)
        fenetres = [spectre[i:i + 76] for i in range(0, spectre.shape[0], 8) if spectre[i:i + 76].shape[0] == 76]
        lot = np.array(fenetres, dtype=np.float32)[:, :, :, None]
        return np.atleast_2d(self._emb.run(None, {"input_1": lot})[0].squeeze())

    def ecouter(self, son):
        """son : octets PCM 16 bits mono 16 kHz (ou tableau int16). Renvoie la meilleure note des blocs traités."""
        if isinstance(son, (bytes, bytearray)):
            son = np.frombuffer(bytes(son), dtype=np.int16)
        meilleure = 0.0
        with self._verrou:
            self._brut = np.concatenate((self._brut, son))
            while len(self._brut) >= BLOC:
                bloc, self._brut = self._brut[:BLOC], self._brut[BLOC:]
                spectre = self._spectrogramme(np.concatenate((self._passe, bloc)))
                self._passe = bloc[-160 * 3:]
                self._spectre = np.vstack((self._spectre, spectre))[-970:]
                fenetre = self._spectre[-76:].astype(np.float32)[None, :, :, None]
                trait = self._emb.run(None, {"input_1": fenetre})[0].reshape(1, -1)
                self._traits = np.vstack((self._traits, trait))[-120:]
                note = float(self._mot.run(None, {self._entree_mot: self._traits[-self._trames:][None, :, :]
                                                  .astype(np.float32)})[0].reshape(-1)[0])
                self._notes += 1
                if self._notes <= 5:
                    note = 0.0
                meilleure = max(meilleure, note)
        return meilleure

    def note_clip(self, son, marge=1.0):
        """Note maximale sur un enregistrement entier : le son est passé bloc par bloc, entouré de silence."""
        self.reinitialiser()
        silence = np.zeros(int(16000 * marge), dtype=np.int16)
        son = np.concatenate((silence, np.asarray(son, dtype=np.int16), silence))
        return max(self.ecouter(son[i:i + BLOC]) for i in range(0, len(son) - BLOC + 1, BLOC))


_detecteur = None
_essaye = False


def detecteur():
    """Le détecteur prêt à l'emploi, ou None si les modèles ne sont pas là (Jarvis marche alors comme avant)."""
    global _detecteur, _essaye
    if not _essaye:
        _essaye = True
        if all(os.path.exists(os.path.join(DOSSIER, nom))
               for nom in ("melspectrogram.onnx", "embedding_model.onnx", "jarvis.onnx")):
            try:
                _detecteur = Detecteur()
                print("Mot d'appel : détecteur « Jarvis » chargé.")
            except Exception as erreur:
                print("Mot d'appel : détecteur indisponible (", erreur, ")")
    return _detecteur


# Secondes analysées au début de chaque phrase : « Jarvis » y est. Sur 300 vraies demandes : 5 s -> 97 % des
# « Jarvis » reconnus, aucune fausse alerte, environ 0,25 s de calcul (2,5 s -> 91 %, 3,5 s -> 94 %)
DEBUT_ANALYSE = 5.0


def note_debut(audio):
    """Note du détecteur sur le début d'une phrase (octets PCM 16 bits). 0 si le détecteur n'est pas là."""
    d = detecteur()
    if d is None or not audio:
        return 0.0
    try:
        son = np.frombuffer(bytes(audio[:int(16000 * 2 * DEBUT_ANALYSE)]), dtype=np.int16)
        return d.note_clip(son, marge=1.0)
    except Exception as erreur:
        print("Mot d'appel :", erreur)
        return 0.0
