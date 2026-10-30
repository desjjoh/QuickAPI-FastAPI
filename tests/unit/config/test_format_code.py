import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.format_code import ROOT, format_source, project_mode, python_files

pytestmark = pytest.mark.unit


def formatted(source: str) -> str:
    return format_source(textwrap.dedent(source).lstrip('\n'), project_mode())


def test_assignment_groups_guards_blocks_and_returns_are_separated() -> None:
    source = '''
    async def operation():
        first = 1
        second = 2
        item = await find(first, second)
        if item is None:
            raise LookupError('missing')
        await update(item)
        return item
    '''
    result = formatted(source)

    assert (
        result
        == textwrap.dedent(
            '''
    async def operation():
        first = 1
        second = 2
        item = await find(first, second)

        if item is None:
            raise LookupError('missing')

        await update(item)

        return item
    '''
        ).lstrip('\n')
    )
    assert ast.dump(ast.parse(result)) == ast.dump(ast.parse(textwrap.dedent(source)))
    assert formatted(result) == result


def test_comments_decorators_and_docstrings_remain_attached() -> None:
    result = formatted(
        '''
    def operation():
        """Keep Black's docstring spacing."""
        value = 1
        # Explain the guard, not the preceding assignment.
        if value:
            run()
        # The decorator and function belong together.
        @wrap
        def nested():
            """Nested docstring."""
            return value
        return nested()
    '''
    )

    assert 'value = 1\n\n    # Explain the guard' in result
    assert (
        '# The decorator and function belong together.\n    @wrap\n    def nested'
        in result
    )
    assert '"""Nested docstring."""\n        return value' in result
    assert formatted(result) == result


def test_try_raise_and_compound_clauses_stay_valid() -> None:
    source = '''
    def operation(value):
        log(value)
        try:
            if value:
                run()
            elif value is None:
                stop()
            else:
                skip()
        except LookupError:
            log('error')
            raise
        finally:
            cleanup()
        return value
    '''
    result = formatted(source)

    assert 'log(value)\n\n    try:' in result
    assert "log('error')\n\n        raise" in result
    assert 'cleanup()\n\n    return value' in result
    assert ast.dump(ast.parse(result)) == ast.dump(ast.parse(textwrap.dedent(source)))
    assert formatted(result) == result


def test_multiline_strings_and_formatter_exclusions_are_preserved() -> None:
    source = '''def operation():
    text = """x = 1
# fmt: off
return x
"""
    # fmt: off
    value=1
    if value: run()
    # fmt: on
    other=2  # fmt: skip
    return text
'''
    result = formatted(source)

    assert '"""x = 1\n# fmt: off\nreturn x\n"""' in result
    assert '    value=1\n    if value: run()' in result
    assert '    other=2  # fmt: skip' in result
    assert formatted(result) == result


def test_semicolons_and_one_line_blocks_are_normalized_before_spacing() -> None:
    result = formatted(
        'def operation():\n    first=1; second=2\n    if first: run()\n    return second\n'
    )

    assert 'first = 1\n    second = 2\n\n    if first:' in result
    assert 'run()\n\n    return second' in result
    assert formatted(result) == result


def cli(
    *arguments: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'format_code.py'), *arguments],
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        encoding='utf-8',
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
    )


def test_check_fix_check_cli_preserves_crlf_and_non_ascii(tmp_path: Path) -> None:
    path = tmp_path / 'directory with spaces' / 'sample.py'

    path.parent.mkdir()
    original = 'def f():\r\n    value = "café →"\r\n    return value\r\n'.encode()

    path.write_bytes(original)
    checked = cli('--check', str(path))

    assert checked.returncode == 1 and 'Would reformat' in checked.stdout
    assert path.read_bytes() == original
    fixed = cli(str(path))

    assert fixed.returncode == 0, fixed.stderr
    assert b'\r\n\r\n    return' in path.read_bytes()
    assert 'café →' in path.read_text(encoding='utf-8')
    assert cli('--check', str(path)).returncode == 0


def test_stdin_editor_protocol_formats_without_touching_disk(tmp_path: Path) -> None:
    path = tmp_path / 'buffer.py'

    path.write_text('# original file\n', encoding='utf-8')
    source = 'def f():\n    value = "café →"\n    return value\n'
    result = cli('--stdin-filename', str(path), '-', input_text=source)

    assert result.returncode == 0, result.stderr
    assert result.stdout == formatted(source)
    assert not result.stderr
    assert path.read_text(encoding='utf-8') == '# original file\n'
    assert cli('--version').stdout.startswith('black, ')


def test_invalid_source_fails_without_partially_rewriting_files(tmp_path: Path) -> None:
    good = tmp_path / 'a_good.py'
    bad = tmp_path / 'z_bad.py'
    original = 'def f():\n    value=1\n    return value\n'

    good.write_text(original, encoding='utf-8')
    bad.write_text('def broken(:\n', encoding='utf-8')
    result = cli(str(tmp_path))

    assert result.returncode == 2 and 'Formatting failed' in result.stderr
    assert str(bad) in result.stderr
    assert good.read_text(encoding='utf-8') == original
    assert cli(str(tmp_path / 'missing.py')).returncode == 2


def test_editor_selection_retains_black_range_behavior(tmp_path: Path) -> None:
    path = tmp_path / 'buffer.py'
    source = 'first=1\n\n\ndef f():\n    value=2\n    return value\n'
    result = cli(
        '--line-ranges', '5-6', '--stdin-filename', str(path), '-', input_text=source
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith('first=1\n')
    assert '    value = 2\n    return value' in result.stdout
    assert not path.exists()
    assert (
        cli(
            '--line-ranges',
            '0-2',
            '--stdin-filename',
            str(path),
            '-',
            input_text=source,
        ).returncode
        == 2
    )


def test_file_discovery_excludes_generated_and_environment_directories(
    tmp_path: Path,
) -> None:
    included = tmp_path / 'source.py'

    included.touch()
    for name in ['.venv', '.cache', '__pycache__', 'node_modules', 'build', 'dist']:
        directory = tmp_path / name

        directory.mkdir()
        (directory / 'ignored.py').touch()

    assert python_files([tmp_path, included]) == [included.resolve()]
