"""Tests for Markdown console block parsing."""

import pytest

from pytest_markdown_console.parsing import parse_blocks

# ---------------------------------------------------------------------------
# Sources that yield no blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "",
        "# Title\n\n```python\nprint('hello')\n```\n",
        "plain text with no fences\n",
    ],
    ids=["empty", "python_block", "no_fences"],
)
def test_no_blocks_parsed(source):
    """Sources with no console blocks produce an empty list."""
    assert parse_blocks(source) == []


# ---------------------------------------------------------------------------
# Single command — basic fields
# ---------------------------------------------------------------------------


def test_single_command_no_output():
    """A lone command with no following lines has empty expected_output."""
    blocks = parse_blocks("```console\n$ echo hi\n```\n")
    assert len(blocks) == 1
    cmd = blocks[0].commands[0]
    assert cmd.cmd == "echo hi"
    assert cmd.expected_output == ""
    assert not cmd.expect_failure


def test_command_with_expected_output():
    """Output lines following a command are captured as expected_output."""
    blocks = parse_blocks("```console\n$ echo hi\nhi\n```\n")
    assert blocks[0].commands[0].expected_output == "hi"


def test_multiline_expected_output():
    """Multiple output lines are joined with newlines."""
    blocks = parse_blocks("```console\n$ printf 'a\\nb'\na\nb\n```\n")
    assert blocks[0].commands[0].expected_output == "a\nb"


# ---------------------------------------------------------------------------
# Multiple commands / blocks
# ---------------------------------------------------------------------------


def test_multiple_commands():
    """Multiple $ lines in one block each produce a distinct Command."""
    blocks = parse_blocks("```console\n$ echo a\na\n$ echo b\nb\n```\n")
    cmd_a, cmd_b = blocks[0].commands
    assert cmd_a.cmd == "echo a"
    assert cmd_a.expected_output == "a"
    assert cmd_b.cmd == "echo b"
    assert cmd_b.expected_output == "b"


def test_multiple_blocks():
    """Separate fenced blocks each produce their own ConsoleBlock."""
    source = "```console\n$ echo a\n```\n\nsome text\n\n```console\n$ echo b\n```\n"
    block_a, block_b = parse_blocks(source)
    assert block_a.commands[0].cmd == "echo a"
    assert block_b.commands[0].cmd == "echo b"


# ---------------------------------------------------------------------------
# expect_failure detection — inline and preceding-comment forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_cmd"),
    [
        ("```console\n$ false  # Error: will fail\n```\n", "false"),
        ("```console\n$ false  # Error:\n```\n", "false"),
        ("```console\n$ false  # Error\n```\n", "false"),
        ("```console\n$ # Error:\n$ false\n```\n", "false"),
        ("```console\n$ # Error\n$ false\n```\n", "false"),
    ],
    ids=["inline_message", "inline_bare", "inline_no_colon", "preceding_comment", "preceding_no_colon"],
)
def test_expect_failure_detected(source, expected_cmd):
    """Commands marked with # Error: have expect_failure set to True."""
    blocks = parse_blocks(source)
    cmd = blocks[0].commands[0]
    assert cmd.expect_failure is True
    assert cmd.cmd == expected_cmd


# ---------------------------------------------------------------------------
# Fence token parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fence_tokens", "attr", "expected"),
    [
        ("notest", "notest", True),
        ("cwd:../", "cwd_override", "../"),
        ("cwd:sub/dir", "cwd_override", "sub/dir"),
        ("shell:pwsh", "shell", "pwsh"),
        ("shell:cmd", "shell", "cmd"),
        ("shell:bash", "shell", "bash"),
        ("shell:sh", "shell", "sh"),
    ],
    ids=["notest", "cwd_parent", "cwd_subdir", "shell_pwsh", "shell_cmd", "shell_bash", "shell_sh"],
)
def test_fence_token_scalar(fence_tokens, attr, expected):
    """Scalar fence tokens (notest, cwd:, shell:) are parsed onto the ConsoleBlock."""
    source = f"```console {fence_tokens}\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert getattr(block, attr) == expected


