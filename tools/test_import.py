import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # il2csharp/ project root after 2026-09-08 consolidation
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'work'))
import il2cpp as il2csharp
print('ok')