#!/usr/bin/env python3
"""Skill-local entry point for one result: filtered official notices."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[3] / "scripts" / "yonsei_notices.py"
sys.argv = [str(RUNTIME), "search", *sys.argv[1:]]
runpy.run_path(str(RUNTIME), run_name="__main__")
