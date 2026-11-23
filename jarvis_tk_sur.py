# -*- coding: utf-8 -*-
"""Tk et les fils : une image ou une variable Tk ne doit être libérée que par le fil qui l'a créée.

Les fenêtres de Jarvis (réglages, rapports, QR...) tournent chacune dans leur propre fil. Quand le ramasse-miettes
de Python, lancé depuis un AUTRE fil (le réacteur, par exemple), libère une image ou une variable de cette
fenêtre, Tk doit réveiller le fil de la fenêtre pour exécuter la suppression et attend sa réponse : si ce fil est
occupé ou déjà terminé, ça bloque (ou ça affiche « main thread is not in main loop »). C'est ce qui pouvait figer la
fenêtre des réglages, voire Jarvis, qu'il fallait alors relancer.

Ici, une image ou une variable libérée depuis un autre fil est simplement laissée telle quelle (quelques octets,
nettoyés avec la fenêtre) ; libérée depuis son propre fil, rien ne change.
"""
import threading


def securiser():
    try:
        import tkinter
    except Exception:
        return
    if getattr(tkinter, "_jarvis_fils_surs", False):
        return
    tkinter._jarvis_fils_surs = True
    for classe in (tkinter.Image, tkinter.Variable):
        init_origine = classe.__init__
        suppr_origine = getattr(classe, "__del__", None)
        if suppr_origine is None:
            continue

        def init(self, *a, _o=init_origine, **k):
            self._jarvis_fil = threading.get_ident()
            _o(self, *a, **k)

        def suppr(self, _o=suppr_origine):
            fil = getattr(self, "_jarvis_fil", None)
            if fil is not None and fil != threading.get_ident():
                return                      # pas depuis ce fil : on ne réveille pas le fil de la fenêtre
            _o(self)

        classe.__init__ = init
        classe.__del__ = suppr


securiser()
