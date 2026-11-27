import sys, os, json, shutil, tempfile, hashlib
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
def h(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:10] if os.path.exists(p) else None
avant = {f: h(f) for f in ("memoire.json", "notes.txt", "enfant.json", "liste.json")}
import jarvis_commandes as c, jarvis_profils as p, jarvis_memoire as m, jarvis_enfant as e, jarvis_extras as x
essai = tempfile.mkdtemp(prefix="jarvis_profils_")
p.FICHIER, p.DOSSIER = os.path.join(essai, "profils.json"), os.path.join(essai, "profils")
enfant_depart = e.actif()
def dire(phrase):
    r = c.commande_instantanee([phrase]); print(f"{phrase!r} -> {r!r}"); return r
dire("crée un profil pour Zoé"); dire("crée un profil enfant pour Tom"); dire("quels sont les profils")
dire("qui suis-je"); dire("c'est nul"); dire("c'est Zoé"); dire("qui suis-je")
dire("retiens que j'adore le thé vert"); dire("note que acheter des fleurs")
print("  faits Zoé:", m.faits(), "| fichier:", os.path.relpath(m.FICHIER, essai))
dire("lis mes mails"); dire("lis mes notes")
dire("c'est Tom"); print("  mode enfant:", e.actif(), "| faits Tom:", m.faits())
dire("passe sur le profil principal"); print("  mode enfant revenu:", e.actif() == enfant_depart, "| mémoire principale:", m.FICHIER == os.path.join(r"C:\Jarvis", "memoire.json"), "| nb faits:", len(m.faits()) > 0)
dire("c'est Zoé"); print("  Zoé retrouve:", m.faits()); dire("lis mes notes")
dire("supprime le profil de Zoé"); dire("oui"); dire("quels sont les profils"); dire("qui suis-je")
print("  mis de côté:", os.listdir(os.path.join(p.DOSSIER, "_supprimes")))
p.activer(None); x.redemarrer_claude = False
apres = {f: h(f) for f in avant}
print("fichiers personnels intacts:", avant == apres, "| profils.json réel créé:", os.path.exists(r"C:\Jarvis\profils.json"))
shutil.rmtree(essai, ignore_errors=True)
