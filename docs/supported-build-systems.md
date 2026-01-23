# Supported Build Systems

SmartFix can automatically detect and run build/test commands for the following build systems.

## How Command Detection Works

SmartFix uses a **three-phase detection approach** with automatic fallback:

### Phase 1: Deterministic Detection (Fast, File-Based)
SmartFix looks for marker files (e.g., `pom.xml`, `package.json`) and generates a prioritized list of common commands for detected build systems. Each candidate command is:
1. Quickly filtered by checking if the tool exists (`mvn --version`, etc.) - skipped if tool not installed
2. Validated against the security allowlist
3. **Actually executed** to verify it works in your project

The first command that successfully builds your project is used immediately.

### Phase 2: LLM-Based Detection (Iterative, Context-Aware)
If Phase 1 fails (no marker files, tools missing, or all builds fail), SmartFix uses an LLM agent to:
1. Analyze your project structure and any Phase 1 failure history
2. Suggest alternative commands from the validated ecosystem tools
3. Iterate up to 6 times with error feedback to find a working command

The LLM agent has access to failure messages and can adapt suggestions based on what didn't work.

### Phase 3: No-Op Fallback (Always Safe)
If both Phase 1 and Phase 2 fail, SmartFix uses a no-op command:
```bash
echo 'No build command detected - using no-op'
```

This ensures SmartFix never fails due to build detection issues—it gracefully degrades to skip build validation when necessary.

### When Detection is Skipped

