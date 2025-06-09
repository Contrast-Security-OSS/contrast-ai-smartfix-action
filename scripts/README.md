# Scripts for Contrast AI SmartFix

This directory contains utility scripts for the Contrast AI SmartFix action.

## generate_lockfile.py

This script generates a `requirements.lock` file from the `requirements.txt` using `uv`. The lockfile ensures all dependencies, including transitive ones, are properly tracked and pinned to specific versions.

### Usage

```bash
python scripts/generate_lockfile.py
```

This will create a `requirements.lock` file in the `src` directory that contains all direct and transitive dependencies with pinned versions.

### Why Use Lockfiles?

Lockfiles help prevent issues related to transitive dependencies by:

1. Pinning all dependency versions explicitly
2. Including all transitive (indirect) dependencies 
3. Ensuring consistent installations across different environments
4. Preventing "works on my machine" issues

The GitHub Action is configured to use this lockfile when installing dependencies, falling back to `requirements.txt` if the lockfile is not available.
