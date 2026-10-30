import pytest
from pydantic import TypeAdapter, ValidationError

from app.common.models.version_model import Version, VersionInput

pytestmark = pytest.mark.unit
adapter = TypeAdapter[int](Version)


@pytest.mark.parametrize('value', [1, 1.0, 4294967295, 4294967295.0])
def test_versions_match_express_numeric_integer_semantics(value: int | float) -> None:
    assert adapter.validate_python(value) == int(value)


@pytest.mark.parametrize(
    'value',
    [
        None,
        True,
        False,
        '1',
        '1.0',
        0,
        -1,
        1.5,
        4294967296,
        float('inf'),
        float('nan'),
        [],
        {},
    ],
)
def test_invalid_revision_types_and_ranges_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


def test_version_precondition_has_no_default() -> None:
    with pytest.raises(ValidationError):
        VersionInput.model_validate({})
