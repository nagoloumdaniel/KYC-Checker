import os
import sys

# Garantit que le package `kyc` est importable quand on lance pytest
# depuis la racine du projet.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