Build command detection is **automatically skipped** when:
- `RUN_TASK` is set to `merge` (merge workflows don't need builds)
- `CODING_AGENT` is not `SMARTFIX` (other agents handle their own builds)
- `BUILD_COMMAND` is manually provided (respects user override)

In these cases, SmartFix uses the provided command or skips build validation entirely.

### Security Validation

**Auto-detected** (Phase 1) and **LLM-suggested** (Phase 2) commands must pass **security validation** against an allowlist of approved executables and patterns.

**Manually specified commands** (via `BUILD_COMMAND` or `FORMATTING_COMMAND` inputs) are **trusted as safe** and skip validation since they come from humans who control the GitHub Actions workflow configuration.

See [Command Validation](./command-validation.md) for security details.

### Auto-Detected vs. Validated Commands

- **Auto-Detected Commands** (Phase 1, listed below): Commands SmartFix will automatically try based on marker files
- **Validated Commands** (Phase 2, broader set): Ecosystem tools the LLM may suggest, all validated by the security allowlist

For example:
- Maven: Phase 1 tries `mvn test`, Phase 2 may suggest `mvn verify`, `mvn clean install`, `mvnw`, etc.
- Node.js: Phase 1 tries `npm test`, Phase 2 may suggest `yarn test`, `pnpm test`, `bun test`, `npx jest`, etc.
- Python: Phase 1 tries `pytest`, Phase 2 may suggest `python -m pytest`, `poetry run pytest`, `tox`, etc.

**See the [full list of allowed executables](../src/smartfix/config/command_validator.py#L38-L74) in the validator source code.**

## Build System Detection

SmartFix detects build systems by looking for marker files in your project:

### Maven (Java)
**Marker File:** `pom.xml`

**Auto-Detected Commands (in priority order):**
- `mvn test`
- `mvn verify`
- `mvn clean install`

**Also Validated:** `mvn` (any Maven goal), `mvnw` (Maven wrapper), `ant`, `sbt`, `junit`, `testng`

**Monorepo Support:**
- Uses `-f` flag: `mvn -f path/to/pom.xml test`

### Gradle (Java/Kotlin)
**Marker Files:** `build.gradle` or `build.gradle.kts`

**Auto-Detected Commands:**
- `./gradlew test` (if `gradlew` wrapper exists)
- `./gradlew build`
- `./gradlew check`
- `gradle test` (fallback if no wrapper)

**Also Validated:** `gradlew`, `gradle` (any Gradle task), `ant`, `sbt`, Java test frameworks

**Monorepo Support:**
- Uses `-p` flag: `./gradlew -p path/to/subdir test`

### Python
**Marker Files:** `pytest.ini`, `setup.py`, or `pyproject.toml`

**Auto-Detected Commands:**
- `pytest`
- `python -m pytest`
- `python setup.py test`

**Also Validated:** `python`, `python3`, `nose2`, `unittest`, `coverage`, `poetry`, `pipenv`, `uv`, `tox`, `virtualenv`

### Node.js / JavaScript / TypeScript
**Marker File:** `package.json`

**Auto-Detected Commands:**
- `npm test`
- `npm run build`
- `npm run test`

**Also Validated:** `yarn`, `pnpm`, `bun`, `npx`, `node`, `jest`, `mocha`, `jasmine`, `karma`, `ava`, `vitest`, `nyc`

**Monorepo Support:**
- Uses `--prefix` flag: `npm --prefix path/to/subdir test`

### PHP
**Marker File:** `composer.json`

**Auto-Detected Commands:**
- `composer test`
- `phpunit`
- `./vendor/bin/phpunit`

**Also Validated:** `php`, `pest`, `codeception`

### .NET (C#/F#)
**Marker Files:** `*.sln` or `*.csproj`

**Auto-Detected Commands:**
- `dotnet test`
- `dotnet build`

**Also Validated:** `dotnet` (any command), `msbuild`, `nuget`, `nunit-console`, `nunit3-console`, `xunit.console`, `vstest.console`, `mstest`

### Makefile
**Marker File:** `Makefile`

**Auto-Detected Commands:**
- `make test` (if `test` target exists)
- `make check` (if `check` target exists)
- `make build` (if `build` target exists)
- `make all` (if `all` target exists)

**Also Validated:** `make` (any target), `cmake`, `ninja`, `bazel`, `ctest`

**Note:** SmartFix prioritizes test-related targets (`test`, `check`) over build targets.

## Format Command Detection

SmartFix can also auto-detect formatting commands:

### Python Formatters
**Marker Files:** `pyproject.toml` or `setup.py`

**Auto-Detected Commands:**
- `black .`
- `ruff format .`
- `autopep8 --in-place --recursive .`

**Also Validated:** `black`, `ruff`, `autopep8`, `yapf`, `isort`, `flake8`, `pylint`

### JavaScript/TypeScript Formatters
**Marker File:** `package.json`

**Auto-Detected Commands:**
- `prettier --write .`
- `npm run format`
- `yarn format`

**Also Validated:** `prettier`, `eslint`, `standard`, package manager commands (`npm`, `yarn`, `pnpm`, `bun`)

### Java Formatters
**Marker File:** `pom.xml`

**Auto-Detected Commands:**
- `mvn spotless:apply`

**Also Validated:** `google-java-format`, `checkstyle`, `clang-format`

### .NET Formatters
**Marker Files:** `*.sln` or `*.csproj`

**Auto-Detected Commands:**
- `dotnet format`
- `csharpier .`

**Also Validated:** `dotnet`, `csharpier`, `clang-format`

### PHP Formatters
**Marker File:** `composer.json`

**Auto-Detected Commands:**
- `php-cs-fixer fix`
- `./vendor/bin/php-cs-fixer fix`

**Also Validated:** `php-cs-fixer`, `phpcbf`

## Detection Priority

### Phase 1 Priority (Deterministic)
When multiple marker files are present, SmartFix generates candidates from all detected build systems and tests them in priority order. The first command that:
1. Has the tool installed on the system (quick `mvn --version` check - just a pre-filter)
2. Passes security validation (allowlist check)
3. **Successfully executes** in your project (actual build must pass)

...is used immediately without trying Phase 2. The `--version` check is just a fast way to skip tools that aren't installed; the real validation is running the actual build.

### Phase 2 Fallback (LLM-Based)
If Phase 1 fails (no working commands found), the LLM agent:
1. Receives all Phase 1 failure messages for context
2. Suggests alternative commands from validated ecosystem tools
3. Iterates up to 6 times, adapting suggestions based on error feedback
4. Returns first successful command or None after exhausting attempts

### Phase 3 Fallback (No-Op)
If both Phase 1 and Phase 2 fail, SmartFix uses the no-op fallback command to gracefully degrade rather than failing the remediation.

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

All commands (both auto-detected and LLM-suggested) are validated against a security allowlist before execution. Commands must:
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

See [Troubleshooting](./troubleshooting-command-detection.md) for common issues and solutions.
