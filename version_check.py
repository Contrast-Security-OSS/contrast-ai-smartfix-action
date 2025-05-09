import os
import requests
from packaging.version import parse as parse_version

VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION")

def get_current_version_from_file():
    """Reads the current version string from the VERSION file."""
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: {VERSION_FILE} not found. Defaulting to 0.0.0")
        return "0.0.0"

def check_for_new_action_version():
    """
    Checks if a newer version of the action is available on GitHub.
    Prints a message if an update is found.
    """
    current_action_version_str = get_current_version_from_file()
    # Use the specific repository for this action
    repo_owner_slash_name = "Contrast-Security-OSS/contrast-resolve-action-dev"
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        api_url = f"https://api.github.com/repos/{repo_owner_slash_name}/tags"
        
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        tags_data = response.json()
        
        if not tags_data:
            return

        latest_tag_name = tags_data[0]['name']
        
        current_version = parse_version(current_action_version_str)
        latest_version = parse_version(latest_tag_name)
        
        if latest_version > current_version:
            print(f"INFO: A new version ({latest_tag_name}) of the '{repo_owner_slash_name}' action is available.")
            print(f"INFO: You are currently using version {current_action_version_str}.")
            print(f"INFO: Please consider updating your workflow to use '{repo_owner_slash_name}@{latest_tag_name}'.")

    except requests.exceptions.Timeout:
        print(f"Warning: Timeout while checking for new action version for '{repo_owner_slash_name}'.")
    except requests.exceptions.RequestException as e:
        status_code_info = f" Status: {e.response.status_code}" if e.response is not None else ""
        print(f"Warning: Could not check for new action version for '{repo_owner_slash_name}'.{status_code_info}")
    except Exception as e:
        print(f"Warning: An unexpected error occurred while checking for new action version: {e}")

if __name__ == "__main__": # pragma: no cover
    # This part is for standalone execution of this script, not typically used when imported.
    check_for_new_action_version()
