"""Parsing of fenced console blocks from Markdown source."""

from __future__ import annotations

import re

from .models import Command, ConsoleBlock

_FENCE_OPEN = re.compile(r"^```\s*console(?:\s+(.+?))?\s*$", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"^```\s*$")


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


def _parse_fence_tokens(
    tokens_str: str,
) -> tuple[bool, str | None, frozenset[str], frozenset[str], str | None]:
    """Return (notest, cwd_override, only_platforms, skip_platforms, shell) from a fence token string."""
    notest = False
    cwd_override: str | None = None
    only: set[str] = set()
    skip: set[str] = set()
    shell: str | None = None
    for token in tokens_str.split():
        if token == "notest":
            notest = True
        elif token.startswith("cwd:"):
            cwd_override = token[len("cwd:"):]
        elif token.startswith("shell:"):
            shell = token[len("shell:"):]
        elif token.startswith("platform:"):
            for p in token[len("platform:"):].split(","):
                p = p.strip()
                if p.startswith("!"):
                    skip.add(p[1:])
                elif p:
                    only.add(p)
    return notest, cwd_override, frozenset(only), frozenset(skip), shell


def _flush_cmd(current_cmd: Command | None, current_block: ConsoleBlock | None) -> None:
    if current_cmd is not None and current_block is not None:
        current_block.commands.append(current_cmd)


def _handle_dollar_line(
    raw: str,
    current_cmd: Command | None,
    current_block: ConsoleBlock | None,
    pending_failure: bool,
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


def parse_blocks(source: str) -> list[ConsoleBlock]:
    """Parse all fenced console blocks from Markdown source text."""
    blocks: list[ConsoleBlock] = []
    lines = source.splitlines()
    in_block = False
    current_block: ConsoleBlock | None = None
    current_cmd: Command | None = None
    pending_failure = False

    for lineno, raw in enumerate(lines, start=1):
        if not in_block:
            m = _FENCE_OPEN.match(raw)
            if m:
                in_block = True
                notest, cwd_override, only, skip, shell = _parse_fence_tokens(m.group(1) or "")
                current_block = ConsoleBlock(
                    line_number=lineno,
                    notest=notest,
                    cwd_override=cwd_override,
                    only_platforms=only,
                    skip_platforms=skip,
                    shell=shell,
                )
                current_cmd = None
            continue

        if _FENCE_CLOSE.match(raw):
            _flush_cmd(current_cmd, current_block)
            current_cmd = None
            if current_block is not None:
                blocks.append(current_block)
                current_block = None
            in_block = False
            continue

        if raw.startswith("$ "):
            current_cmd, pending_failure = _handle_dollar_line(raw, current_cmd, current_block, pending_failure)
        elif raw == "$":
            _flush_cmd(current_cmd, current_block)
            current_cmd = None
        elif current_cmd is not None:
            if current_cmd.expected_output:
                current_cmd.expected_output += "\n" + raw
            else:
                current_cmd.expected_output = raw

    return blocks
