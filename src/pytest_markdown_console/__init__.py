"""pytest plugin for testing console code blocks in Markdown files."""

from .plugin import markdown_console_tmpdir as markdown_console_tmpdir
from .plugin import pytest_addoption as pytest_addoption
from .plugin import pytest_collect_file as pytest_collect_file
from .plugin import pytest_configure as pytest_configure
from .runner import ConsoleCommandFailed, ConsoleOutputMismatch, ConsoleUnexpectedSuccess

__all__ = [
    "ConsoleCommandFailed",
    "ConsoleOutputMismatch",
    "ConsoleUnexpectedSuccess",
    "markdown_console_tmpdir",
    "pytest_addoption",
    "pytest_collect_file",
    "pytest_configure",
]
