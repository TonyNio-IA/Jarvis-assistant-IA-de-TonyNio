# -*- coding: utf-8 -*-
"""
Fabrique l'application Android de Jarvis (Jarvis-tablette.apk), sans Android Studio ni Gradle.

Il faut, dans C:\\Jarvis\\android-tools (jamais publié) : un JDK 17 (jdk17\\...), et le SDK Android en ligne de
commande avec platforms\\android-36 et build-tools\\36.0.0.
La signature de l'application (tablette\\signature, jamais publiée) est créée à la première fabrication : il faut
la garder, car Android n'accepte une mise à jour que si elle est signée comme l'application déjà installée.

    python-env\\python.exe android\\construire.py            fabrique android\\Jarvis-tablette.apk
    python-env\\python.exe android\\construire.py --publier  et la copie dans docs\\ (celle qui est publiée sur GitHub)
Le numéro de version est dans android\\version.json : « code » doit augmenter à chaque version proposée aux tablettes.
"""
import glob
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

ICI = os.path.dirname(os.path.abspath(__file__))
JARVIS = os.path.dirname(ICI)
OUTILS = os.path.join(JARVIS, "android-tools")
TRAVAIL = os.path.join(ICI, "construction")
SIGNATURE = os.path.join(JARVIS, "tablette", "signature")
SORTIE = os.path.join(ICI, "Jarvis-tablette.apk")
MIN_SDK, CIBLE_SDK = "26", "34"          # Android 8 au moins ; les règles d'Android 14 (marche aussi sur les suivants)


def trouver(motif, quoi):
    trouves = sorted(glob.glob(motif))
    if not trouves:
        sys.exit(f"Introuvable : {quoi} ({motif})")
    return trouves[-1]


JDK = trouver(os.path.join(OUTILS, "jdk17", "*", "bin", "java.exe"), "le JDK 17")
JDK = os.path.dirname(os.path.dirname(JDK))
OUTILS_SDK = os.path.dirname(trouver(os.path.join(OUTILS, "build-tools", "*", "aapt2.exe"), "les build-tools d'Android"))
ANDROID = trouver(os.path.join(OUTILS, "platforms", "android-*", "android.jar"), "la plateforme Android")
ENV = dict(os.environ, JAVA_HOME=JDK, PATH=os.path.join(JDK, "bin") + os.pathsep + os.environ.get("PATH", ""))


# Le moteur qui fait tourner le détecteur du mot « Jarvis » dans la tablette (ONNX Runtime, licence MIT), pris une fois
# sur Maven Central et gardé dans android-tools\onnx. Seules les tablettes ARM sont servies (32 et 64 bits).
ONNX_VERSION = "1.22.0"
ONNX_ADRESSE = ("https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/"
                f"{ONNX_VERSION}/onnxruntime-android-{ONNX_VERSION}.aar")
ONNX = os.path.join(OUTILS, "onnx", "ort-android.aar")
PROCESSEURS = ("arm64-v8a", "armeabi-v7a")


def moteur_onnx():
    """Renvoie (classes.jar du moteur, [(nom dans l'application, octets)] de ses bibliothèques)."""
    if not os.path.exists(ONNX):
        import urllib.request
        os.makedirs(os.path.dirname(ONNX), exist_ok=True)
        print("Téléchargement d'ONNX Runtime", ONNX_VERSION, "…")
        urllib.request.urlretrieve(ONNX_ADRESSE, ONNX + ".recu")
        os.replace(ONNX + ".recu", ONNX)
    bibliotheques = []
    with zipfile.ZipFile(ONNX) as archive:
        classes = os.path.join(TRAVAIL, "onnx-classes.jar")
        with open(classes, "wb") as f:
            f.write(archive.read("classes.jar"))
        for nom in archive.namelist():
            morceaux = nom.split("/")
            if len(morceaux) == 3 and morceaux[0] == "jni" and morceaux[1] in PROCESSEURS and nom.endswith(".so"):
                bibliotheques.append((f"lib/{morceaux[1]}/{morceaux[2]}", archive.read(nom)))
    if len(bibliotheques) < 2 * len(PROCESSEURS):
        sys.exit("ONNX Runtime : bibliothèques introuvables dans " + ONNX)
    return classes, bibliotheques


