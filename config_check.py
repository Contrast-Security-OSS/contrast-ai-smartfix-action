import os
import sys
from message_prefixes import MessagePrefix # Added import

def check_config():
    """
    Checks the action configuration and sets defaults or exits if required fields are missing.
    """
    config = {}

    # Optional with defaults
    config['MAX_BUILD_ATTEMPTS'] = os.environ.get('INPUT_MAX_BUILD_ATTEMPTS', '6')
    config['MAX_OPEN_PRS'] = os.environ.get('INPUT_MAX_OPEN_PRS', '5')
    config['VERBOSE_LOGGING'] = os.environ.get('INPUT_VERBOSE_LOGGING', 'false').lower() == 'true'

    # Optional, no defaults
    config['BUILD_COMMAND'] = os.environ.get('INPUT_BUILD_COMMAND')
    config['FORMATTING_COMMAND'] = os.environ.get('INPUT_FORMATTING_COMMAND')
    config['AWS_SESSION_TOKEN'] = os.environ.get('INPUT_AWS_SESSION_TOKEN')

    # Required
    required_vars = [
        'GITHUB_TOKEN',
        'CONTRAST_HOST',
        'CONTRAST_ORG_ID',
        'CONTRAST_APP_ID',
        'CONTRAST_AUTHORIZATION_KEY',
        'CONTRAST_API_KEY',
        'AGENT_MODEL',
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'AWS_REGION',
        'BASE_BRANCH',
    ]

    missing_vars = []
    for var in required_vars:
        value = os.environ.get(f'INPUT_{var}')
        if not value:
            missing_vars.append(var)
        else:
            config[var] = value

    if missing_vars:
        # Updated error message prefix
        print(f"{MessagePrefix.CONFIG_INVALID.value}Missing required configuration variables: {', '.join(missing_vars)}")
        sys.exit(1)

    # Validate integer fields
    try:
        config['MAX_BUILD_ATTEMPTS'] = int(config['MAX_BUILD_ATTEMPTS'])
    except ValueError:
        # Updated error message prefix
        print(f"{MessagePrefix.CONFIG_INVALID.value}Invalid value for MAX_BUILD_ATTEMPTS. Must be an integer.")
        sys.exit(1)

    try:
        config['MAX_OPEN_PRS'] = int(config['MAX_OPEN_PRS'])
    except ValueError:
        # Updated error message prefix
        print(f"{MessagePrefix.CONFIG_INVALID.value}Invalid value for MAX_OPEN_PRS. Must be an integer.")
        sys.exit(1)

    if config['VERBOSE_LOGGING']:
        print(f"{MessagePrefix.INFO.value}Verbose logging enabled.") # Updated print prefix
        print(f"{MessagePrefix.INFO.value}Configuration:") # Updated print prefix
        for key, value in config.items():
            if '_KEY' in key or 'TOKEN' in key: # Mask sensitive values
                print(f"  {key}: ***")
            else:
                print(f"  {key}: {value}")
    
    return config

if __name__ == "__main__":
    check_config()
