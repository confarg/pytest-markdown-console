# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for command execution and output matching."""

from unittest.mock import MagicMock, patch

import pytest

from pytest_markdown_console.models import Command
from pytest_markdown_console.runner import (
    ConsoleCommandFailed,
    ConsoleOutputMismatch,
    ConsoleUnexpectedSuccess,
    _build_argv,
    _pwd_cmd,
    _separator,
    matches,
    run_command,
)

# ---------------------------------------------------------------------------
# _build_argv(), _separator(), _pwd_cmd()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shell", "cmd", "expected"),
    [
        ("pwsh", "Get-Date", ["pwsh", "-NoProfile", "-Command", "Get-Date"]),
        ("powershell", "Get-Date", ["powershell", "-NoProfile", "-Command", "Get-Date"]),
        ("cmd", "dir", ["cmd", "/c", "dir"]),
        ("sh", "echo hi", ["sh", "-c", "echo hi"]),
        ("bash", "echo hi", ["bash", "-c", "echo hi"]),
        ("zsh", "echo hi", ["zsh", "-c", "echo hi"]),
    ],
    ids=["pwsh", "powershell", "cmd", "sh", "bash", "zsh"],
)
def test_build_argv(shell, cmd, expected):
    """_build_argv() produces the correct argv list for each shell."""
    assert _build_argv(cmd, shell) == expected


@pytest.mark.parametrize(
    ("shell", "expect_failure", "expected"),
    [
        ("pwsh", False, "&&"),
        ("pwsh", True, ";"),
        ("powershell", False, "&&"),
        ("powershell", True, ";"),
        ("cmd", False, "&&"),
        ("cmd", True, "&"),
        ("sh", False, "&&"),
        ("sh", True, ";"),
        ("bash", False, "&&"),
        ("bash", True, ";"),
    ],
    ids=[
        "pwsh_ok",
        "pwsh_fail",
        "powershell_ok",
        "powershell_fail",
        "cmd_ok",
        "cmd_fail",
        "sh_ok",
        "sh_fail",
        "bash_ok",
        "bash_fail",
    ],
)
def test_separator(shell, expect_failure, expected):
    """_separator() returns the correct shell-specific command separator."""
    assert _separator(shell, expect_failure) == expected


@pytest.mark.parametrize(
    ("shell", "expected"),
    [
        ("pwsh", "(Get-Location).Path"),
        ("powershell", "(Get-Location).Path"),
        ("cmd", "echo %CD%"),
        ("sh", "pwd"),
        ("bash", "pwd"),
        ("zsh", "pwd"),
    ],
    ids=["pwsh", "powershell", "cmd", "sh", "bash", "zsh"],
)
def test_pwd_cmd(shell, expected):
    """_pwd_cmd() returns the correct pwd command for each shell."""
    assert _pwd_cmd(shell) == expected


# ---------------------------------------------------------------------------
# matches()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "actual", "result"),
    [
        ("hello", "hello", True),
        ("hello", "world", False),
        ("a b", "a  b", False),
        ("...world", "helloworld", True),
        ("hello...", "hello world", True),
        ("hel...rld", "hello world", True),
        ("a...b...c", "aXbYc", True),
        ("start\n...\nend", "start\nmiddle\nend", True),
        ("...", "", True),
        ("a...b", "ab", True),
    ],
    ids=[
        "exact_match",
        "exact_mismatch",
        "no_ellipsis_strict",
        "ellipsis_prefix",
        "ellipsis_suffix",
        "ellipsis_middle",
        "multiple_ellipses",
        "ellipsis_multiline",
        "ellipsis_only",
        "ellipsis_adjacent",
    ],
)
def test_matches(expected, actual, result):
    """matches() returns True iff actual satisfies expected (with ... wildcards)."""
    assert matches(expected, actual) is result


# ---------------------------------------------------------------------------
# run_command() helpers
# ---------------------------------------------------------------------------


