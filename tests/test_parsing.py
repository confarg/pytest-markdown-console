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
# Directive comment parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("directive_tokens", "attr", "expected"),
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
def test_directive_comment_scalar(directive_tokens, attr, expected):
    """Scalar directive tokens (notest, cwd:, shell:) are parsed onto the ConsoleBlock."""
    source = f"<!-- pytest-markdown-console: {directive_tokens} -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert getattr(block, attr) == expected


def test_shell_token_absent():
    """Shell is None when no shell: token is present."""
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
def test_platform_directive(platform_token, only_platforms, skip_platforms):
    """Platform tokens populate only_platforms and skip_platforms correctly."""
    source = f"<!-- pytest-markdown-console: {platform_token} -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.only_platforms == only_platforms
    assert block.skip_platforms == skip_platforms


def test_combined_directives():
    """Multiple directive tokens in one comment are all parsed independently."""
    source = "<!-- pytest-markdown-console: notest cwd:sub platform:linux shell:bash -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.notest is True
    assert block.cwd_override == "sub"
    assert block.only_platforms == frozenset({"linux"})
    assert block.shell == "bash"


def test_directive_comment_not_adjacent():
    """A directive comment separated from the fence by a blank line is ignored."""
    source = "<!-- pytest-markdown-console: notest -->\n\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.notest is False


def test_unrelated_html_comment_ignored():
    """An HTML comment without the directive prefix does not set any directives."""
    source = "<!-- some other comment -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.notest is False
    assert block.cwd_override is None
    assert block.shell is None


def test_second_block_without_directive():
    """When only the first of two blocks has a directive comment, the second gets defaults."""
    source = "<!-- pytest-markdown-console: notest -->\n```console\n$ echo a\n```\n\n```console\n$ echo b\n```\n"
    block_a, block_b = parse_blocks(source)
    assert block_a.notest is True
    assert block_b.notest is False


def test_old_directive_tag_not_recognised_by_default():
    """The legacy pytest-console: tag is not recognised with the default directive."""
    source = "<!-- pytest-console: notest -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert block.notest is False


def test_custom_directive_recognised():
    """A custom directive string is matched when passed explicitly."""
    source = "<!-- my-project: notest -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source, directive="my-project")[0]
    assert block.notest is True


# ---------------------------------------------------------------------------
# Line number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_line"),
    [
        ("```console\n$ echo hi\n```\n", 1),
        ("# Title\n\n```console\n$ echo hi\n```\n", 3),
        ("\n\n\n```console\n$ echo hi\n```\n", 4),
        ("- item\n\n    ```console\n    $ echo hi\n    ```\n", 3),
    ],
    ids=["first_line", "after_heading", "after_blanks", "indented_fence"],
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
        ('```console\n$ echo "\'#"  # comment\n```\n', 'echo "\'#"', False),
        # '#' inside single quotes also containing a double quote — must not be treated as comment
        ("```console\n$ echo '\"#'  # comment\n```\n", "echo '\"#'", False),
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


# ---------------------------------------------------------------------------
# Indented fences (e.g. inside list items)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_cmd", "expected_output"),
    [
        (
            "1. Step one:\n\n    ```console\n    $ echo hi\n    hi\n    ```\n",
            "echo hi",
            "hi",
        ),
        (
            "- item\n\n  ```console\n  $ echo hi\n  hi\n  ```\n",
            "echo hi",
            "hi",
        ),
    ],
    ids=["indented_4_spaces", "indented_2_spaces"],
)
def test_indented_fence_detected(source, expected_cmd, expected_output):
    """Console blocks indented inside list items are parsed correctly."""
    blocks = parse_blocks(source)
    assert len(blocks) == 1
    cmd = blocks[0].commands[0]
    assert cmd.cmd == expected_cmd
    assert cmd.expected_output == expected_output


def test_indented_fence_multiline_output():
    """Multi-line expected output inside an indented block is de-indented correctly."""
    source = "- item\n\n    ```console\n    $ printf 'a\\nb'\n    a\n    b\n    ```\n"
    blocks = parse_blocks(source)
    assert blocks[0].commands[0].expected_output == "a\nb"


def test_indented_fence_directive():
    """A directive comment before an indented fence is still applied."""
    source = "- item\n\n    <!-- pytest-markdown-console: notest -->\n    ```console\n    $ echo hi\n    ```\n"
    blocks = parse_blocks(source)
    assert blocks[0].notest is True


