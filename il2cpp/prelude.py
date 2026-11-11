"""Shared stdlib / optional-disassembler imports for the il2cpp package.

Every module does `from il2cpp.prelude import *` so the third-party probe
(iced_x86, capstone) happens once and HAVE_ICED / HAVE_CAPSTONE stay
single-valued across the package.
"""
import math
import os
import re
import struct
import sys
from collections import Counter
from dataclasses import dataclass, field as dcfield
from typing import Dict, List, Optional, Set, Tuple

try:
    from iced_x86 import (Decoder, Formatter, FormatterSyntax, Mnemonic, OpKind,
                          Register as IReg, FlowControl, DecoderOptions, MemorySizeExt)
    HAVE_ICED = True
except ImportError:
    HAVE_ICED = False

try:
    from capstone import Cs as _ArmCs  # noqa: F401 (used lazily by Arm64Lifter)
    HAVE_CAPSTONE = True
except ImportError:
    HAVE_CAPSTONE = False
