# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""pytest collector and item classes for Markdown console blocks."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

import pytest

from .parsing import parse_blocks
from .runner import (
    ConsoleCommandFailed,
    ConsoleOutputMismatch,
    ConsoleUnexpectedSuccess,
    run_command,
)

try:
    from _pytest.fixtures import FixtureLookupError as _FixtureLookupError
    from _pytest.fixtures import TopRequest as _TopRequest
except ImportError:
    _TopRequest = None  # ty: ignore[invalid-assignment]  # optional private API, may not exist
    _FixtureLookupError = None  # ty: ignore[invalid-assignment]  # optional private API, may not exist

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path
    from typing import Any

    from .models import ConsoleBlock


class MarkdownFile(pytest.File):
    """pytest collector for Markdown files containing console blocks."""

    def collect(self) -> Generator[ConsoleBlockItem, None, None]:
        """Yield a ConsoleBlockItem for each testable console block."""
        source = self.path.read_text(encoding="utf-8")
        directive = self.config.getini("markdown_console_directive") or "pytest-markdown-console"
        blocks = parse_blocks(source, directive=directive)
        for idx, block in enumerate(blocks):
            if not block.commands or block.notest:
                continue
            name = f"console[{idx}]@line{block.line_number}"
            yield ConsoleBlockItem.from_parent(self, name=name, block=block)


class ConsoleBlockItem(pytest.Item):
    """pytest item representing one console block."""

    def __init__(self, *, block: ConsoleBlock, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize with the parsed ConsoleBlock."""
        super().__init__(**kwargs)
        self.block = block
        self.add_marker("markdown_console")

        factory = cast(
            "pytest.TempPathFactory | None",
            getattr(self.config, "_tmp_path_factory", None),
        )
        self._md_tmpdir: Path | None = factory.mktemp("md_console") if factory is not None else None

        if block.fixtures:
            self.add_marker(pytest.mark.usefixtures("markdown_console_tmpdir", *block.fixtures))
            self._setup_fixture_request()

    def _setup_fixture_request(self) -> None:
        """Set up pytest fixture infrastructure for user-declared fixtures."""
        if _TopRequest is None:
            return
        fm = self.session._fixturemanager  # type: ignore[attr-defined]
        fixtureinfo = fm.getfixtureinfo(node=self, func=None, cls=None)
        self._fixtureinfo = fixtureinfo  # type: ignore[attr-defined]
        self.fixturenames: list[str] = fixtureinfo.names_closure
        self.funcargs: dict[str, object] = {}
        self._request = _TopRequest(self, _ispytest=True)  # ty: ignore[invalid-argument-type]  # ConsoleBlockItem satisfies the duck type

    def setup(self) -> None:
        """Resolve user-declared fixtures, if any."""
        if not self.block.fixtures:
            return
        request = getattr(self, "_request", None)
        if request is None:
            return
        try:
            request._fillfixtures()
        except Exception as e:
            if _FixtureLookupError is not None and isinstance(e, _FixtureLookupError):
                raise LookupError(str(e)) from None
            raise

    def runtest(self) -> None:
        """Run all commands in the block and assert their output."""
        current = sys.platform
        if self.block.only_platforms and current not in self.block.only_platforms:
            pytest.skip(
                f"console block requires platform in {sorted(self.block.only_platforms)!r},"
                f" current platform is {current!r}",
            )
        if current in self.block.skip_platforms:
            pytest.skip(f"console block is skipped on platform {current!r}")

        tmpdir_path = str(self._md_tmpdir) if self._md_tmpdir is not None else None
        extra_env: dict[str, str] = {"tmpdir": tmpdir_path} if tmpdir_path is not None else {}

        funcargs: dict[str, object] = getattr(self, "funcargs", {})
        for name in self.block.fixtures:
            result = funcargs.get(name)
            if isinstance(result, dict):
                extra_env.update(result)  # ty: ignore[no-matching-overload]  # runtime isinstance check guarantees dict[str, str]

        base_dir = self.path.parent
        if self.block.cwd_override is not None:
            raw_cwd = self.block.cwd_override
            expanded_cwd = raw_cwd.replace("${tmpdir}", tmpdir_path) if tmpdir_path is not None else raw_cwd
            cwd_path = (base_dir / expanded_cwd).resolve()
            if not cwd_path.is_dir():
                msg = f"cwd path does not exist: {cwd_path}"
                raise FileNotFoundError(msg)
            cwd = str(cwd_path)
        else:
            cwd = str(base_dir)

        ini_shell = self.config.getini("markdown_console_shell") or None
        effective_shell = self.block.shell or ini_shell

        for command in self.block.commands:
            cwd = run_command(command, cwd, shell=effective_shell, extra_env=extra_env)

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException]) -> str | pytest.TerminalRepr:
        """Format a human-readable failure message."""
        if isinstance(excinfo.value, ConsoleOutputMismatch):
            e = excinfo.value
            return f"Command:  $ {e.cmd}\nExpected:\n{e.expected}\nGot:\n{e.actual}"
        if isinstance(excinfo.value, ConsoleUnexpectedSuccess):
            e = excinfo.value
            return f"Command:  $ {e.cmd}  # Error:\nExpected a non-zero exit code, but the command succeeded."
        if isinstance(excinfo.value, ConsoleCommandFailed):
            e = excinfo.value
            msg = f"Command:  $ {e.cmd}\nCommand failed with exit code {e.returncode}."
            if e.stderr:
                msg += f"\nStderr:\n{e.stderr}"
            return msg
        return super().repr_failure(excinfo)

    def reportinfo(self) -> tuple[Path, int, str]:
        """Return location info for pytest's report header."""
        return self.path, self.block.line_number - 1, f"console block @ line {self.block.line_number}"


@pytest.fixture
def markdown_console_tmpdir(request: pytest.FixtureRequest) -> Path:
    """The temporary directory for the current console block test.

    Only available when running inside a console block item. Intended for use
    by fixtures declared via the ``fixtures:`` directive — files written here
    are accessible inside the block via the ``${tmpdir}`` environment variable.
    """
    node = request.node
    if isinstance(node, ConsoleBlockItem) and node._md_tmpdir is not None:
        return node._md_tmpdir
    pytest.skip("markdown_console_tmpdir is only available inside a console block item")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ini options for pytest-markdown-console."""
    parser.addini(
        "markdown_console_shell",
        help=(
            "Default shell for console blocks (pwsh, cmd, sh, bash, zsh, …). Defaults to pwsh on Windows, sh elsewhere."
        ),
        type="string",
        default=None,
    )
    parser.addini(
        "markdown_console_directive",
        help='HTML comment tag for directives (default: "pytest-markdown-console").',
        type="string",
        default="pytest-markdown-console",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the markdown_console marker."""
    config.addinivalue_line(
        "markers",
        "markdown_console: marks tests generated by pytest-markdown-console",
    )


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> MarkdownFile | None:
    """Return a MarkdownFile collector for .md files."""
    if file_path.suffix == ".md":
        return MarkdownFile.from_parent(parent, path=file_path)
    return None
