# GitHub Copilot Instructions for Contrast AI SmartFix

This document provides guidelines for GitHub Copilot when working on the Contrast AI SmartFix project.

## Core Development Principles

### 1. Code Quality & Linting
- **All code changes MUST pass linting** - Use flake8 with the project's configuration (`.flake8`)
- Follow PEP 8 style guidelines strictly
- Maximum line length: 180 characters (as configured in `.flake8`)
- Use type hints for all function parameters and return values
- Ensure proper docstrings for all functions, classes, and modules

### 2. Testing Requirements
- **New code MUST have unit tests** - No exceptions for new functionality
- **Existing code modifications MUST include tests** - When editing existing code, write comprehensive unit tests
- Use pytest as the testing framework
- Maintain minimum 80% code coverage for new code
- Tests should follow the Arrange-Act-Assert pattern
- Mock external dependencies appropriately (GitHub API, Contrast API, file system operations)

### 3. Object-Oriented Design & Domain-Driven Design
- **New code MUST follow Object-Oriented principles** - Encapsulation, inheritance, polymorphism
- **Refactor existing procedural code to OOP** - When editing old code, take the opportunity to make it Object-Oriented
- Apply Domain-Driven Design (DDD) principles to identify and model domain objects:

#### Domain Objects to Consider:
- **Vulnerability** - Represents security vulnerabilities with properties like severity, rule, UUID
- **Remediation** - Encapsulates the process of fixing a vulnerability
- **BuildResult** - Represents build execution results and status
- **GitRepository** - Manages git operations and repository state
- **PullRequest** - Represents GitHub pull request with metadata and operations
- **Agent** - Abstracts AI agent behavior (FixAgent, QAAgent)
- **TelemetryEvent** - Structured telemetry data collection
- **ConfigurationContext** - Environment and configuration management

#### Design Patterns to Use:
- **Strategy Pattern** - For different coding agents (SmartFix vs External)
- **Factory Pattern** - For creating agents, configurations, and API clients
- **Repository Pattern** - For data access (GitHub, Contrast API)
- **Command Pattern** - For git operations and build commands
- **Observer Pattern** - For telemetry and logging events

### 4. Error Handling & Resilience
- Use custom exception classes that inherit from appropriate base exceptions
- Implement proper logging at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Handle external API failures gracefully with retries where appropriate
- Validate inputs at boundaries (API responses, user inputs, configuration)

### 5. Async/Await Best Practices
- Use async/await consistently for I/O operations
- Properly handle asyncio event loops and cleanup
- Use context managers for resource management
- Handle cancellation and timeout scenarios

## File Organization & Architecture

### 6. Module Structure
- Keep modules focused on single responsibilities
- Use dependency injection instead of global state where possible
- Separate domain logic from infrastructure concerns
- Group related functionality into cohesive modules

### 7. Configuration Management
- Centralize configuration in the `Config` class
- Use environment variables with sensible defaults
- Validate configuration at startup
- Support testing configurations

## Security & Performance

### 8. Security Considerations
- Never log sensitive data (API keys, tokens)
- Sanitize user inputs and API responses
- Use secure defaults for all configurations
- Validate file paths to prevent directory traversal

### 9. Performance Guidelines
- Use efficient data structures and algorithms
- Implement proper caching where beneficial
- Avoid blocking operations in async contexts
- Monitor memory usage for large operations

## Documentation & Maintenance

### 10. Code Documentation
- Write clear, concise docstrings for all public methods
- Include usage examples in docstrings for complex functions
- Document complex business logic with inline comments
- Keep README.md updated with architectural changes

### 11. Git & Version Control
- Use descriptive commit messages following conventional commits
- Keep commits atomic and focused
- Write meaningful branch names
- Update version numbers appropriately

## Testing Patterns

### 12. Test Structure
```python
class TestClassName:
    """Test class for ClassName functionality."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        pass
    
    def test_method_name_should_expected_behavior(self):
        """Test that method_name produces expected behavior under specific conditions."""
        # Arrange
        # Act
        # Assert
        pass
```

### 13. Mock Usage
- Mock external dependencies (APIs, file system, network)
- Use `unittest.mock.patch` appropriately
- Verify mock calls when testing side effects
- Use `pytest.fixture` for reusable test data

## Legacy Code Refactoring

### 14. When Editing Existing Code
- **Identify domain objects** - Look for data and behavior that belong together
- **Extract classes** - Convert function clusters into cohesive classes
- **Introduce interfaces** - Abstract complex dependencies
- **Add tests first** - Write tests for existing behavior before refactoring
- **Refactor incrementally** - Make small, safe changes

### 15. Gradual Modernization
- Replace global variables with dependency injection
- Convert procedural code to class-based approaches
- Introduce type hints to existing functions
- Add comprehensive error handling

## Example Refactoring Approach

**Before (Procedural):**
```python
def process_vulnerability(vuln_data, repo_path, config):
    # 50+ lines of mixed concerns
    pass
```

**After (Object-Oriented):**
```python
class VulnerabilityProcessor:
    def __init__(self, repository: GitRepository, agent_factory: AgentFactory):
        self._repository = repository
        self._agent_factory = agent_factory
    
    def process(self, vulnerability: Vulnerability) -> RemediationResult:
        agent = self._agent_factory.create_fix_agent()
        return agent.remediate(vulnerability, self._repository)
```

## Continuous Improvement

- Regularly review and update these guidelines
- Incorporate learnings from code reviews
- Stay updated with Python and testing best practices
- Monitor code quality metrics and improve accordingly

---

**Remember:** These guidelines ensure maintainable, testable, and robust code that follows industry best practices and domain-driven design principles.
