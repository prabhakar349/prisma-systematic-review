"""Shared sys.path setup so tests can import the plugin's scripts directly."""
import os
import sys

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "skills", "prisma-systematic-review", "scripts"
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))
