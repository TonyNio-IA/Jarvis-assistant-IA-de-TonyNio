# -*- coding: utf-8 -*-
"""
Le dessin du réacteur de Jarvis pour l'icône de l'application et le widget de l'écran d'accueil (numpy seul).

Du centre vers le bord : un cœur lumineux, un anneau en pointillés, un anneau turquoise, trois arcs roses qui virent
au violet, une couronne de graduations, un anneau fin, le tout dans un halo. Dessiné deux fois plus grand puis réduit,
pour des bords nets.
"""
import numpy as np

TURQUOISE = np.array((79, 242, 220), dtype=np.float64) / 255
ROSE = np.array((255, 46, 151), dtype=np.float64) / 255
VIOLET = np.array((157, 77, 255), dtype=np.float64) / 255
BLANC = np.ones(3)


def _bande(u, centre, largeur):
    """1 sur l'anneau de rayon « centre » et de demi-largeur « largeur », 0 ailleurs, avec des bords doux."""
    x = np.clip(1 - np.abs(u - centre) / largeur, 0, 1)
    return x * x * (3 - 2 * x)


def _flou(image, sigma):
    """Flou gaussien (pour le halo), séparable : lignes puis colonnes."""
    rayon = int(3 * sigma)
    noyau = np.exp(-0.5 * (np.arange(-rayon, rayon + 1) / sigma) ** 2)
    noyau /= noyau.sum()
    sortie = np.empty_like(image)
    for c in range(image.shape[2]):
        couche = np.apply_along_axis(lambda v: np.convolve(v, noyau, mode="same"), 0, image[:, :, c])
        sortie[:, :, c] = np.apply_along_axis(lambda v: np.convolve(v, noyau, mode="same"), 1, couche)
    return sortie


def reacteur(taille, echelle=1.0, fond="aucun"):
    """Image RGBA (valeurs de 0 à 1) du réacteur.
    echelle : rayon du réacteur par rapport à la moitié de l'image ; fond : « aucun » (transparent), « disque »
    (disque sombre, transparent autour) ou « carre » (toute l'image sombre)."""
    grand = taille * 2
    y, x = np.mgrid[0:grand, 0:grand]
    dx, dy = x - grand / 2 + 0.5, y - grand / 2 + 0.5
    r = np.hypot(dx, dy) / (grand / 2)                     # 0 au centre, 1 au bord de l'image
    u = r / echelle                                        # 0 au centre, 1 au bord du réacteur
    angle = (np.degrees(np.arctan2(dx, -dy)) + 360) % 360  # 0 en haut, dans le sens des aiguilles d'une montre

    lumiere = np.zeros((grand, grand, 3))

    def ajouter(force, couleur):
        lumiere[:] += force[..., None] * couleur

    ajouter(0.95 * _bande(u, 0.955, 0.016), TURQUOISE)                                   # anneau fin du bord
    graduation = (np.abs(((angle + 3) % 6) - 3) < 0.9).astype(float)                     # 60 graduations
    grande = (np.abs(((angle + 15) % 30) - 15) < 1.3).astype(float)                      # 12 plus longues
    ajouter(0.45 * graduation * _bande(u, 0.855, 0.03), BLANC)
    ajouter(0.8 * grande * _bande(u, 0.835, 0.055), BLANC)
    arcs = np.zeros_like(u)                                                              # trois arcs, du rose au violet
    for debut in (20, 140, 260):
        dans = ((angle - debut) % 360) < 85
        arcs = np.maximum(arcs, dans * np.clip(np.minimum((angle - debut) % 360, 85 - (angle - debut) % 360) / 4, 0, 1))
    teinte = (((angle - 20) % 120) / 85).clip(0, 1)[..., None]
    lumiere[:] += (arcs * _bande(u, 0.72, 0.045))[..., None] * (ROSE * (1 - teinte) + VIOLET * teinte)
    ajouter(1.0 * _bande(u, 0.6, 0.022), TURQUOISE)                                      # anneau turquoise
    pointilles = (np.abs(((angle + 5) % 10) - 5) < 2.6).astype(float)
    ajouter(0.55 * pointilles * _bande(u, 0.47, 0.012), TURQUOISE)                       # anneau en pointillés
    coeur = np.clip(1 - u / 0.3, 0, 1) ** 2
    ajouter(0.9 * coeur, TURQUOISE)
    ajouter(np.clip(1 - u / 0.11, 0, 1) ** 1.5, BLANC)                                   # le cœur, presque blanc
    lumiere = np.clip(lumiere, 0, 1)
    lumiere = np.clip(lumiere + 0.9 * _flou(lumiere, grand * 0.018), 0, 1)              # le halo

    if fond == "aucun":
        alpha = lumiere.max(axis=2)
        couleur = lumiere / np.maximum(alpha, 1e-6)[..., None]
    else:
        degrade = np.clip(r / (0.98 if fond == "disque" else 1.42), 0, 1)[..., None]   # bleu nuit au centre, noir au bord
        sombre = np.array((16, 32, 52)) / 255 * (1 - degrade) + np.array((4, 7, 11)) / 255 * degrade
        sombre = sombre + (np.clip(1 - np.hypot(dx, dy - grand * 0.35) / (grand * 0.5), 0, 1) ** 2)[..., None] \
            * (VIOLET * 0.12)                                                             # une lueur violette en bas
        couleur = 1 - (1 - sombre) * (1 - lumiere)                                       # la lumière éclaire le fond
        if fond == "disque":
            alpha = np.clip((1 - r) * grand / 2, 0, 1)
            couleur = couleur + (_bande(r, 0.975, 0.02)[..., None] * 0.35) * TURQUOISE    # liseré du disque
        else:
            alpha = np.ones_like(r)
    image = np.concatenate((np.clip(couleur, 0, 1), alpha[..., None]), axis=2)
    # réduction 2 × 2 en tenant compte de la transparence (sinon les bords noircissent)
    a = image[..., 3:4]
    premult = np.concatenate((image[..., :3] * a, a), axis=2)
    petit = premult.reshape(taille, 2, taille, 2, 4).mean(axis=(1, 3))
    petit[..., :3] /= np.maximum(petit[..., 3:4], 1e-6)
    return np.clip(petit, 0, 1)


def fond_icone(taille):
    """Le fond de l'icône adaptative : bleu nuit au centre, noir sur les bords, avec une lueur violette."""
    y, x = np.mgrid[0:taille, 0:taille]
    dx, dy = x - taille / 2 + 0.5, y - taille / 2 + 0.5
    degrade = np.clip(np.hypot(dx, dy) / (taille * 0.7), 0, 1)[..., None]
    couleur = np.array((18, 34, 56)) / 255 * (1 - degrade) + np.array((4, 7, 11)) / 255 * degrade
    couleur = couleur + (np.clip(1 - np.hypot(dx, dy - taille * 0.32) / (taille * 0.55), 0, 1) ** 2)[..., None] * (VIOLET * 0.14)
    return np.concatenate((np.clip(couleur, 0, 1), np.ones((taille, taille, 1))), axis=2)


def octets(image):
    """Image RGBA (0 à 1) vers un tableau d'octets pour le PNG."""
    return (np.clip(image, 0, 1) * 255 + 0.5).astype(np.uint8)
