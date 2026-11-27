# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"C:\Jarvis")
import jarvis_pratique as P
for t in ["deux mille", "deux mille trente", "deux mille vingt-huit", "deux mille vingt huit", "deux mille un", "mille neuf cent quatre-vingt-dix",
          "dix-neuf cent quatre-vingt-dix", "mille neuf cent quatre vingt dix neuf", "deux mille vingt-six"]:
    m = P._decouper(t)
    print(t, "->", P._lire_nombre(m, 0), len(m))
