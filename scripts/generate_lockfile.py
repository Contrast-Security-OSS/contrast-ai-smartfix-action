#!/usr/bin/env python3
"""
Script to generate a requirements.lock file using uv.
This ensures all dependencies, including transitive ones, are properly pinned.
"""

import os
import subprocess
import sys
import tempfile
import venv

def generate_lockfile():
    """Generate a lockfile from requirements.txt using uv."""
    # Define paths
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(current_dir, 'src')
    requirements_txt = os.path.join(src_dir, 'requirements.txt')
    requirements_lock = os.path.join(src_dir, 'requirements.lock')
    
    # Check if requirements.txt exists
    if not os.path.exists(requirements_txt):
        print(f"Error: requirements.txt not found at {requirements_txt}")
        sys.exit(1)
    
    # First, try to use python3.9 with corrected --output-file parameter
    try:
        print("Trying with python3.9...")
        subprocess.run(
            ["python3.9", "-m", "pip", "install", "--upgrade", "uv", "--user"],
            check=True
        )
        print("Running uv with python3.9...")
        subprocess.run(
            ["python3.9", "-m", "uv", "pip", "compile", 
             requirements_txt, "--output-file", requirements_lock,
             "--native-tls", "--system"],  # Add native-tls and system flags
            check=True
        )
        print(f"Lockfile generated successfully at {requirements_lock}")
        return
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Failed with python3.9: {e}")
    
    # If Python3.9 fails, create a virtual environment and try there
    print("Creating a temporary virtual environment...")
    try:
        # Create a temporary directory for the venv
        with tempfile.TemporaryDirectory() as tempdir:
            venv_dir = os.path.join(tempdir, "venv")
            
            # Create a virtual environment
            venv.create(venv_dir, with_pip=True)
            
            # Get the path to the Python executable in the virtual environment
            if os.name == 'nt':  # Windows
                venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
                venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
            else:  # Unix/Linux/Mac
                venv_python = os.path.join(venv_dir, "bin", "python")
                venv_pip = os.path.join(venv_dir, "bin", "pip")
            
            # Install uv in the virtual environment
            print(f"Installing uv in virtual environment...")
            subprocess.run(
                [venv_pip, "install", "uv"],
                check=True
            )
            
            # Use uv to generate the lockfile
            print(f"Generating lockfile with uv in virtual environment...")
            subprocess.run(
                [venv_python, "-m", "uv", "pip", "compile", 
                 requirements_txt, "--output-file", requirements_lock,
                 "--native-tls", "--system"],  # Add native-tls and system flags
                check=True
            )
            
            print(f"Lockfile generated successfully at {requirements_lock}")
            return
    except subprocess.CalledProcessError as e:
        print(f"Failed with virtual environment: {e}")
    
    # If all methods fail
    print("Failed to generate lockfile using uv.")
    sys.exit(1)

if __name__ == "__main__":
    generate_lockfile()
