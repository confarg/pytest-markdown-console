# A pytest plugin to test console code blocks in Markdown files


## Installation

In your project, run:

```bash
pip install pytest-markdown-console
```

If you are using `uv`, install it as a development dependency:

```bash
uv add --dev pytest-markdown-console
```

The plugin self-registers and will run in each subsequent `pytest` invocation.


## How does it work?

Each `console` code block in Markdown files collected by the plugin generates a test case.

The test runs each command in the block and compares its actual output to the expected output written in the block.

Take this Markdown file:

````markdown
# README.md

Here is an example of running my app:

```console
$ uv run myapp.py
Hello, world!
```
````

Running pytest with this plugin creates a test case that passes if the app actually prints "Hello, world!".

### Match partial output

Use `...` anywhere in the expected output to match any text in its place, including multiple lines:

````markdown
```console
$ python -c "print(object())"
<object object at 0x...>
```
````

This is useful when part of the output is non-deterministic, such as memory addresses or timestamps, or when the output is very long.


### Signal expected failures

Sometimes you want to illustrate expected failures. To convey this to both the reader and the plugin, place a `# Error: `comment at the end of the failing command, or on the line preceding it:

````markdown
```console
$ uv run myapp.py --bad_option  # Error: this will fail
...
$ # Error: this will also most definitely fail
$ uv run myapp.py --still_bad
...
```
````

To the test case to pass, the command line must fail and the error message produced by the application, if any, must match.

### Filter by platform

To restrict a test to specific platforms, use the `platform:` directive in an HTML comment immediately before the fence:

````markdown
<!-- pytest-markdown-console: platform:linux,macos -->
```console
$ echo "This will generate a test case on Linux and macOS"
```
````

To exclude a platform, prefix its name with `!`:

````markdown
<!-- pytest-markdown-console: platform:!windows -->
```console
$ echo "This will not generate a test case on Windows"
```
````

### Change the working directory

By default, all commands run in the same directory as the Markdown file. To use a different directory, use the `cwd:` directive:

````markdown
<!-- pytest-markdown-console: cwd:../ -->
```console
$ uv run myapp.py
...
```
````

Relative paths are resolved relative to the Markdown file's location.


### Use a temporary directory

Each console block test automatically gets an isolated temporary directory, available as the `tmpdir` environment variable. This is useful when your app writes files during testing:

````markdown
```console
$ uv run myapp.py --logdir "${tmpdir}/logs"
Done.
```
````

You can also use `${tmpdir}` in the `cwd:` directive to run the block's commands inside the temporary directory:

````markdown
<!-- pytest-markdown-console: cwd:${tmpdir} -->
```console
$ uv run myapp.py
$ cat output.txt
Hello, world!
```
````

Each block gets its own dedicated directory, so blocks do not share state through the filesystem.

> **Note for PowerShell users:** In `pwsh` command lines, environment variables use the `$env:` prefix. Reference the directory as `$env:tmpdir` instead of `${tmpdir}`. The `${tmpdir}` syntax in `cwd:` always works regardless of the target shell, since it is expanded by the plugin before the shell runs.


### Use your own fixtures

For more complex setup — seeding a config file, creating a mock, or running any other preparation logic — you can declare pytest fixtures and name them in a `fixtures:` directive. The fixtures run before the block's commands.

The plugin provides a `markdown_console_tmpdir` fixture that returns the block's `tmpdir` as a `pathlib.Path`, so your fixtures can write files that the block can read via `${tmpdir}`:

```python
# conftest.py
import pytest

@pytest.fixture
def write_config(markdown_console_tmpdir):
    (markdown_console_tmpdir / "config.ini").write_text("[settings]\nkey=value\n")
```

````markdown
<!-- pytest-markdown-console: fixtures:write_config -->
```console
$ uv run myapp.py --config "${tmpdir}/config.ini"
Done.
```
````

A fixture can also return a `dict[str, str]` to inject additional environment variables into the block's subprocess. If it returns `None` (or nothing), the return value is ignored:

```python
@pytest.fixture
def inject_env(markdown_console_tmpdir):
    (markdown_console_tmpdir / "seed.db").write_bytes(b"...")
    return {"DB_PATH": str(markdown_console_tmpdir / "seed.db")}
```

Multiple fixtures can be listed, comma-separated:

````markdown
<!-- pytest-markdown-console: fixtures:write_config,inject_env -->
```console
$ uv run myapp.py
Done.
```
````

`yield` fixtures work normally — teardown runs after the block completes.

### Exclude a block from testing

To exclude a block from being collected as a test at all, use the `notest` directive:

````markdown
<!-- pytest-markdown-console: notest -->
```console
$ echo "This block will not be tested"
```
````

### Run hidden blocks

Wrapping a fence in an HTML comment hides it from rendered output (e.g. on GitHub) while
the plugin still finds and runs it. This is useful for setup steps that would clutter the
documentation:

````markdown
<!-- pytest-markdown-console: notest -->
<!--
```console
$ mkdir -p tmp
```
-->
````

To attach a directive to a hidden block, place it on the line immediately before the `<!--`
opener:

````markdown
<!-- pytest-markdown-console: cwd:tmp -->
<!--
```console
$ echo hi
hi
```
-->
````

### Customise the directive tag

By default, directive comments use the `pytest-markdown-console` tag:

````markdown
<!-- pytest-markdown-console: notest -->
```console
$ echo "This block will not be tested"
```
````

You can change this tag via `pyproject.toml`, for example to keep your Markdown source shorter:

```toml
[tool.pytest.ini_options]
markdown_console_directive = "console-test"
```

With the above setting you would write `<!-- console-test: notest -->` instead.

### Control test case runs globally

By default, test cases generated by this plugin are run whenever pytest is invoked. To exclude them entirely:

```bash
pytest -p no:markdown-console
```

To run only the plugin's tests:

```bash
pytest -m markdown_console
```


## Why this plugin?

This plugin makes your documentation testable — specifically `console` blocks — within the same pytest suite you use for the rest of your Python code.

Other tools can test `console` blocks in Markdown files, but we couldn't find one that is simple, supports Windows, integrates with pytest, and requires no boilerplate.

### Does it make sense to test `console` blocks?

Testing `console` blocks is admittedly niche. They often contain installation instructions or shell-specific commands that don't translate across platforms.

However, if you are building a CLI app, you likely already showcase commands and their output in your docs. Testing those snippets ensures they stay up-to-date.

Launching a Python app on Windows, Linux, or macOS is the same one-liner when using `uv`. That is the sweet spot motivating this small plugin.
