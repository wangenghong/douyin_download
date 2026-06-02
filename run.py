# -*- coding: utf-8 -*-
"""Douyin crawler launcher."""

import subprocess
import sys
from pathlib import Path

project_dir = Path(__file__).parent
result = subprocess.run(
    [sys.executable, "-m", "src.douyin_crawler"],
    cwd=str(project_dir))
sys.exit(result.returncode)
