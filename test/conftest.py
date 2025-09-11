"""Test configuration and setup for pytest.

This file is automatically loaded by pytest and sets up the Python path
so that all test files can import from src without path manipulation.
"""

import sys
from pathlib import Path

# Add the project root to Python path so that 'src' imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add test directory to path for test helpers
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))
