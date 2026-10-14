import sys
import os

# Agrega la raíz del proyecto al path de Python
# Esto permite que todos los tests encuentren src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
