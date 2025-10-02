# GitHub Copilot Instructions for Contrast AI SmartFix

## FUNDAMENTAL RULE: Test-First Simplicity

**EVERY change follows this pattern:**
1. **Write tests FIRST** - Before writing any production code
2. **Question every requirement** - Is this actually needed? (*Exception: When executing planned refactoring tasks from ai-dev/tasks.md*)
3. **Delete unnecessary parts** - Remove complexity, don't add it
4. **Make tests pass** - Simplest implementation that works
5. **Look around and refactor downstream** - Fix related code that uses your changes

## Working with Planned vs. Unplanned Work

### Planned Tasks (ai-dev/tasks.md):
- Follow the task plan - requirements pre-analyzed
- Test each task's deliverables before implementing
- Keep implementations simple even if architecture is complex
- Question implementation details, not the overall plan

### Unplanned Work:
- Question everything - apply full YAGNI principles
- Start minimal - build only what's needed right now
- Delete unused code immediately

## Core Workflow

### Testing (DO THIS FIRST)
- Write tests before production code - no exceptions
- Run `./test/run_tests.sh` after every change
- All tests must pass before moving on
- Delete tests for deleted features

### Complete Refactoring (Not Partial)
- When you touch code, look around - what else uses this?
- Follow the dependency chain - update ALL callers
- Clean up as you go - remove dead imports, unused variables

### Anti-Over-Engineering
- YAGNI - don't build for imaginary future requirements
- Question every class/method - can this be a simple function?
- Delete unused code immediately
- Favor simple functions over complex class hierarchies

### Red Flags - Stop and Simplify
- Classes with 1 method → use a function
- Enums/constants nobody uses → delete them
- More than 3 levels of abstraction → flatten it
- Configuration for imaginary features → remove it

## Code Standards
- All changes must pass flake8 linting
- Type hints for public interfaces
- Max line length: 180 characters
- Fix whitespace: `sed -i '' 's/[[:space:]]*$//' path/to/file.py`

## File Management - CLEAN UP INTERMEDIATE FILES
- **Never leave duplicate files** - If you create `file_clean.py`, `file_backup.py`, `file_new.py` while editing, DELETE the extras
- **Check for duplicates before finishing** - Run `ls -la` to spot files with similar names
- **One source of truth** - Each logical unit should have exactly one file
- **Remove failed attempts** - If you mess up editing and start over, delete the corrupted version
- **Common duplicate patterns to avoid:**
  - `test_something.py` and `test_something_clean.py`
  - `module.py` and `module_backup.py`
  - `config.py` and `config_new.py`

## When Refactoring Existing Code
1. **Write tests for current behavior first** - Capture existing functionality
2. **Check for planned migration path** - Is there a tasks.md plan for this area?
3. **For planned refactoring**: Follow the task sequence and dependencies
4. **For unplanned refactoring**: Question what can be deleted - Unused code, over-complex abstractions
5. **Refactor incrementally** - Small, safe changes with tests between each
6. **Follow the chain** - Update ALL code that depends on your changes
7. **Clean up afterwards** - Remove dead imports, fix related issues

## Additional Red Flags - Stop and Simplify (Even in Planned Work)
- **Complex class hierarchies** - Can the implementation be simpler?
- **More than 3 levels of abstraction** - Flatten the implementation
- **Circular dependencies** - Break them up during implementation
- **Classes with 1 method** - Could this be a function instead?
- **Enums or constants nobody uses** - Delete them even if planned
- **Configuration for imaginary future features** - Remove it

## Balancing Planning vs. Simplicity
- **Respect the architecture plan** - Don't change overall structure during task execution
- **Keep implementations simple** - Complex architecture ≠ complex implementation
- **Suggest alternatives** - If you see over-engineering opportunities during implementation
- **Focus on YAGNI for implementation details** - Don't add features not required by the current task
- **Test thoroughly** - Especially important when following complex architectural plans