def _make_result(stdout="", stderr="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


# ---------------------------------------------------------------------------
# run_command() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stdout", "expected_output"),
    [
        ("", ""),
        ("hello\n", "hello"),
        ("line1\nline2\n", "line1\nline2"),
    ],
    ids=["no_output", "single_line", "multiline"],
)
@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_success(mock_run, tmp_path, stdout, expected_output):
    """Successful commands with matching output do not raise."""
    mock_run.side_effect = [
        _make_result(stdout=stdout, returncode=0),
        _make_result(stdout=str(tmp_path) + "\n", returncode=0),
    ]
    run_command(Command(cmd="cmd", expected_output=expected_output), str(tmp_path))


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_output_mismatch_raises(mock_run, tmp_path):
    """A stdout mismatch raises ConsoleOutputMismatch with the correct fields."""
    mock_run.return_value = _make_result(stdout="wrong\n", returncode=0)
    with pytest.raises(ConsoleOutputMismatch) as exc:
        run_command(Command(cmd="echo hello", expected_output="hello"), str(tmp_path))
    assert exc.value.cmd == "echo hello"
    assert exc.value.expected == "hello"
    assert exc.value.actual == "wrong"


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_nonzero_exit_raises(mock_run, tmp_path):
    """A non-zero exit code raises ConsoleCommandFailed with returncode and stderr."""
    mock_run.return_value = _make_result(stdout="", stderr="oops\n", returncode=1)
    with pytest.raises(ConsoleCommandFailed) as exc:
        run_command(Command(cmd="false", expected_output=""), str(tmp_path))
    assert exc.value.returncode == 1
    assert exc.value.stderr == "oops"


# ---------------------------------------------------------------------------
# run_command() — expect_failure branch
# ---------------------------------------------------------------------------


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_expected_failure_correct(mock_run, tmp_path):
    """A command that fails as expected (matching stderr) does not raise."""
    mock_run.side_effect = [
        _make_result(stdout="", stderr="bad arg\n", returncode=1),
        _make_result(stdout=str(tmp_path) + "\n", returncode=0),
    ]
    run_command(Command(cmd="false", expected_output="bad arg", expect_failure=True), str(tmp_path))


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_unexpected_success_raises(mock_run, tmp_path):
    """A command that succeeds when failure was expected raises ConsoleUnexpectedSuccess."""
    mock_run.return_value = _make_result(stdout="ok\n", stderr="", returncode=0)
    with pytest.raises(ConsoleUnexpectedSuccess) as exc:
        run_command(Command(cmd="true", expected_output="", expect_failure=True), str(tmp_path))
    assert exc.value.cmd == "true"


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_expected_failure_output_mismatch_raises(mock_run, tmp_path):
    """A failing command whose stderr doesn't match expected raises ConsoleOutputMismatch."""
    mock_run.return_value = _make_result(stdout="", stderr="wrong error\n", returncode=1)
    with pytest.raises(ConsoleOutputMismatch):
        run_command(Command(cmd="false", expected_output="expected error", expect_failure=True), str(tmp_path))


@patch("pytest_markdown_console.runner.subprocess.run")
def test_run_command_returns_original_cwd_when_pwd_output_invalid(mock_run, tmp_path):
    """run_command returns the original cwd when the pwd probe produces no valid directory path."""
    mock_run.side_effect = [
        _make_result(stdout="hello\n", returncode=0),
        _make_result(stdout="not_a_real_directory_xyz_abc\n", returncode=0),
    ]
    result = run_command(Command(cmd="echo hello", expected_output="hello"), str(tmp_path))
    assert result == str(tmp_path)


# ---------------------------------------------------------------------------
# Exception attributes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "attrs"),
    [
        (
            ConsoleCommandFailed(cmd="ls /nope", returncode=2, stderr="no such file"),
            {"cmd": "ls /nope", "returncode": 2, "stderr": "no such file"},
        ),
        (
            ConsoleUnexpectedSuccess(cmd="true"),
            {"cmd": "true"},
        ),
        (
            ConsoleOutputMismatch(cmd="echo hi", expected="hi", actual="bye"),
            {"cmd": "echo hi", "expected": "hi", "actual": "bye"},
        ),
    ],
    ids=["command_failed", "unexpected_success", "output_mismatch"],
)
def test_exception_attributes(exc, attrs):
    """Each exception class exposes its constructor arguments as attributes."""
    for attr, value in attrs.items():
        assert getattr(exc, attr) == value
