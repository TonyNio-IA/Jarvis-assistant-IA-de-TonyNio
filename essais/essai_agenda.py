# -*- coding: utf-8 -*-
"""Agenda iCloud : un agenda d'essai (jamais le vrai) passe par le calendrier familial et « c'est quand… »."""
import datetime, os, re, sys, tempfile
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import jarvis_agenda as a, jarvis_foyer as f, jarvis_commandes as c

f.FICHIER_CALENDRIER = os.path.join(tempfile.mkdtemp(), "calendrier.json") if hasattr(f, "FICHIER_CALENDRIER") else None
d = datetime.date.today() + datetime.timedelta(days=1)
dd = d.strftime("%Y%m%d")
jour_ics = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][d.weekday()]
ICS = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Paris:{dd}T170000
DTEND;TZID=Europe/Paris:{dd}T180000
SUMMARY:Piscine
RRULE:FREQ=WEEKLY;BYDAY={jour_ics};COUNT=4
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART;TZID=Europe/Paris:{(d + datetime.timedelta(days=9)).strftime('%Y%m%d')}T101500
DTEND;TZID=Europe/Paris:{(d + datetime.timedelta(days=9)).strftime('%Y%m%d')}T110000
SUMMARY:Dentiste
LOCATION:Cabinet du centre
END:VEVENT
END:VCALENDAR"""
a.lien = "essai"
a._telecharger = lambda: ICS
erreurs = 0
for phrase, attendu in [("qu'est-ce qu'on a demain ?", r"Demain : à 17 heures?, Piscine"),
                        ("c'est quand le dentiste ?", r"Dentiste \(lieu : Cabinet du centre\)"),
                        ("c'est quand la piscine ?", r"demain à 17 h : Piscine"),
                        ("c'est quand les prochaines vacances ?", r"vacances")]:
    r = c.commande_instantanee([phrase])
    ok = bool(r and re.search(attendu, r))
    erreurs += 0 if ok else 1
    print(("OK   " if ok else "ÉCHEC ") + f"« {phrase} » -> {r}")
ok = (a.rendez_vous_de_demain() or "").startswith("Demain dans l'agenda : à 17 h : Piscine")
erreurs += 0 if ok else 1
print(("OK   " if ok else "ÉCHEC ") + "rappel de la veille :", a.rendez_vous_de_demain())
ok = a.commande("c'est quand le match de foot ?") is None
erreurs += 0 if ok else 1
print(("OK   " if ok else "ÉCHEC ") + "« c'est quand le match » : absent de l'agenda, laissé à Claude")
print(f"erreurs : {erreurs}")
