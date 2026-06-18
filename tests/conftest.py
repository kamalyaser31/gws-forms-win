# conftest.py — shared pytest configuration for gws-forms-win tests
import os
import sys

# Ensure scripts/ is importable from any test file
SKILL_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SKILL_SCRIPTS))
