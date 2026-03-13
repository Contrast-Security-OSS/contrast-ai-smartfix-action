# Supported Build Systems

SmartFix can automatically detect and run build/test commands.

## How Command Detection Works

SmartFix uses **deterministic file-based detection** to find build and format commands:

### Detection Process
SmartFix looks for marker files (e.g., `pom.xml`, `package.json`) and generates a prioritized list of common commands for detected build systems. Each candidate command is:
1. Quickly filtered by checking if the tool exists (`mvn --version`, etc.) — skipped if tool not installed
2. Validated against the security allowlist
3. The first command that passes both checks is selected

The Fix agent then uses the BuildTool to actually execute the command and verify it works.

### When Detection is Skipped

Build command detection is **automatically skipped** when:
- `RUN_TASK` is set to `merge` (merge workflows don't need builds)
- `CODING_AGENT` is not `SMARTFIX` (other agents handle their own builds)
- `BUILD_COMMAND` is manually provided (respects user override)

In these cases, SmartFix uses the provided command or skips build validation entirely.

### Security Validation

**Auto-detected** commands must pass **security validation** against an allowlist of approved executables and patterns.

**Manually specified commands** (via `BUILD_COMMAND` or `FORMATTING_COMMAND` inputs) are **trusted as safe** and skip validation since they come from humans who control the GitHub Actions workflow configuration.

See [Command Validation](./command-validation.md) for security details.

**See the [full list of allowed executables](../src/smartfix/config/command_validator.py#L38-L74) in the validator source code.**

## Build System Detection

SmartFix detects build systems by looking for marker files in your project:

### Maven (Java)
**Marker File:** `pom.xml`

**Auto-Detected Commands (in priority order):**
- `mvn test`
- `mvn verify`
- `mvn clean install`

**Also on allowlist:** `mvn` (any Maven goal), `mvnw` (Maven wrapper), `ant`, `sbt`, `junit`, `testng`

### Gradle (Java/Kotlin)
**Marker Files:** `build.gradle` or `build.gradle.kts`

**Auto-Detected Commands:**
- `./gradlew test` (if `gradlew` wrapper exists)
- `./gradlew build`
- `./gradlew check`
- `gradle test` (fallback if no wrapper)

**Also on allowlist:** `gradlew`, `gradle` (any Gradle task), `ant`, `sbt`, Java test frameworks

### Python
**Marker Files:** `pytest.ini`, `setup.py`, or `pyproject.toml`

**Auto-Detected Commands:**
- `pytest`
- `python -m pytest`
- `python setup.py test`

**Also on allowlist:** `python`, `python3`, `nose2`, `unittest`, `coverage`, `poetry`, `pipenv`, `uv`, `tox`, `virtualenv`

### Node.js / JavaScript / TypeScript
**Marker File:** `package.json`

**Auto-Detected Commands:**
- `npm test`
- `npm run build`
- `npm run test`

**Also on allowlist:** `yarn`, `pnpm`, `bun`, `npx`, `node`, `jest`, `mocha`, `jasmine`, `karma`, `ava`, `vitest`, `nyc`

### PHP
**Marker File:** `composer.json`

**Auto-Detected Commands:**
- `composer test`
- `phpunit`
- `./vendor/bin/phpunit`

**Also on allowlist:** `php`, `pest`, `codeception`

### .NET (C#/F#)
**Marker Files:** `*.sln` or `*.csproj`

**Auto-Detected Commands:**
- `dotnet test`
- `dotnet build`

**Also on allowlist:** `dotnet` (any command), `msbuild`, `nuget`, `nunit-console`, `nunit3-console`, `xunit.console`, `vstest.console`, `mstest`

### Makefile
**Marker File:** `Makefile`

**Auto-Detected Commands:**
- `make test` (if `test` target exists)
- `make check` (if `check` target exists)
- `make build` (if `build` target exists)
- `make all` (if `all` target exists)

**Also on allowlist:** `make` (any target), `cmake`, `ninja`, `bazel`, `ctest`

**Note:** SmartFix prioritizes test-related targets (`test`, `check`) over build targets.

## Format Command Detection

SmartFix can also auto-detect formatting commands:

### Python Formatters
**Marker Files:** `pyproject.toml` or `setup.py`

**Auto-Detected Commands:**
- `black .`
- `ruff format .`
- `autopep8 --in-place --recursive .`

**Also on allowlist:** `black`, `ruff`, `autopep8`, `yapf`, `isort`, `flake8`, `pylint`

### JavaScript/TypeScript Formatters
**Marker File:** `package.json`

**Auto-Detected Commands:**
- `prettier --write .`
- `npm run format`
- `yarn format`

**Also on allowlist:** `prettier`, `eslint`, `standard`, package manager commands (`npm`, `yarn`, `pnpm`, `bun`)

### Java Formatters
**Marker File:** `pom.xml`

**Auto-Detected Commands:**
- `mvn spotless:apply`

**Also on allowlist:** `google-java-format`, `checkstyle`, `clang-format`

### .NET Formatters
**Marker Files:** `*.sln` or `*.csproj`

**Auto-Detected Commands:**
- `dotnet format`
- `csharpier .`

**Also on allowlist:** `dotnet`, `csharpier`, `clang-format`

### PHP Formatters
**Marker File:** `composer.json`

**Auto-Detected Commands:**
- `php-cs-fixer fix`
- `./vendor/bin/php-cs-fixer fix`

**Also on allowlist:** `php-cs-fixer`, `phpcbf`

## Detection Priority

When multiple marker files are present, SmartFix generates candidates from all detected build systems and tests them in priority order. The first command that:
1. Has the tool installed on the system (quick `--version` check — just a pre-filter to skip tools that aren't installed)
2. Passes security validation (allowlist check)

...is selected as the detected command. The Fix agent's BuildTool handles actual execution and verification.

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

All auto-detected commands are validated against a security allowlist before execution. Commands must:
- Start with an approved tool name from the [validated executables list](../src/smartfix/config/command_validator.py#L38-L74)
- Not contain dangerous patterns (command substitution, shell injection, etc.)
- Not use dangerous interpreter flags (`python -c`, `node -e`, etc.)
- Pass all validation checks for operators, redirects, and complexity limits

**Key security features:**
- Allowlist-only approach: Only explicitly approved executables are permitted
- Pattern blocking: Blocks command injection patterns like `$()`, backticks, `eval`, etc.
- Interpreter protection: Prevents inline code execution via flags
- Python module validation: Only allowed modules can be used with `python -m`
- Redirect validation: File redirects must be to safe relative paths

See [Command Validation](./command-validation.md) for complete security details.

## Manual Override

If auto-detection doesn't work for your project, you can manually specify commands using environment variables. **Manually specified commands are trusted as safe and skip security validation** since they come from humans who control the GitHub Actions workflow configuration.

```yaml
env:
  BUILD_COMMAND: "your custom build command"
  FORMATTING_COMMAND: "your custom format command"  # optional
```

**Examples:**
- Maven with specific profile: `BUILD_COMMAND: "mvn test -P ci"`
- Yarn workspaces: `BUILD_COMMAND: "yarn workspace @my/package test"`
- Poetry with pytest: `BUILD_COMMAND: "poetry run pytest -v"`
- Custom make target: `BUILD_COMMAND: "make integration-test"`

You can use any command you want in manual overrides - there are no restrictions since you control the workflow configuration.
