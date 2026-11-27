"""Essai : chaque réglage choisi est-il retrouvé tel quel après l'arrêt et le redémarrage de Jarvis ?
Deux processus : le premier change tous les réglages (dans un fichier provisoire, jamais le vrai preferences.json),
le second, tout neuf, recharge ce fichier comme au démarrage et compare ce que chaque réglage vaut."""
import json
import os
import subprocess
import sys
import tempfile

DOSSIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DOSSIER)
PROVISOIRE = os.path.join(tempfile.gettempdir(), "essai_preferences.json")
ATTENDU = os.path.join(tempfile.gettempdir(), "essai_preferences_attendu.json")


def phase_a():
    import jarvis_reglages_ui as r
    r.FICHIER = PROVISOIRE
    if os.path.exists(PROVISOIRE):
        os.remove(PROVISOIRE)
    r.charger()
    attendu = {}
    for cle, _, _, genre, mod, attr, options in r.REGLAGES:
        if r._module(mod) is None:
            continue                                   # le réacteur n'existe que dans le vrai Jarvis
        defaut = r.DEFAUTS.get(cle)
        if genre == "bool":
            v = not bool(defaut)
        elif genre == "nombre":
            mini, maxi = options[0], options[1]
            v = maxi if abs(defaut - mini) < abs(defaut - maxi) else mini
        else:
            v = next(valeur for _, valeur in options if valeur != defaut)
        r.regler(cle, v)
        attendu[cle] = v
    r._module("jarvis_claude").regler_micro(True)
    r.regler("micro", "bruyante")
    r.regler("reveil", "prudente")
    r.regler("nuit_auto", "22 h à 7 h")
    r.regler("jauges", ["CPU", "RAM"])
    attendu.update(micro_coupe=True, micro="bruyante", reveil="prudente", nuit_auto="22 h à 7 h", jauges=["CPU", "RAM"])
    with open(ATTENDU, "w", encoding="utf-8") as f:
        json.dump(attendu, f)
    print("phase A :", len(attendu), "réglages changés")


def phase_b():
    import jarvis_reglages_ui as r
    r.FICHIER = PROVISOIRE
    r.charger()
    with open(ATTENDU, encoding="utf-8") as f:
        attendu = json.load(f)
    fautes = 0

    def verifie(nom, ok, vu=None):
        nonlocal fautes
        if not ok:
            fautes += 1
        print(("OK   " if ok else "FAUX ") + nom + ("" if ok else f" (vu : {vu!r})"))
    for cle, v in attendu.items():
        if cle in ("micro", "reveil", "nuit_auto", "jauges", "micro_coupe"):
            continue
        vu = r.valeur(cle)
        egal = (abs(float(vu) - float(v)) < 1e-9) if isinstance(v, (int, float)) and not isinstance(v, bool) and vu is not None else vu == v
        verifie(f"réglage « {cle} » retrouvé après redémarrage", egal, vu)
    jc = r._module("jarvis_claude")
    verifie("sensibilité du micro retrouvée", (jc.SEUIL_SON_MIN, jc.SEUIL_SON_MAX) == (0.015, 0.022), (jc.SEUIL_SON_MIN, jc.SEUIL_SON_MAX))
    verifie("sensibilité du réveil retrouvée", (jc.PAUSE_AVANT_JARVIS, jc.PAUSE_LONGUE_AVANT_JARVIS) == (0.5, 1.1))
    import jarvis_config
    verifie("heures de nuit retrouvées", tuple(jarvis_config.HEURES_NUIT or ()) == (22, 7), jarvis_config.HEURES_NUIT)
    verifie("jauges retrouvées", tuple(r._module("jarvis_affichage").JAUGES) == ("CPU", "RAM"))
    verifie("le micro coupé est retrouvé après redémarrage", micro_coupe_retrouve(r))
    print("RESULTAT :", "TOUT EST BON" if not fautes else f"{fautes} faute(s)")
    sys.exit(1 if fautes else 0)


def micro_coupe_retrouve(r):
    jc = r._module("jarvis_claude")
    return bool(getattr(jc, "micro_coupe", False)) is True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "b":
        phase_b()
    elif len(sys.argv) > 1 and sys.argv[1] == "a":
        phase_a()
    else:
        env = dict(os.environ)
        subprocess.run([sys.executable, __file__, "a"], check=True, env=env, cwd=DOSSIER)
        sys.exit(subprocess.run([sys.executable, __file__, "b"], env=env, cwd=DOSSIER).returncode)
