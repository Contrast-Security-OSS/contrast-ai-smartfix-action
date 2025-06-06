import os
import requests
from packaging.version import parse as parse_version

HEX_CHARS = "0123456789abcdef"

def get_latest_repo_version(repo_url: str):
    """Fetches the latest release tag from a GitHub repository."""
    try:
        # Clean the repo URL to avoid double https:// issues
        cleaned_repo_path = repo_url.replace('https://github.com/', '')
        if cleaned_repo_path == repo_url:
            # If no substitution happened, ensure we're using the correct format
            cleaned_repo_path = repo_url.replace('github.com/', '')
        
        # Construct the API URL for tags
        api_url = f"https://api.github.com/repos/{cleaned_repo_path}/tags"
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        tags = response.json()

        if not tags:
            return None

        valid_tags = []
        for tag in tags:
            try:
                version_str = tag['name']
                if version_str.startswith('v'):
                    version_str = version_str[1:]
                parse_version(version_str) # Check if it's a valid version
                valid_tags.append(tag['name'])
            except Exception:
                # Ignore tags that are not valid versions
                pass

        if not valid_tags:
            return None

        # Sort valid tags to find the latest
        valid_tags.sort(key=lambda v: parse_version(v.lstrip('v')), reverse=True)
        return valid_tags[0]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tags: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching tags: {e}")
        return None

def check_for_newer_version(current_version_str: str, latest_version_str: str):
    """Compares the current version with the latest version.
    Returns the latest_version_str if it's newer, otherwise None.
    """
    original_latest_version_str = latest_version_str # Store the original

    # Normalize versions for comparison by removing 'v' prefix
    current_comp_ver = current_version_str
    if current_comp_ver.startswith('v'):
        current_comp_ver = current_comp_ver[1:]

    latest_comp_ver = latest_version_str
    if latest_comp_ver.startswith('v'):
        latest_comp_ver = latest_comp_ver[1:]

    try:
        current_v = parse_version(current_comp_ver)
        latest_v = parse_version(latest_comp_ver)

        if latest_v > current_v:
            return original_latest_version_str # Return the original string
        return None
    except Exception as e:
        print(f"Error parsing versions for comparison: {current_version_str}, {latest_version_str} - {e}")
        return None

ACTION_REPO_URL = "https://github.com/Contrast-Security-OSS/contrast-ai-smartfix-action"

def do_version_check():
    """
    Orchestrates the version check:
    1. Gets the current action version from GITHUB_ACTION_REF.
    2. Fetches the latest version from the repository.
    3. Compares versions and prints a message if a newer version is available.
    """
    current_action_ref = os.environ.get("GITHUB_ACTION_REF")

    if not current_action_ref:
        print("Warning: GITHUB_ACTION_REF environment variable is not set. Version checking is skipped. This variable is automatically set by GitHub Actions. To enable version checking, ensure this script is running as part of a GitHub Action workflow.")
        return

    current_action_version = current_action_ref
    if current_action_ref.startswith('refs/tags/'):
        current_action_version = current_action_ref.split('/')[-1]
    
    if len(current_action_version) == 40 and all(c in HEX_CHARS for c in current_action_version.lower()):
        print(f"Running action from SHA: {current_action_version}. Skipping version comparison against tags.")
        return
    
    try:
        parsed_version_str_for_logging = current_action_version
        temp_version_to_parse = current_action_version
        if temp_version_to_parse.startswith('v'):
            temp_version_to_parse = temp_version_to_parse[1:]
        parse_version(temp_version_to_parse)
    except Exception:
        print(f"Warning: Could not parse current action version '{current_action_version}' from GITHUB_ACTION_REF '{current_action_ref}'. Skipping version check.")
        return

    print(f"Current action version (from GITHUB_ACTION_REF '{current_action_ref}'): {parsed_version_str_for_logging}")

    latest_repo_version = get_latest_repo_version(ACTION_REPO_URL)

    if latest_repo_version:
        print(f"Latest version available in repo: {latest_repo_version}")
        newer_version = check_for_newer_version(parsed_version_str_for_logging, latest_repo_version)
        if newer_version:
            print(f"INFO: A newer version of this action is available ({newer_version}).")
            print(f"INFO: You are running version {parsed_version_str_for_logging}.")
            print(f"INFO: Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-resolve-action-dev@{newer_version}")
    else:
        print("Could not determine the latest version from the repository.")
