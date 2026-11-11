"""python -m il2cpp <game-dir|metadata> -o <outdir>"""
import sys

from il2cpp.cli import main

sys.exit(main(sys.argv))
