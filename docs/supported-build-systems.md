# Supported Build Systems

SmartFix can automatically detect and run build/test commands for the following build systems.

## Build System Detection

SmartFix detects build systems by looking for marker files in your project:

### Maven (Java)
**Marker File:** `pom.xml`

**Detected Commands (in priority order):**
- `mvn test`
- `mvn verify`
- `mvn clean install`

**Monorepo Support:**
- Uses `-f` flag: `mvn -f path/to/pom.xml test`

### Gradle (Java/Kotlin)
**Marker Files:** `build.gradle` or `build.gradle.kts`

**Detected Commands:**
- `./gradlew test` (if `gradlew` wrapper exists)
- `./gradlew build`
- `./gradlew check`
- `gradle test` (fallback if no wrapper)

**Monorepo Support:**
- Uses `-p` flag: `./gradlew -p path/to/subdir test`

### Python
**Marker Files:** `pytest.ini`, `setup.py`, or `pyproject.toml`

**Detected Commands:**
- `pytest`
- `python -m pytest`
- `python setup.py test`

### Node.js / JavaScript / TypeScript
**Marker File:** `package.json`

**Detected Commands:**
- `npm test`
- `npm run build`
- `npm run test`

**Monorepo Support:**
- Uses `--prefix` flag: `npm --prefix path/to/subdir test`

### PHP
**Marker File:** `composer.json`

**Detected Commands:**
- `composer test`
- `phpunit`
- `./vendor/bin/phpunit`

### .NET (C#/F#)
**Marker Files:** `*.sln` or `*.csproj`

**Detected Commands:**
- `dotnet test`
- `dotnet build`

### Makefile
**Marker File:** `Makefile`

**Detected Commands:**
- `make test` (if `test` target exists)
- `make check` (if `check` target exists)
- `make build` (if `build` target exists)
- `make all` (if `all` target exists)

**Note:** SmartFix prioritizes test-related targets (`test`, `check`) over build targets.

## Format Command Detection

SmartFix can also auto-detect formatting commands:

### Python Formatters
**Marker Files:** `pyproject.toml` or `setup.py`

**Detected Commands:**
- `black .`
- `ruff format .`
- `autopep8 --in-place --recursive .`

### JavaScript/TypeScript Formatters
**Marker File:** `package.json`

**Detected Commands:**
- `prettier --write .`
- `npm run format`
- `yarn format`

### Java Formatters
**Marker File:** `pom.xml`

**Detected Commands:**
- `mvn spotless:apply`

### .NET Formatters
**Marker Files:** `*.sln` or `*.csproj`

**Detected Commands:**
- `dotnet format`
- `csharpier .`

### PHP Formatters
**Marker File:** `composer.json`

**Detected Commands:**
- `php-cs-fixer fix`
- `./vendor/bin/php-cs-fixer fix`

## Detection Priority

When multiple marker files are present, SmartFix generates candidates from all detected build systems and tests them in the order they appear. The first command that:
1. Passes security validation (allowlist check)
2. Exists on the system (tool is installed)

...will be used.

## Monorepo Support

SmartFix automatically adapts commands for monorepo structures by:
- **Maven**: Using `-f path/to/pom.xml` instead of `cd`
- **Gradle**: Using `-p path/to/subdir` instead of `cd`
- **npm**: Using `--prefix path/to/subdir` instead of `cd`

This ensures commands run from the repository root while targeting the correct subdirectory.

## Package Manager Detection

For Node.js projects, SmartFix detects the package manager by checking for lock files:

| Lock File | Package Manager |
|-----------|----------------|
| `package-lock.json` | npm |
| `yarn.lock` | yarn |
| `pnpm-lock.yaml` | pnpm |
| `bun.lockb` | bun |

If only `package.json` exists with no lock file, defaults to `npm`.

## Security

All detected commands are validated against a security allowlist before execution. Commands must:
- Start with an approved tool name
- Not contain dangerous patterns (command injection, shell execution, etc.)
- Pass validation checks

See [Command Validation](./command-validation.md) for details.

## Manual Override

If auto-detection doesn't work for your project, you can always manually set:

```yaml
env:
  BUILD_COMMAND: "your custom build command"
  FORMATTING_COMMAND: "your custom format command"  # optional
```

See [Troubleshooting](./troubleshooting-command-detection.md) for common issues and solutions.
