# Contrast Resolve Action Dev

This repository contains the source code for the Contrast Resolve Action.

## Local Development and Testing

To set up this project for local development and run tests, follow these steps:

1.  **Navigate to your project directory:**
    Replace `/path/to/your/project` with the actual path to where you cloned this repository.
    ```bash
    cd /path/to/your/project
    ```

2.  **Create a Python virtual environment:**
    This helps manage project-specific dependencies.
    ```bash
    python3 -m venv .venv
    ```

3.  **Activate the virtual environment:**
    On macOS and Linux:
    ```bash
    source .venv/bin/activate
    ```
    On Windows (Git Bash or WSL):
    ```bash
    source .venv/Scripts/activate 
    ```
    Or (Command Prompt/PowerShell):
    ```bash
    .venv\Scripts\activate.bat
    ```
    Your terminal prompt should change to indicate the active virtual environment.

4.  **Install dependencies:**
    This will install all the necessary Python packages listed in `requirements.txt`.
    ```bash
    pip install -r requirements.txt
    ```

5.  **Run tests:**
    This command will discover and run all tests (files named `test_*.py`) in the project.
    ```bash
    python -m unittest discover -s . -p "test_*.py"
    ```

When you are finished working, you can deactivate the virtual environment by simply running:
```bash
deactivate
```

## Version Checking

This action includes a feature to notify users if a new version is available. The current version of the action is stored in the `VERSION` file.

## Contributing

[Details on contributing to this project will be added here.]

## License

[License information will be added here.]
