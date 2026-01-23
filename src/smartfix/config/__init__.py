"""Configuration Management System

This package contains configuration management components including
base configuration classes, domain-specific configurations, and
dependency injection functionality.

Key Components (to be implemented):
- SmartFixConfig: Main configuration aggregate root
- BaseConfig: Abstract base for configuration classes
- AgentConfig: AI agent configuration and settings
- BuildConfig: Build system configuration
- ScmConfig: Source control management configuration
- TelemetryConfig: Telemetry and observability configuration
"""

from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
    ALLOWED_COMMANDS,
)

__all__ = [
    # Configuration components will be exported as they are implemented
    "validate_command",
    "CommandValidationError",
    "ALLOWED_COMMANDS",
]
