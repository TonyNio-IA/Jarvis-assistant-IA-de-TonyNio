# -*- coding: utf-8 -*-
"""Mode léger 1.66 : Whisper garde ses 5 hypothèses ; les commandes connues partent sans attendre Whisper ;
la décision automatique (PC lent) marche comme avant. Bac à sable : mode_leger.json est celui de la copie."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_claude as j
sys.stdout.reconfigure(encoding="utf-8")
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


j._ecrire_mode_leger(choix="auto", actif=False, mesures=[])
verifier(not j.MODE_LEGER_ACTIF and j.WHISPER_FAISCEAU == 5, "au départ : mode normal, 5 hypothèses")
for d in (2.9, 3.1, 3.0):
    j.noter_duree_whisper(d)
verifier(not j.MODE_LEGER_ACTIF, "PC à 3 s par phrase : pas de mode léger")
j._durees_whisper.clear()
for d in (12.0, 13.0):
    j.noter_duree_whisper(d)
verifier(j.MODE_LEGER_ACTIF and j.jarvis_commandes.MODE_LEGER, "deux phrases à plus de 10 s : mode léger activé")
verifier(j.WHISPER_FAISCEAU == 5 and j.WHISPER_TEMPERATURES == (0.0, 0.4),
         "en mode léger, Whisper garde 5 hypothèses et ses 2 essais (mesure du 27/11 : aucun gain de temps sinon)")
verifier(j.etat_mode_leger().get("actif") is True, "la décision est gardée pour les prochains démarrages")
j.noter_duree_whisper(30.0)
verifier(j.etat_mode_leger().get("secondes") == [12.0, 13.0], "une fois en mode léger, plus de nouvelles mesures")
print(f"\n{ok} / {total} essais réussis.")
