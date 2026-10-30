"""Black formatting plus syntax-aware logical spacing: python -m scripts.format_code."""

from __future__ import annotations

import argparse
import ast
import io
import os
import sys
import tokenize
from collections.abc import Sequence
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from typing import cast

from black import format_file_contents
from black.files import parse_pyproject_toml
from black.mode import Mode, TargetVersion
from black.report import NothingChanged

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (ROOT / 'app', ROOT / 'tests', ROOT / 'scripts')
ASSIGNMENTS = (ast.Assign, ast.AnnAssign, ast.AugAssign)
BLOCKS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)
SEPARATED = (ast.Return, ast.Raise, ast.Try, ast.TryStar)
IGNORED_DIRS = {'__pycache__', 'node_modules', 'venv', 'env', 'build', 'dist'}


def protected_lines(source: str) -> set[int]:
    """Read formatter directives as comments, never as text inside strings."""
    protected: set[int] = set()
    disabled: int | None = None

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue

        directive = token.string.lstrip('#').strip()

        if directive == 'fmt: off' and disabled is None:
            disabled = token.start[0]
        elif directive == 'fmt: on' and disabled is not None:
            protected.update(range(disabled, token.end[0] + 1))
            disabled = None
        elif directive == 'fmt: skip':
            protected.add(token.start[0])

    if disabled is not None:
        protected.update(range(disabled, len(source.splitlines()) + 1))

    return protected


def statement_start(statement: ast.stmt) -> int:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return min(
            [statement.lineno, *(item.lineno for item in statement.decorator_list)]
        )

    return statement.lineno


