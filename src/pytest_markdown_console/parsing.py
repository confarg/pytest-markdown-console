"""Parsing of fenced console blocks from Markdown source."""

from __future__ import annotations

import re

from .models import Command, ConsoleBlock

_FENCE_OPEN = re.compile(r"^```\s*console\b", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"^```\s*$")
_HTML_COMMENT_OPEN = re.compile(r"^\s*<!--\s*$")


def _comment_start(cmd: str) -> int | None:
    """Return the index of the first unquoted '#' preceded by whitespace, or None."""
    in_single = False
    in_double = False
    for i, c in enumerate(cmd):
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        elif c == "#" and not in_single and not in_double and i > 0 and cmd[i - 1] in " \t":
            return i
    return None


def _strip_error_comment(cmd: str) -> tuple[str, bool]:
    """Strip a trailing inline comment; return (clean_cmd, expect_failure).

    ' # Error[:]' annotations set expect_failure; any other unquoted ' #'
    comment is silently removed so it is never passed as a command argument.
    """
    idx = cmd.find(" # Error:")
    if idx != -1:
        return cmd[:idx].rstrip(), True
    idx = cmd.find(" # Error")
    if idx != -1 and not cmd[idx + len(" # Error") :].strip():
        return cmd[:idx].rstrip(), True
    comment_idx = _comment_start(cmd)
    if comment_idx is not None:
        return cmd[:comment_idx].rstrip(), False
    return cmd, False


def _parse_directive_tokens(
    tokens_str: str,
) -> tuple[bool, str | None, frozenset[str], frozenset[str], str | None, tuple[str, ...]]:
    """Return (notest, cwd_override, only_platforms, skip_platforms, shell, fixtures) from a directive token string."""
    notest = False
    cwd_override: str | None = None
    only: set[str] = set()
    skip: set[str] = set()
    shell: str | None = None
    fixtures: tuple[str, ...] = ()
    for token in tokens_str.split():
        if token == "notest":  # noqa: S105
            notest = True
        elif token.startswith("cwd:"):
            cwd_override = token[len("cwd:") :]
        elif token.startswith("shell:"):
            shell = token[len("shell:") :]
        elif token.startswith("platform:"):
            for p in token[len("platform:") :].split(","):
                name = p.strip()
                if name.startswith("!"):
                    skip.add(name[1:])
                elif name:
                    only.add(name)
        elif token.startswith("fixtures:"):
            fixtures = tuple(n.strip() for n in token[len("fixtures:") :].split(",") if n.strip())
    return notest, cwd_override, frozenset(only), frozenset(skip), shell, fixtures


def _flush_cmd(current_cmd: Command | None, current_block: ConsoleBlock | None) -> None:
    if current_cmd is not None and current_block is not None:
        current_block.commands.append(current_cmd)


def _handle_dollar_line(
    raw: str,
    current_cmd: Command | None,
    current_block: ConsoleBlock | None,
    pending_failure: bool,  # noqa: FBT001
) -> tuple[Command | None, bool]:
    cmd_part = raw[2:]
    stripped = cmd_part.lstrip()
    if not stripped or stripped.startswith("#"):
        _flush_cmd(current_cmd, current_block)
        is_error_comment = stripped == "# Error" or stripped.startswith("# Error:")
        return None, pending_failure or is_error_comment
    _flush_cmd(current_cmd, current_block)
    clean_cmd, inline_failure = _strip_error_comment(cmd_part)
    return Command(
        cmd=clean_cmd,
        expected_output="",
        expect_failure=pending_failure or inline_failure,
    ), False


def _find_block_directive(
    lines: list[str],
    lineno: int,
    directive_re: re.Pattern[str],
) -> re.Match[str] | None:
    """Return the directive match for the fence at *lineno*, looking through a bare <!-- if needed."""
    prev_line = lines[lineno - 2] if lineno >= 2 else ""  # noqa: PLR2004
    m = directive_re.match(prev_line)
    if m is None and lineno >= 3 and _HTML_COMMENT_OPEN.match(prev_line):  # noqa: PLR2004
        m = directive_re.match(lines[lineno - 3])
    return m


def _parse_file_config(
    lines: list[str],
    directive_tag: str,
) -> tuple[bool, str | None, frozenset[str], frozenset[str], str | None, tuple[str, ...]]:
    """Return file-level directive defaults from the first matching ``<tag>-file:`` comment."""
    file_re = re.compile(rf"^\s*<!--\s*{re.escape(directive_tag)}-file:\s*(.+?)\s*-->\s*$")
    for line in lines:
        m = file_re.match(line)
        if m:
            return _parse_directive_tokens(m.group(1))
    return False, None, frozenset(), frozenset(), None, ()


def parse_blocks(source: str, directive: str = "pytest-markdown-console") -> list[ConsoleBlock]:
    """Parse all fenced console blocks from Markdown source text."""
    directive_re = re.compile(rf"^\s*<!--\s*{re.escape(directive)}:\s*(.+?)\s*-->\s*$")
    blocks: list[ConsoleBlock] = []
    lines = source.splitlines()
    f_notest, f_cwd, f_only, f_skip, f_shell, f_fixtures = _parse_file_config(lines, directive)
    in_block = False
    current_block: ConsoleBlock | None = None
    current_cmd: Command | None = None
    pending_failure = False
    indent = ""

    for lineno, raw in enumerate(lines, start=1):
        if not in_block:
            stripped = raw.lstrip()
            if _FENCE_OPEN.match(stripped):
                indent = raw[: len(raw) - len(stripped)]
                in_block = True
                directive_match = _find_block_directive(lines, lineno, directive_re)
                tokens_str = directive_match.group(1) if directive_match else ""
                notest, cwd_override, only, skip, shell, fixtures = _parse_directive_tokens(tokens_str)
                current_block = ConsoleBlock(
                    line_number=lineno,
                    notest=notest or f_notest,
                    cwd_override=cwd_override if cwd_override is not None else f_cwd,
                    only_platforms=only or f_only,
                    skip_platforms=skip or f_skip,
                    shell=shell if shell is not None else f_shell,
                    fixtures=fixtures or f_fixtures,
                )
                current_cmd = None
            continue

        line = raw.removeprefix(indent)

        if _FENCE_CLOSE.match(line):
            _flush_cmd(current_cmd, current_block)
            current_cmd = None
            if current_block is not None:
                blocks.append(current_block)
                current_block = None
            in_block = False
            indent = ""
            continue

        if line.startswith("$ "):
            current_cmd, pending_failure = _handle_dollar_line(line, current_cmd, current_block, pending_failure)
        elif line == "$":
            _flush_cmd(current_cmd, current_block)
            current_cmd = None
        elif current_cmd is not None:
            if current_cmd.expected_output:
                current_cmd.expected_output += "\n" + line
            else:
                current_cmd.expected_output = line

    return blocks
