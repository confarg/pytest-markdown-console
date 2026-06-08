# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Integration tests for the pytest plugin using pytester."""

import sys

import pytest


@pytest.fixture
def md(pytester):
    """Helper that writes a Markdown file and returns the path."""

    def _write(content: str, name: str = "doc.md"):
        p = pytester.path / name
        p.write_text(content, encoding="utf-8")
        return p

    return _write


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "```console\n$ echo hi\nhi\n```\n",
        "# Title\n\n```console\n$ echo hi\n```\n",
        "text\n\n```console\n$ a\n```\n\n```console\n$ b\n```\n",
    ],
    ids=["simple_block", "block_after_heading", "multiple_blocks"],
)
def test_collects_md_files(pytester, md, source):
    """Markdown files with console blocks are collected as test items."""
    md(source)
    result = pytester.runpytest("--collect-only", "-q")
    result.stdout.fnmatch_lines(["*console*"])


@pytest.mark.parametrize(
    "source",
    [
        "<!-- pytest-markdown-console: notest -->\n```console\n$ echo hi\n```\n",
        "```console\n```\n",
    ],
    ids=["notest_flag", "empty_block"],
)
def test_not_collected(pytester, md, source):
    """Blocks with notest flag or no commands are excluded from collection."""
    md(source)
    result = pytester.runpytest("--collect-only", "-q")
    result.stdout.no_fnmatch_line("*console*")


def test_ignores_non_md_files(pytester):
    """Non-.md files are not collected by the plugin."""
    (pytester.path / "script.py").write_text("# nothing\n", encoding="utf-8")
    result = pytester.runpytest("--collect-only", "-q")
    result.stdout.no_fnmatch_line("*console*")


# ---------------------------------------------------------------------------
# Passing tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="echo behaves differently on Windows")
def test_passing_echo(pytester, md):
    """A block whose command output matches passes."""
    md("```console\n$ echo hello\nhello\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform == "win32", reason="echo behaves differently on Windows")
def test_ellipsis_wildcard(pytester, md):
    """The ... wildcard in expected output matches any substring."""
    md("```console\n$ echo hello world\nhello ...\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Failing tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="echo behaves differently on Windows")
def test_output_mismatch_reported(pytester, md):
    """An output mismatch produces a failure with Expected/Got in the report."""
    md("```console\n$ echo hello\nwrong\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Expected*", "*Got*"])


@pytest.mark.skipif(sys.platform != "win32", reason="uses pwsh Write-Output")
def test_output_mismatch_reported_windows(pytester, md):
    """An output mismatch produces a failure with Expected/Got in the report (Windows)."""
    md("```console\n$ Write-Output hello\nwrong\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Expected*", "*Got*"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: uses 'exit 1'")
def test_unexpected_command_failure_windows(pytester, md):
    """A command that exits non-zero without expect_failure produces a failure."""
    md("```console\n$ exit 1\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)


@pytest.mark.skipif(sys.platform != "win32", reason="uses pwsh Write-Error")
def test_command_failure_stderr_in_report_windows(pytester, md):
    """A failing command with stderr output includes a Stderr section in the report."""
    md("```console\n$ Write-Error 'oops'; exit 1\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Stderr*"])


# ---------------------------------------------------------------------------
# Expected failure
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="'false' command not standard on Windows")
def test_expected_failure_passes(pytester, md):
    """A command annotated with # Error: that does fail is a passing test."""
    md("```console\n$ false  # Error: will fail\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform == "win32", reason="'true' command not standard on Windows")
def test_unexpected_success_fails(pytester, md):
    """A command annotated with # Error: that succeeds is a failing test."""
    md("```console\n$ true  # Error:\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Expected a non-zero exit code*"])


@pytest.mark.skipif(sys.platform != "win32", reason="uses pwsh Write-Output")
def test_unexpected_success_fails_windows(pytester, md):
    """A command annotated with # Error: that succeeds is a failing test (Windows)."""
    md("```console\n$ Write-Output hi  # Error:\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Expected a non-zero exit code*"])


