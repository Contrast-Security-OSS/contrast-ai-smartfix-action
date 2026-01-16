# Troubleshooting Command Detection

This guide helps you diagnose and fix issues when SmartFix cannot auto-detect your build or format commands.

## Common Issues

### 1. No Build System Marker Files Found

**Problem:** SmartFix cannot find marker files like `pom.xml`, `package.json`, `build.gradle`, etc.

**Solution:**
```yaml
# Manually specify your build command in GitHub Actions workflow
env:
  BUILD_COMMAND: "your-build-command"
```

**Example:**
```yaml
env:
  BUILD_COMMAND: "bazel test //..."  # For Bazel projects
  BUILD_COMMAND: "cargo test"       # For Rust projects
  BUILD_COMMAND: "go test ./..."    # For Go projects
```

### 2. Build Tool Not Installed

**Problem:** Marker file exists but the build tool isn't available in the GitHub Actions environment.

**Error Message:**
```
Could not auto-detect BUILD_COMMAND from project structure
```

**Solution:**

Install the required build tool before running SmartFix:

```yaml
steps:
  # Install build tool first
  - name: Set up Node.js
    uses: actions/setup-node@v4
    with:
      node-version: '20'

  # Then run SmartFix (will auto-detect npm commands)
  - name: Run SmartFix
    uses: contrast-security-oss/contrast-ai-smartfix-action@main
```

### 3. Custom Build Command Needed

**Problem:** Auto-detection finds a command, but you need a different one.

**Solution:**

Override with your custom command:

```yaml
env:
  BUILD_COMMAND: "mvn clean verify -P integration-tests"
```

SmartFix will use your command instead of auto-detecting.

### 4. Monorepo with Non-Standard Structure

**Problem:** Monorepo has build files in unusual locations.

**Solution:**

SmartFix auto-detects monorepo structures, but if detection fails:

```yaml
env:
  BUILD_COMMAND: "mvn -f services/backend/pom.xml test"
```

Or use workspace-level commands:

```yaml
env:
  BUILD_COMMAND: "nx test backend"  # For Nx monorepos
  BUILD_COMMAND: "turbo run test"   # For Turborepo
```

### 5. Detection Succeeds But Command Fails

**Problem:** SmartFix detects a command but it fails when executed.

**Causes:**
- Missing dependencies
- Environment variables not set
- Database not available
- Wrong working directory

**Solution:**

Set up your environment before SmartFix runs:

```yaml
steps:
  - uses: actions/checkout@v4

  # Install dependencies
  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      java-version: '17'

  - name: Cache Maven packages
    uses: actions/cache@v4
    with:
      path: ~/.m2
      key: ${{ runner.os }}-m2-${{ hashFiles('**/pom.xml') }}

  # Set environment variables
  - name: Set up environment
    run: |
      echo "DATABASE_URL=postgres://test:test@localhost:5432/test" >> $GITHUB_ENV

  # Now run SmartFix
  - uses: contrast-security-oss/contrast-ai-smartfix-action@main
```

### 6. Format Command Not Needed

**Problem:** SmartFix tries to auto-detect a format command but you don't want one.

**Solution:**

Set an empty format command to skip formatting:

```yaml
env:
  FORMATTING_COMMAND: ""  # Skip formatting
```

Or let SmartFix handle it automatically (format commands are optional and won't cause failures).

### 7. Multiple Build Systems in One Repo

**Problem:** Repository has multiple marker files (e.g., both `pom.xml` and `package.json`).

**Behavior:** SmartFix tests all detected commands in order and uses the first one that works.

**Solution (if wrong one is chosen):**

Explicitly set the command you want:

```yaml
env:
  BUILD_COMMAND: "npm test"  # Prefer npm over Maven
```

### 8. Security Validation Failure

**Problem:** Detected command fails security validation.

**Error Message:**
```
Command validation failed: Command contains dangerous pattern
```

**Cause:** The detected command contains patterns that could be security risks (e.g., command substitution, shell redirection).

**Solution:**

This shouldn't happen with auto-detected commands (they're safe by design), but if it does:

1. **Check if command was manually set with unsafe patterns:**
   ```yaml
   # ❌ Unsafe - will be rejected
   BUILD_COMMAND: "mvn test && rm -rf /"

   # ✅ Safe - will pass validation
   BUILD_COMMAND: "mvn test"
   ```

2. **Report the issue** if auto-detection generated an invalid command (this is a bug).

### 9. Required Command But None Detected

**Problem:** `RUN_TASK=generate_fix` requires a BUILD_COMMAND but detection failed.

**Error Message:**
```
BUILD_COMMAND is required but not provided and could not be auto-detected.
Please set BUILD_COMMAND environment variable or ensure project has
recognizable build system markers (pom.xml, build.gradle, package.json, etc.)
```

**Solution:**

Set BUILD_COMMAND manually:

```yaml
env:
  BUILD_COMMAND: "your-test-command"
```

## Debugging

### Enable Debug Mode

See detailed detection logs:

```yaml
env:
  DEBUG_MODE: "true"
```

This will show:
- Which marker files were found
- Which commands were generated
- Which command was selected
- Why commands were rejected

### Check Logs

Look for these log messages:

```
Auto-detected BUILD_COMMAND: mvn test
```

or

```
Could not auto-detect BUILD_COMMAND from project structure
```

### Verify Marker Files Exist

Check that your project has the expected marker files:

```bash
# In your repository
ls -la pom.xml package.json build.gradle pytest.ini
```

### Test Command Locally

Before relying on auto-detection, verify your command works:

```bash
# Test the command SmartFix would use
mvn test
npm test
pytest
```

## Best Practices

### 1. Use Standard Project Structure

SmartFix works best with standard project layouts:

```
✅ Good (standard)
my-project/
  pom.xml
  src/
    main/
    test/

❌ Challenging (non-standard)
my-project/
  config/
    maven/
      pom.xml
  sources/
```

### 2. Include Lock Files

For Node.js projects, commit lock files for accurate package manager detection:

- `package-lock.json` (npm)
- `yarn.lock` (yarn)
- `pnpm-lock.yaml` (pnpm)
- `bun.lockb` (bun)

### 3. Test in CI First

Before relying on auto-detection in production:

1. Create a test PR
2. Let SmartFix auto-detect
3. Verify the detected command works
4. Adjust if needed

### 4. Document Custom Commands

If you must use custom commands, document why in your workflow:

```yaml
env:
  # Custom command needed because:
  # - We use a wrapper script for test setup
  # - Standard 'mvn test' doesn't include integration tests
  BUILD_COMMAND: "./scripts/run-all-tests.sh"
```

## Getting Help

If auto-detection isn't working:

1. **Check this guide** for your specific issue
2. **Enable DEBUG_MODE** and review logs
3. **Check [Supported Build Systems](./supported-build-systems.md)** to verify your tool is supported
4. **Set BUILD_COMMAND manually** as a workaround
5. **Open an issue** with:
   - Your build system and version
   - Relevant marker files in your repo
   - Debug logs
   - Expected vs actual behavior

## Related Documentation

- [Supported Build Systems](./supported-build-systems.md) - Complete list of supported build systems
- [Command Validation](./command-validation.md) - Security validation rules
- [Configuration](../README.md#configuration) - All environment variables
