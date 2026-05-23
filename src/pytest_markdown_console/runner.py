"""Command execution and output matching for console blocks."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Command

_ELLIPSIS = "..."
_WINDOWS = sys.platform == "win32"


def _build_argv(cmd: str, shell: str) -> list[str]:
    if shell in ("pwsh", "powershell"):
        return [shell, "-NoProfile", "-Command", cmd]
    if shell == "cmd":
        return ["cmd", "/c", cmd]
    return [shell, "-c", cmd]


def _separator(shell: str, expect_failure: bool) -> str:  # noqa: FBT001
    if shell == "cmd":
        return "&" if expect_failure else "&&"
    return ";" if expect_failure else "&&"


def _pwd_cmd(shell: str) -> str:
    if shell in ("pwsh", "powershell"):
        return "(Get-Location).Path"
    if shell == "cmd":
        return "echo %CD%"
    return "pwd"


def _run(cmd: str, cwd: str, shell: str | None = None, **kwargs: object) -> subprocess.CompletedProcess:
    """Run *cmd* in the given shell (or the platform default if None)."""
    resolved = shell or ("pwsh" if _WINDOWS else "sh")
    return subprocess.run(_build_argv(cmd, resolved), cwd=cwd, **kwargs)  # type: ignore[call-overload]


def matches(expected: str, actual: str) -> bool:
    """Return True if actual matches expected, treating '...' as a wildcard."""
    if _ELLIPSIS not in expected:
        return expected == actual
    pattern = ".*".join(re.escape(part) for part in expected.split(_ELLIPSIS))
    return bool(re.fullmatch(pattern, actual, re.DOTALL))


class ConsoleCommandFailed(Exception):
    """Raised when a command exits with a non-zero return code unexpectedly."""

    def __init__(self, cmd: str, returncode: int, stderr: str = "") -> None:
        """Initialize with command, return code, and optional stderr output."""
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command failed (exit {returncode}): $ {cmd}")


class ConsoleUnexpectedSuccess(Exception):
    """Raised when a command succeeds but was expected to fail."""

    def __init__(self, cmd: str) -> None:
        """Initialize with the command that unexpectedly succeeded."""
        self.cmd = cmd
        super().__init__(f"Expected non-zero exit code but command succeeded: $ {cmd}")


class ConsoleOutputMismatch(Exception):
    """Raised when a command's output does not match the expected output."""

    def __init__(self, cmd: str, expected: str, actual: str) -> None:
        """Initialize with command, expected output, and actual output."""
        self.cmd = cmd
        self.expected = expected
        self.actual = actual
        super().__init__(f"Output mismatch for: $ {cmd}")


def run_command(command: Command, cwd: str, shell: str | None = None) -> str:
    """Run a single command and return the updated cwd after execution.

    Raises ConsoleOutputMismatch, ConsoleUnexpectedSuccess, or ConsoleCommandFailed on failure.
    """
    resolved_shell = shell or ("pwsh" if _WINDOWS else "sh")
    result = _run(command.cmd, cwd, shell=resolved_shell, capture_output=True, text=True, check=False)

    actual = (result.stderr if command.expect_failure else result.stdout).rstrip("\n")
    expected = command.expected_output.rstrip("\n")

    if not matches(expected, actual):
        raise ConsoleOutputMismatch(cmd=command.cmd, expected=expected, actual=actual)

    if command.expect_failure and result.returncode == 0:
        raise ConsoleUnexpectedSuccess(cmd=command.cmd)

    if not command.expect_failure and result.returncode != 0:
        raise ConsoleCommandFailed(
            cmd=command.cmd,
            returncode=result.returncode,
            stderr=result.stderr.rstrip("\n"),
        )

    # Track cwd changes caused by `cd` so the next command starts there.
    sep = _separator(resolved_shell, command.expect_failure)
    pwd = _pwd_cmd(resolved_shell)
    new_cwd_result = _run(
        f"{command.cmd} {sep} {pwd}",
        cwd,
        shell=resolved_shell,
        capture_output=True,
        text=True,
        check=False,
    )
    pwd_lines = [line for line in new_cwd_result.stdout.splitlines() if line]
    if pwd_lines:
        candidate = pwd_lines[-1].strip()
        if os.path.isdir(candidate):
            return candidate

    return cwd