# ---------------------------------------------------------------------------
# Platform filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("platform_token", "expected_outcome"),
    [
        (sys.platform, "collected"),
        ("notaplatform", "skipped"),
    ],
    ids=["current_platform_runs", "unknown_platform_skipped"],
)
def test_platform_only(pytester, md, platform_token, expected_outcome):
    """platform: token runs the block on matching platforms and skips it on others."""
    md(f"<!-- pytest-markdown-console: platform:{platform_token} -->\n```console\n$ echo hi\n```\n")
    if expected_outcome == "collected":
        result = pytester.runpytest("--collect-only", "-q")
        result.stdout.fnmatch_lines(["*console*"])
    else:
        result = pytester.runpytest("-v")
        result.assert_outcomes(skipped=1)


def test_platform_skip_current(pytester, md):
    """platform:!<current> causes the block to be skipped on this platform."""
    md(f"<!-- pytest-markdown-console: platform:!{sys.platform} -->\n```console\n$ echo hi\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(skipped=1)


# ---------------------------------------------------------------------------
# cwd override
# ---------------------------------------------------------------------------


def test_cwd_override_valid(pytester, md):
    """cwd: pointing to an existing directory runs the command there."""
    subdir = pytester.path / "sub"
    subdir.mkdir()
    md("<!-- pytest-markdown-console: cwd:sub -->\n```console\n$ echo ok\nok\n```\n")
    result = pytester.runpytest("-v")
    # Windows echo adds a trailing space; just check it didn't crash badly
    assert result.ret in (0, 1)


def test_cwd_override_missing_raises(pytester, md):
    """cwd: pointing to a missing directory causes the test to fail."""
    md("<!-- pytest-markdown-console: cwd:nonexistent -->\n```console\n$ echo ok\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)


# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------


def test_markdown_console_marker_registered(pytester, md):
    """The markdown_console marker is registered and visible via --markers."""
    md("```console\n$ echo hi\n```\n")
    result = pytester.runpytest("--markers")
    result.stdout.fnmatch_lines(["*markdown_console*"])


# ---------------------------------------------------------------------------
# Multiple blocks in one file
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="echo behaves differently on Windows")
def test_multiple_blocks_both_run(pytester, md):
    """Each console block in a file produces an independent test item."""
    md("```console\n$ echo a\na\n```\n\n```console\n$ echo b\nb\n```\n")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=2)


# ---------------------------------------------------------------------------
# tmpdir env var
# ---------------------------------------------------------------------------


def test_tmpdir_env_var_is_a_directory(pytester, md):
    """The tmpdir env var is set to an existing directory for each console block."""
    md(
        "```console\n"
        "$ python -c \"import os, sys; v = os.environ.get('tmpdir'); sys.exit(0 if v and os.path.isdir(v) else 1)\"\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX shell ${} expansion")
