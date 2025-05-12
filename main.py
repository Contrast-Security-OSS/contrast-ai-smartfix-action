import os
# Import the function from version_check.py
from version_check import do_version_check
# Import the function from config_check.py
from config_check import check_config

def main():
    print("Hello, World!")
    config = check_config()
    # Potentially use config values later
    do_version_check()

if __name__ == "__main__":
    main()