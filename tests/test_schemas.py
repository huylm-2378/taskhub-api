from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas.project import ProjectUpdate
from schemas.tag import TagCreate, TagUpdate


def test_partial_project_update_distinguishes_omitted_and_null():
    assert ProjectUpdate().model_dump(exclude_unset=True) == {}
    assert ProjectUpdate(description=None).model_dump(exclude_unset=True) == {"description": None}
    owner_id = uuid4()
    assert ProjectUpdate(owner_id=str(owner_id)).model_dump(exclude_unset=True) == {"owner_id": owner_id}


@pytest.mark.parametrize("data", [
    {"name": None}, {"name": "  "}, {"name": "x" * 201},
    {"owner_id": None}, {"owner_id": "invalid"}, {"id": str(uuid4())},
])
def test_invalid_project_update(data):
    with pytest.raises(ValidationError):
        ProjectUpdate(**data)


def test_tag_create_and_partial_update():
    assert TagCreate(name=" backend ").name == "backend"
    assert TagUpdate().model_dump(exclude_unset=True) == {}
    assert TagUpdate(name=" urgent ").model_dump(exclude_unset=True) == {"name": "urgent"}
    with pytest.raises(ValidationError):
        TagCreate()


@pytest.mark.parametrize("schema", [TagCreate, TagUpdate])
@pytest.mark.parametrize("data", [{"name": None}, {"name": " "}, {"name": "x" * 51}, {"name": "backend", "id": str(uuid4())}])
def test_invalid_tag_input(schema, data):
    with pytest.raises(ValidationError):
        schema(**data)