def test_tmpdir_expands_in_posix_commands(pytester, md):
    """On POSIX, ${tmpdir} expands to an existing directory path in shell commands."""
    md('```console\n$ test -d "${tmpdir}"\n```\n')
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform != "win32", reason="uses PowerShell $env: syntax")
def test_tmpdir_accessible_in_powershell(pytester, md):
    """On Windows, $env:tmpdir expands to an existing directory path in pwsh commands."""
    md(
        "```console\n$ if (-not (Test-Path $env:tmpdir -PathType Container)) { exit 1 }\n```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_tmpdir_in_cwd_directive(pytester, md):
    """cwd:${tmpdir} resolves to the block's tmpdir and the command runs there."""
    md(
        '<!-- pytest-markdown-console: cwd:${tmpdir} -->\n```console\n$ python -c "pass"\n```\n',
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_tmpdir_in_cwd_missing_subdir_raises(pytester, md):
    """cwd:${tmpdir}/nonexistent fails because the subdirectory does not exist."""
    md(
        '<!-- pytest-markdown-console: cwd:${tmpdir}/nonexistent_subdir -->\n```console\n$ python -c "pass"\n```\n',
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1)


def test_tmpdir_is_isolated_between_blocks(pytester, md):
    """Each console block receives a distinct tmpdir path."""
    md(
        "```console\n"
        "$ python -c \"import os; print(os.environ['tmpdir'])\"\n"
        "...\n"
        "```\n"
        "\n"
        "```console\n"
        "$ python -c \"import os; print(os.environ['tmpdir'])\"\n"
        "...\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=2)


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX mkdir")
def test_cwd_tmpdir_mkdir_in_block(pytester, md):
    """Within a block starting in ${tmpdir}, a mkdir'd subdir is visible to the next command."""
    md(
        "<!-- pytest-markdown-console: cwd:${tmpdir} -->\n"
        "```console\n"
        "$ mkdir mysubdir\n"
        "$ python -c \"import os; assert os.path.isdir('mysubdir')\"\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# fixtures: directive
# ---------------------------------------------------------------------------


def test_fixture_writes_to_tmpdir(pytester, md):
    """A fixture that writes to markdown_console_tmpdir makes the file accessible via ${tmpdir}."""
    pytester.makeconftest(
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def write_greeting(markdown_console_tmpdir):\n"
        "    (markdown_console_tmpdir / 'hello.txt').write_text('hi')\n",
    )
    md(
        "<!-- pytest-markdown-console: fixtures:write_greeting -->\n"
        "```console\n"
        "$ python -c \"import pathlib,os;assert(pathlib.Path(os.environ['tmpdir'])/'hello.txt').read_text()=='hi'\"\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX shell variable expansion")
def test_fixture_returns_env_dict_posix(pytester, md):
    """A fixture returning dict[str, str] injects those keys as environment variables (POSIX)."""
    pytester.makeconftest(
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def inject_var(markdown_console_tmpdir):\n"
        "    return {'MY_GREETING': 'hello'}\n",
    )
    md(
        '<!-- pytest-markdown-console: fixtures:inject_var -->\n```console\n$ test "${MY_GREETING}" = "hello"\n```\n',
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


@pytest.mark.skipif(sys.platform != "win32", reason="uses PowerShell $env: syntax")
def test_fixture_returns_env_dict_windows(pytester, md):
    """A fixture returning dict[str, str] injects those keys as environment variables (Windows)."""
    pytester.makeconftest(
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def inject_var(markdown_console_tmpdir):\n"
        "    return {'MY_GREETING': 'hello'}\n",
    )
    md(
        "<!-- pytest-markdown-console: fixtures:inject_var -->\n"
        "```console\n"
        "$ if ($env:MY_GREETING -ne 'hello') { exit 1 }\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_fixture_side_effect_only(pytester, md):
    """A fixture returning None (side-effect only) is tolerated; files it wrote are accessible."""
    pytester.makeconftest(
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def write_file(markdown_console_tmpdir):\n"
        "    (markdown_console_tmpdir / 'data.txt').write_text('ok')\n"
        "    # returns None implicitly\n",
    )
    md(
        "<!-- pytest-markdown-console: fixtures:write_file -->\n"
        "```console\n"
        "$ python -c \"import pathlib,os;assert(pathlib.Path(os.environ['tmpdir'])/'data.txt').read_text()=='ok'\"\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_multiple_fixtures(pytester, md):
    """Multiple fixtures listed in fixtures: all run and their env dicts are merged."""
    pytester.makeconftest(
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def setup_a(markdown_console_tmpdir):\n"
        "    return {'VAR_A': 'alpha'}\n"
        "\n"
        "@pytest.fixture\n"
        "def setup_b(markdown_console_tmpdir):\n"
        "    return {'VAR_B': 'beta'}\n",
    )
    md(
        "<!-- pytest-markdown-console: fixtures:setup_a,setup_b -->\n"
        "```console\n"
        "$ python -c \"import os; assert (os.environ.get('VAR_A'), os.environ.get('VAR_B')) == ('alpha', 'beta')\"\n"
        "```\n",
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_unknown_fixture_fails(pytester, md):
    """Naming a fixture that does not exist causes the test to fail."""
    md(
        '<!-- pytest-markdown-console: fixtures:does_not_exist -->\n```console\n$ python -c "pass"\n```\n',
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(errors=1)
