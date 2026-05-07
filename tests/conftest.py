"""
Pytest configuration and fixtures for BGI tests.

Ensures that modules in the working directory (like lang_registry) are importable.
"""

import sys
from pathlib import Path

# Add the project root to sys.path so pytest can find bgi modules
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