def spaced_source(source: str) -> str:
    """Insert blank lines between sibling statements, without changing their AST."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    protected = protected_lines(source)
    insertions: set[int] = set()

    for node in ast.walk(tree):
        for field, value in ast.iter_fields(node):
            if not isinstance(value, list):
                continue

            statements = [
                item for item in cast(list[object], value) if isinstance(item, ast.stmt)
            ]

            for previous, following in pairwise(statements):
                end = previous.end_lineno
                start = statement_start(following)

                if end is None or start <= end:
                    continue  # Black handles multiple statements on one line.

                # Black owns docstring padding and definition spacing.
                if (
                    field == 'body'
                    and isinstance(
                        node,
                        (
                            ast.Module,
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef,
                        ),
                    )
                    and previous is statements[0]
                    and isinstance(previous, ast.Expr)
                    and isinstance(previous.value, ast.Constant)
                    and isinstance(previous.value.value, str)
                ):
                    continue

                required = (
                    (
                        isinstance(previous, ASSIGNMENTS)
                        and not isinstance(following, ASSIGNMENTS)
                    )
                    or isinstance(previous, BLOCKS)
                    or isinstance(following, SEPARATED)
                )

                if not required or any(
                    line in protected
                    for line in range(
                        previous.lineno, (following.end_lineno or start) + 1
                    )
                ):
                    continue

                if any(not line.strip() for line in lines[end : start - 1]):
                    continue

                # Keep leading comments attached to the next statement/decorator.
                insertion = start - 1

                while insertion > end and lines[insertion - 1].lstrip().startswith('#'):
                    insertion -= 1

                insertions.add(insertion)

    for insertion in sorted(insertions, reverse=True):
        lines.insert(insertion, '\n')

    result = ''.join(lines)

    if ast.dump(tree, include_attributes=False) != ast.dump(
        ast.parse(result), include_attributes=False
    ):
        raise ValueError('Spacing changed Python syntax; refusing to format.')

    return result


def project_mode() -> Mode:
    options = parse_pyproject_toml(str(ROOT / 'pyproject.toml'))

    return Mode(
        line_length=int(options.get('line_length', 88)),
        target_versions={
            TargetVersion[target.upper()]
            for target in options.get('target_version', ['py312'])
        },
        string_normalization=not options.get('skip_string_normalization', False),
    )


def black_source(
    source: str,
    mode: Mode,
    ranges: Sequence[tuple[int, int]] = (),
) -> str:
    try:
        return format_file_contents(source, fast=False, mode=mode, lines=ranges)
    except NothingChanged:
        return source


def format_source(source: str, mode: Mode) -> str:
    newline = '\r\n' if '\r\n' in source else '\n'
    normalized = source.replace('\r\n', '\n')
    initial = black_source(normalized, mode)
    result = black_source(spaced_source(initial), mode)

    if spaced_source(result) != result:
        raise ValueError('Black and spacing rules disagree; refusing to format.')

    return result.replace('\n', newline)


def python_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()

    for path in paths:
        if path.is_symlink():
            raise ValueError(f'Refusing symbolic-link target: {path}')

        if path.is_file() and path.suffix == '.py':
            files.add(path.resolve())
        elif path.is_dir():
            for directory, names, filenames in os.walk(path, followlinks=False):
                names[:] = [
                    name
                    for name in names
                    if not name.startswith('.')
                    and name not in IGNORED_DIRS
                    and not (Path(directory) / name).is_symlink()
                ]

                files.update(
                    (Path(directory) / name).resolve()
                    for name in filenames
                    if name.endswith('.py')
                    and not (Path(directory) / name).is_symlink()
                )
        else:
            raise ValueError(f'Expected an existing Python file or directory: {path}')

    if not files:
        raise ValueError('No Python files selected.')

    return sorted(files)


def line_range(value: str) -> tuple[int, int]:
    try:
        start, end = (int(part) for part in value.split('-', 1))

        if start < 1 or end < start:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(
            'Expected a positive START-END line range.'
        ) from None

    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument(
        '--check',
        action='store_true',
        help='Report formatting differences without writing files.',
    )
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--version', action='store_true')
    parser.add_argument(
        '--line-ranges',
        action='append',
        type=line_range,
        default=[],
        help='Editor selection: preserve Black range formatting; whole-document formatting applies logical spacing.',
    )
    parser.add_argument(
        '--stdin-filename',
        help='Format an editor buffer from stdin; never write its file.',
    )
    args = parser.parse_args()

    if args.version:
        print(f'black, {version("black")} (project logical spacing)')

        return 0

    try:
        mode = project_mode()

        if args.stdin_filename:
            if args.paths != [Path('-')]:
                parser.error('--stdin-filename requires the single input path -')

            source = sys.stdin.buffer.read().decode('utf-8')
            result = (
                black_source(source, mode, args.line_ranges)
                if args.line_ranges
                else format_source(source, mode)
            )

            if args.check:
                return int(source != result)

            sys.stdout.buffer.write(result.encode('utf-8'))

            return 0

        if args.line_ranges:
            parser.error('--line-ranges is only supported with --stdin-filename')

        files = python_files(args.paths or list(DEFAULT_PATHS))
        changes: list[tuple[Path, bytes]] = []

        # Validate every target before writing any formatting changes.
        for path in files:
            raw = path.read_bytes()
            encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)

            try:
                formatted_bytes = format_source(raw.decode(encoding), mode).encode(
                    encoding
                )
            except (SyntaxError, ValueError, tokenize.TokenError) as error:
                raise ValueError(f'{path}: {error}') from error

            if formatted_bytes != raw:
                changes.append((path, formatted_bytes))

        for path, formatted_bytes in changes:
            if not args.check:
                path.write_bytes(formatted_bytes)

            if not args.quiet:
                print(f'{"Would reformat" if args.check else "Reformatted"}: {path}')

        if not args.quiet:
            print(
                f'{len(files)} Python files checked; {len(changes)} formatting changes.'
            )

        return int(args.check and bool(changes))
    except (OSError, SyntaxError, ValueError, tokenize.TokenError) as error:
        print(f'Formatting failed: {error}', file=sys.stderr)

        return 2


if __name__ == '__main__':
    raise SystemExit(main())
