"""Data model for parsed console blocks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Command:
    """A single shell command with its expected output."""

    cmd: str
    expected_output: str  # may be empty
    expect_failure: bool = False


@dataclass
class ConsoleBlock:
    """A fenced console block parsed from a Markdown file."""

    commands: list[Command] = field(default_factory=list)
    line_number: int = 0  # 1-based line of the opening fence
    notest: bool = False
    cwd_override: str | None = None
    only_platforms: frozenset[str] = field(default_factory=frozenset)  # empty = all
    skip_platforms: frozenset[str] = field(default_factory=frozenset)  # empty = none
    shell: str | None = None
