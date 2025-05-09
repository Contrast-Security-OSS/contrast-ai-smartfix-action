import os
import version_check # Import the new module

def main():
    version_check.check_for_new_action_version() # Call the version check

    current_version = version_check.get_current_version_from_file()
    print(f"Executing action: {os.environ.get('GITHUB_ACTION', 'unknown_action')} version {current_version}")
    print("Hello, World!")

if __name__ == "__main__":
    main()