def test_mixed_indented_and_plain_blocks():
    """A mix of indented and non-indented blocks in the same source are both collected."""
    source = "```console\n$ echo a\n```\n\n- item\n\n    ```console\n    $ echo b\n    ```\n"
    block_a, block_b = parse_blocks(source)
    assert block_a.commands[0].cmd == "echo a"
    assert block_b.commands[0].cmd == "echo b"


# ---------------------------------------------------------------------------
# File-level directives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("directive_tokens", "attr", "expected"),
    [
        ("notest", "notest", True),
        ("cwd:../", "cwd_override", "../"),
        ("shell:pwsh", "shell", "pwsh"),
        ("platform:linux", "only_platforms", frozenset({"linux"})),
        ("platform:!windows", "skip_platforms", frozenset({"windows"})),
    ],
    ids=["notest", "cwd", "shell", "only_platform", "skip_platform"],
)
def test_file_directive_sets_default(directive_tokens, attr, expected):
    """A file-level directive comment sets the default for all blocks in the file."""
    source = f"<!-- pytest-markdown-console-file: {directive_tokens} -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source)[0]
    assert getattr(block, attr) == expected


def test_file_directive_applies_to_all_blocks():
    """File-level defaults propagate to every block in the file."""
    source = (
        "<!-- pytest-markdown-console-file: shell:bash -->\n```console\n$ echo a\n```\n\n```console\n$ echo b\n```\n"
    )
    block_a, block_b = parse_blocks(source)
    assert block_a.shell == "bash"
    assert block_b.shell == "bash"


def test_block_directive_overrides_file_directive():
    """A block-level directive takes precedence over the file-level default."""
    source = (
        "<!-- pytest-markdown-console-file: shell:bash -->\n"
        "<!-- pytest-markdown-console: shell:pwsh -->\n"
        "```console\n$ echo hi\n```\n"
    )
    block = parse_blocks(source)[0]
    assert block.shell == "pwsh"


def test_block_directive_partial_inherits_file_defaults():
    """A block directive for one field still inherits other fields from the file level."""
    source = (
        "<!-- pytest-markdown-console-file: shell:bash cwd:./sub -->\n"
        "<!-- pytest-markdown-console: shell:pwsh -->\n"
        "```console\n$ echo hi\n```\n"
    )
    block = parse_blocks(source)[0]
    assert block.shell == "pwsh"
    assert block.cwd_override == "./sub"


def test_file_directive_anywhere_in_file():
    """A file-level directive comment is recognised wherever it appears in the file."""
    source = (
        "# My Docs\n\n"
        "Some intro text.\n\n"
        "<!-- pytest-markdown-console-file: shell:bash -->\n\n"
        "```console\n$ echo hi\n```\n"
    )
    block = parse_blocks(source)[0]
    assert block.shell == "bash"


def test_file_directive_after_blocks():
    """A file-level directive comment is applied even when it appears after the blocks."""
    source = "```console\n$ echo hi\n```\n\n<!-- pytest-markdown-console-file: shell:bash -->\n"
    block = parse_blocks(source)[0]
    assert block.shell == "bash"


def test_file_directive_first_occurrence_wins():
    """When multiple file-level directives appear, the first one wins."""
    source = (
        "<!-- pytest-markdown-console-file: shell:bash -->\n"
        "<!-- pytest-markdown-console-file: shell:pwsh -->\n"
        "```console\n$ echo hi\n```\n"
    )
    block = parse_blocks(source)[0]
    assert block.shell == "bash"


def test_file_directive_custom_tag():
    """A custom directive tag also controls the -file variant."""
    source = "<!-- my-project-file: shell:bash -->\n```console\n$ echo hi\n```\n"
    block = parse_blocks(source, directive="my-project")[0]
    assert block.shell == "bash"


def test_file_directive_no_effect_without_suffix():
    """A comment matching the block tag (not -file:) does not act as a file directive."""
    source = "<!-- pytest-markdown-console: shell:bash -->\n\n```console\n$ echo hi\n```\n"
    # The blank line above makes the block directive adjacent check fail,
    # so the block should get no shell from either source.
    block = parse_blocks(source)[0]
    assert block.shell is None
