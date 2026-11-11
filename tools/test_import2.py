import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # il2csharp/ project root after 2026-09-08 consolidation
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'work'))
from il2cpp import Decompiler
from il2cpp import Lifter
print('decompiler and lifter ok')