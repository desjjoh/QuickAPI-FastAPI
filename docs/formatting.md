# Python formatting and spacing

[Documentation index](../README.md#documentation)

## Commands

Activate the Python 3.12 virtual environment and install `requirements-dev.txt`.

```powershell
# Format the application, tests and scripts.
python -m scripts.format_code

# Check the same files without changing them; CI uses this command.
python -m scripts.format_code --check

# Format a specific file or directory.
python -m scripts.format_code app/api/v1/items
```

The formatter combines the pinned Black version with logical blank-line rules.
It reads the project's Black line-length, Python target and string-normalization
settings from `pyproject.toml`. Black handles layout first, logical spacing follows,
and Black runs again to verify a consistent result. Repeated formatting produces
no further changes. Ruff remains the separate import/code-quality check.

## Logical separation

The policy follows the intent of Express and NestJS statement-padding rules while
retaining Python syntax and Black's definition/docstring conventions:

- Keep consecutive assignments together.
- Separate an assignment group from a following operation or guard.
- Separate a completed control-flow block from its next sibling statement.
- Separate `return`, `raise`, `try` and `try*` statements from preceding work.
- Do not add padding before the first statement of a block or after its docstring.

```python
async def get(self, id: HexId) -> ItemORM:
    item = await repo.get_by_id(self.db, id)

    if item is None:
        raise HTTPException(404, f"Resource with ID '{id}' not found")

    return item
```

The checker uses Python statement boundaries, rather than text patterns. It keeps
comments attached to guards/decorators, preserves strings and respects `# fmt: off`,
`# fmt: on` and `# fmt: skip`. A single `raise` inside a guard does not acquire an
extra blank line before it. Compound clauses such as `elif`, `else`, `except` and
`finally` remain attached to their statement.

## Editor integration

The checked-in VS Code settings route the Black Formatter extension through
`scripts/format_code.py`, using the repository's `.venv` interpreter. **Format
Document and format-on-save apply both Black and logical spacing.** Install the
recommended Python, Black Formatter and Ruff extensions. Reload VS Code if an
already-running formatter server has not picked up the changed configuration.

The repository's interpreter settings target Windows. On POSIX, use
`${workspaceFolder}/.venv/bin/python` in both `python.defaultInterpreterPath` and
the first entry of `black-formatter.path`.

Format Selection preserves Black's existing line-range behavior; the full logical
spacing policy runs on document formatting/save. This avoids changing unrelated
statements outside the selected range. The stdin adapter writes only the formatted
buffer to stdout and does not modify the file on disk.

## Scope and enforcement

Default targets are `.py` files under `app`, `tests` and `scripts`, including the
checked-in migration code. Directory discovery skips hidden directories,
environments, caches, build output and `node_modules`; it does not follow symbolic
links. Explicit file/directory arguments let a developer narrow the run.

`--check` exits with 1 for formatting differences. Invalid input or formatting
failure exits with 2. File formatting validates every selected source before writing
changes, preserves its encoding and newline style, and verifies that logical padding
does not alter its syntax tree. Existing valid `# fmt:` exclusions remain available
for deliberate formatting exceptions.

The `Quality / static-analysis` job runs the combined formatter check before Ruff
and mypy. Cramped statements therefore fail CI even when Black alone accepts them.

## Verification

```powershell
python -m pytest -q tests/unit/config/test_format_code.py --no-cov
python -m scripts.format_code --check
```

Tests cover assignment/guard/return spacing, compound clauses, comments, decorators,
docstrings, multiline strings, formatter exclusions, syntax preservation,
idempotence, check/fix exit codes, invalid input without partial rewrites, file
discovery, Unicode, CRLF and the editor stdin/selection protocols.