def lancer(*commande):
    resultat = subprocess.run(list(commande), env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sortie = (resultat.stdout + resultat.stderr).strip()
    if resultat.returncode:
        sys.exit(f"ÉCHEC : {os.path.basename(commande[0])}\n{sortie}")
    return sortie


def png(pixels):
    """Une image PNG (avec transparence) à partir d'un tableau numpy (hauteur, largeur, 4)."""
    hauteur, largeur = pixels.shape[:2]
    lignes = b"".join(b"\x00" + pixels[i].tobytes() for i in range(hauteur))

    def bloc(nom, donnees):
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(lignes, 9)) + bloc(b"IEND", b""))


def main():
    with open(os.path.join(ICI, "version.json"), encoding="utf-8") as f:
        version = json.load(f)
    code, nom = str(int(version["code"])), str(version["nom"])
    shutil.rmtree(TRAVAIL, ignore_errors=True)
    os.makedirs(TRAVAIL)

    # 1. Les ressources (avec l'icône, dessinée ici) et le manifeste
    res = os.path.join(TRAVAIL, "res")
    shutil.copytree(os.path.join(ICI, "res"), res)
    import dessin                                     # le réacteur dessiné (android\dessin.py)
    os.makedirs(os.path.join(res, "mipmap-xxxhdpi"))
    with open(os.path.join(res, "mipmap-xxxhdpi", "ic_avant.png"), "wb") as f:
        f.write(png(dessin.octets(dessin.reacteur(432, 0.6))))     # tient dans la zone toujours visible de l'icône
    with open(os.path.join(res, "mipmap-xxxhdpi", "ic_fond.png"), "wb") as f:
        f.write(png(dessin.octets(dessin.fond_icone(432))))
    with open(os.path.join(res, "mipmap-xxxhdpi", "ic_launcher.png"), "wb") as f:
        f.write(png(dessin.octets(dessin.reacteur(192, 0.82, "disque"))))
    os.makedirs(os.path.join(res, "drawable-nodpi"))
    with open(os.path.join(res, "drawable-nodpi", "widget_rond.png"), "wb") as f:
        f.write(png(dessin.octets(dessin.reacteur(512, 0.82, "disque"))))
    with open(os.path.join(ICI, "AndroidManifest.xml"), encoding="utf-8") as f:
        manifeste = f.read().replace("@CODE@", code).replace("@NOM@", nom)
    chemin_manifeste = os.path.join(TRAVAIL, "AndroidManifest.xml")
    with open(chemin_manifeste, "w", encoding="utf-8") as f:
        f.write(manifeste)
    aapt2 = os.path.join(OUTILS_SDK, "aapt2.exe")
    lancer(aapt2, "compile", "--dir", res, "-o", os.path.join(TRAVAIL, "res.zip"))
    lancer(aapt2, "link", "-o", os.path.join(TRAVAIL, "base.apk"), "-I", ANDROID, "--manifest", chemin_manifeste,
           "--java", os.path.join(TRAVAIL, "gen"), "--min-sdk-version", MIN_SDK, "--target-sdk-version", CIBLE_SDK,
           "--version-code", code, "--version-name", nom, os.path.join(TRAVAIL, "res.zip"))

    # 2. Le code
    sources = glob.glob(os.path.join(ICI, "src", "**", "*.java"), recursive=True) \
        + glob.glob(os.path.join(TRAVAIL, "gen", "**", "*.java"), recursive=True)
    classes = os.path.join(TRAVAIL, "classes")
    os.makedirs(classes)
    onnx_classes, bibliotheques = moteur_onnx()
    avis = lancer(os.path.join(JDK, "bin", "javac.exe"), "-encoding", "UTF-8", "-source", "11", "-target", "11",
                  "-Xlint:-options", "-classpath", ANDROID + os.pathsep + onnx_classes, "-d", classes, *sources)
    if avis:
        print(avis)
    lancer(os.path.join(JDK, "bin", "jar.exe"), "cf", os.path.join(TRAVAIL, "classes.jar"), "-C", classes, ".")
    lancer(os.path.join(OUTILS_SDK, "d8.bat"), "--release", "--lib", ANDROID, "--min-api", MIN_SDK,
           "--output", TRAVAIL, os.path.join(TRAVAIL, "classes.jar"), onnx_classes)

    # 3. L'assemblage : les ressources telles qu'aapt2 les a rangées, plus le code
    brut = os.path.join(TRAVAIL, "brut.apk")
    with zipfile.ZipFile(os.path.join(TRAVAIL, "base.apk")) as entree, zipfile.ZipFile(brut, "w") as sortie:
        for element in entree.infolist():
            sortie.writestr(element, entree.read(element.filename), compress_type=element.compress_type)
        sortie.write(os.path.join(TRAVAIL, "classes.dex"), "classes.dex", compress_type=zipfile.ZIP_DEFLATED)
        for place, octets in bibliotheques:           # compressées : Android les déballe à l'installation
            sortie.writestr(place, octets, compress_type=zipfile.ZIP_DEFLATED)
    aligne = os.path.join(TRAVAIL, "aligne.apk")
    lancer(os.path.join(OUTILS_SDK, "zipalign.exe"), "-f", "-p", "4", brut, aligne)

    # 4. La signature (créée une fois, gardée sur ce PC)
    os.makedirs(SIGNATURE, exist_ok=True)
    coffre, passe = os.path.join(SIGNATURE, "jarvis.jks"), os.path.join(SIGNATURE, "passe.txt")
    if not os.path.exists(coffre):
        with open(passe, "w", encoding="ascii") as f:
            f.write(secrets.token_urlsafe(24))
        with open(passe, encoding="ascii") as f:
            mot = f.read().split()[0]
        lancer(os.path.join(JDK, "bin", "keytool.exe"), "-genkeypair", "-keystore", coffre, "-alias", "jarvis",
               "-keyalg", "RSA", "-keysize", "2048", "-validity", "20000", "-storepass", mot, "-keypass", mot,
               "-dname", "CN=Jarvis")
        print("Signature créée dans", SIGNATURE, ": à garder précieusement (sans elle, plus de mise à jour possible).")
    with open(passe, encoding="ascii") as f:
        mot = f.read().split()[0]
    with open(passe, "w", encoding="ascii") as f:     # deux lignes : apksigner lit le mot de passe du coffre, puis celui de la clé
        f.write(mot + "\n" + mot + "\n")
    signeur = os.path.join(OUTILS_SDK, "apksigner.bat")
    lancer(signeur, "sign", "--ks", coffre, "--ks-key-alias", "jarvis", "--ks-pass", "file:" + passe,
           "--key-pass", "file:" + passe, "--out", SORTIE, aligne)
    print(lancer(signeur, "verify", "--verbose", "--min-sdk-version", MIN_SDK, SORTIE).splitlines()[0])
    for reste in glob.glob(SORTIE + ".idsig"):
        os.remove(reste)
    with open(os.path.join(ICI, "Jarvis-tablette.json"), "w", encoding="utf-8") as f:
        json.dump({"code": int(code), "nom": nom}, f)
    if "--publier" in sys.argv:                       # la copie publiée avec Jarvis, que les autres PC proposent à leurs tablettes
        docs = os.path.join(JARVIS, "docs")
        shutil.copy2(SORTIE, os.path.join(docs, "Jarvis-tablette.apk"))
        shutil.copy2(os.path.join(ICI, "Jarvis-tablette.json"), os.path.join(docs, "Jarvis-tablette.json"))
        print("Copiée dans docs\\ pour la publication.")
    print(f"Application fabriquée : {SORTIE} (version {nom}, n° {code}, {os.path.getsize(SORTIE) // 1024} Ko)")


if __name__ == "__main__":
    main()
