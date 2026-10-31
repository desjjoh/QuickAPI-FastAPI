from typing import Annotated

from fastapi import Depends, Query, status

from app.api.v1.items.models.item_model import ItemBase, ItemResponse
from app.api.v1.items.models.item_replace_model import ReplaceItemRequest
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.api.v1.items.services.item_service import ItemService, get_item_service
from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.flexible_router import FlexibleRouter
from app.common.handlers.query_validation import reject_repeated_query_parameters
from app.common.models.error_model import ErrorResponse
from app.common.models.idempotency_model import idempotent
from app.common.models.pagination import PaginatedResult
from app.common.models.parameters_model import EntityId
from app.common.models.version_model import VersionInput

router = FlexibleRouter(route_class=ApplicationRoute)


## POST /


@router.post(
    "",
    summary="Create a new item",
    description="Creates a new item using validated input. Returns the fully normalized item resource after persistence.",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
)
@transactional
@idempotent(operation="items.create")
async def create(
    payload: ItemBase, service: ItemService = Depends(get_item_service)
) -> ItemResponse:
    item = await service.create(payload)

    return ItemResponse.model_validate(item)


## GET /


@router.get(
    "",
    summary="Get a list of items",
    dependencies=[Depends(reject_repeated_query_parameters)],
    description="Retrieves a paginated list of items. Supports page, limit, sorting, and optional filtering.",
    response_model=PaginatedResult[ItemResponse],
    status_code=status.HTTP_200_OK,
)
async def get_all(
    query: Annotated[ItemPaginationQuery, Query()],
    service: ItemService = Depends(get_item_service),
) -> PaginatedResult[ItemResponse]:
    items, count = await service.get_all(query)

    return PaginatedResult[ItemResponse](
        data=[ItemResponse.model_validate(item) for item in items],
        total=count,
        page=query.page,
        limit=query.limit,
    )


## GET /:id


@router.get(
    "/{id}",
    summary="Get a single item by ID",
    description="Fetches a single item by its unique identifier. Returns 404 if the item does not exist.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        }
    },
)
async def get(
    id: EntityId, service: ItemService = Depends(get_item_service)
) -> ItemResponse:
    item = await service.get(id)

    return ItemResponse.model_validate(item)


## PATCH /:id


@router.patch(
    "/{id}",
    summary="Update an item by ID",
    description="Applies a partial update to an existing item. Requires expected_version and an editable field. Only provided fields are modified; each accepted update increments version once.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        409: {
            "description": "Stale item version, in-progress idempotent request, or Idempotency-Key reused with different validated input.",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
@idempotent(operation="items.update")
async def update(
    id: EntityId,
    payload: UpdateItemRequest,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = await service.update(id, payload)

    return ItemResponse.model_validate(item)


## PUT /:id


@router.put(
    "/{id}",
    summary="Replace an item by ID",
    description="Replaces an existing item with the provided data. Requires expected_version, name and price; omitted description becomes null. Each accepted replacement increments version once.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        409: {
            "description": "Stale item version, in-progress idempotent request, or Idempotency-Key reused with different validated input.",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
@idempotent(operation="items.replace")
async def replace(
    id: EntityId,
    payload: ReplaceItemRequest,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = await service.replace(id, payload)

    return ItemResponse.model_validate(item)


## POST /:id/delete


@router.post(
    "/{id}/delete",
    summary="Delete an item by ID",
    description="Requires expected_version in the JSON body. Returns the removed resource with its final version. Stale versions return 409 and missing items return 404.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        409: {
            "description": "Stale item version, in-progress idempotent request, or Idempotency-Key reused with different validated input.",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
@idempotent(
    operation="items.delete",
)
async def delete(
    id: EntityId,
    payload: VersionInput,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = await service.delete(id, payload)

    return ItemResponse.model_validate(item)
