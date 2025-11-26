"""Test environment helper utilities.

This module provides helper functions for test setup, including
temporary directory management.
"""

from pathlib import Path


def create_temp_repo_dir():
    """
    Create a temporary directory for repository testing.

    Returns:
        pathlib.Path: Path to temporary directory
    """
    import tempfile
    return Path(tempfile.mkdtemp())


def cleanup_temp_dir(temp_dir):
    """
    Clean up temporary directory.

    Args:
        temp_dir: Path to temporary directory to clean up
    """
    import shutil
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
