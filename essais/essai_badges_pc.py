"""Dessine hors Ã©cran la pastille Â« micro coupÃ© Â» et le bandeau de rappel du rÃ©acteur PC, pour vÃ©rifier qu'ils
ne plantent pas, et enregistre le rÃ©sultat dans tests/sortie/pc_badges.png."""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame  # noqa: E402

pygame.init()
import jarvis_affichage as a  # noqa: E402

faux = types.SimpleNamespace(fond=(5, 9, 14), s=1.5, src=types.SimpleNamespace(texte_actuel="Rappel : sortir le gÃ¢teau du four, il est prÃªt depuis cinq minutes"),
                             police_titre=pygame.font.SysFont("segoeui", 20, bold=True))
faux._texte = lambda police, texte, couleur: police.render(texte, True, couleur)
surf = pygame.Surface((400, 300))
surf.fill((5, 9, 14))


def teinte(f, vers=None):
    c = vers or (255, 46, 151)
    return tuple(int(5 + (c[i] - 5) * max(0, min(1, f))) for i in range(3))


classe = next(v for v in vars(a).values() if isinstance(v, type) and hasattr(v, "_badge_micro"))
classe._badge_micro(faux, surf, teinte, (255, 200, 230), 300, 80, 24)
classe._bandeau_rappel(faux, surf, teinte, (255, 200, 230), 200, 200, 300)
pygame.image.save(surf, os.path.join(os.path.dirname(__file__), "sortie", "pc_badges.png"))
print("ok", classe.__name__)