def test_shell_token_absent():
    """shell is None when no shell: token is present."""
    block = parse_blocks("```console\n$ echo hi\n```\n")[0]
    assert block.shell is None


@pytest.mark.parametrize(
    ("platform_token", "only_platforms", "skip_platforms"),
    [
        ("platform:linux,macos", frozenset({"linux", "macos"}), frozenset()),
        ("platform:linux", frozenset({"linux"}), frozenset()),
        ("platform:!windows", frozenset(), frozenset({"windows"})),
        ("platform:!linux,!macos", frozenset(), frozenset({"linux", "macos"})),
    ],
    ids=["only_two", "only_one", "skip_one", "skip_two"],
)
def test_platform_token(platform_token, only_platforms, skip_platforms):
    """Platform tokens populate only_platforms and skip_platforms correctly."""
    source = f"```console {platform_token}\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.only_platforms == only_platforms
    assert block.skip_platforms == skip_platforms


def test_combined_fence_tokens():
    """Multiple fence tokens in one line are all parsed independently."""
    block = parse_blocks("```console notest cwd:sub platform:linux shell:bash\n$ echo hi\n```\n")[0]
    assert block.notest is True
    assert block.cwd_override == "sub"
    assert block.only_platforms == frozenset({"linux"})
    assert block.shell == "bash"


# ---------------------------------------------------------------------------
# Line number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_line"),
    [
        ("```console\n$ echo hi\n```\n", 1),
        ("# Title\n\n```console\n$ echo hi\n```\n", 3),
        ("\n\n\n```console\n$ echo hi\n```\n", 4),
    ],
    ids=["first_line", "after_heading", "after_blanks"],
)
def test_line_number_recorded(source, expected_line):
    """The 1-based opening-fence line number is stored on the block."""
    blocks = parse_blocks(source)
    assert blocks[0].line_number == expected_line


# ---------------------------------------------------------------------------
# Lines ignored by the parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_body",
    [
        "$\n",
        "$ # just a comment\n",
        "$ \n",
    ],
    ids=["bare_dollar", "comment_line", "dollar_space"],
)
def test_no_command_produced(block_body):
    """Lines that are bare $ or $ comments do not produce a Command."""
    blocks = parse_blocks(f"```console\n{block_body}```\n")
    assert blocks[0].commands == []


# ---------------------------------------------------------------------------
# Inline shell comments (non-Error)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_cmd", "expected_failure"),
    [
        # Plain and no-space inline comments
        ("```console\n$ my_app --flag 42  # to order pizza\n```\n", "my_app --flag 42", False),
        ("```console\n$ my_app --flag  #no-space-after-hash\n```\n", "my_app --flag", False),
        # '#' inside double quotes also containing a single quote — must not be treated as comment
        ("```console\n$ echo \"'#\"  # comment\n```\n", "echo \"'#\"", False),
        # '#' inside single quotes also containing a double quote — must not be treated as comment
        ('```console\n$ echo \'\"#\'  # comment\n```\n', "echo '\"#'", False),
        # '# Error' annotations still set expect_failure
        ("```console\n$ false  # Error: expected\n```\n", "false", True),
        ("```console\n$ false  # Error\n```\n", "false", True),
    ],
    ids=[
        "plain_comment",
        "comment_no_space",
        "hash_single_quote_in_double_quotes",
        "hash_double_quote_in_single_quotes",
        "error_colon_preserved",
        "error_bare_preserved",
    ],
)
def test_inline_comment_handling(source, expected_cmd, expected_failure):
    """Inline comments are stripped; quoted '#' and # Error annotations are handled correctly."""
    cmd = parse_blocks(source)[0].commands[0]
    assert cmd.cmd == expected_cmd
    assert cmd.expect_failure is expected_failure


# ---------------------------------------------------------------------------
# Case-insensitive fence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language_tag", ["Console", "CONSOLE", "console"])
def test_fence_case_insensitive(language_tag):
    """The console language tag is matched case-insensitively."""
    blocks = parse_blocks(f"```{language_tag}\n$ echo hi\n```\n")
    assert len(blocks) == 1
