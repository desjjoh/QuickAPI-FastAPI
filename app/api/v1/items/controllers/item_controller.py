from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.items.models.item_model import ItemBase, ItemResponse
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.api.v1.items.services.item_service import ItemService, get_item_service
from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.models.error_model import ErrorResponse
from app.common.models.pagination import PaginatedResult
from app.common.models.parameters_model import EntityId

router: APIRouter = APIRouter(route_class=ApplicationRoute)


## POST /
@router.post(
    "/",
    summary="Create a new item",
    description="Creates a new item using validated input. Returns the fully normalized item resource after persistence.",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
)
@transactional
async def create(
    payload: ItemBase, service: ItemService = Depends(get_item_service)
) -> ItemResponse:
    item = await service.create(payload)

    return ItemResponse.model_validate(item)


## GET /
@router.get(
    "/",
    summary="Get a list of items",
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
    description="Applies a partial update to an existing item. Only provided fields are modified. Returns the updated resource.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
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
    description="Replaces an existing item with the provided data. All fields must be supplied. Returns the updated resource.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
async def replace(
    id: EntityId, payload: ItemBase, service: ItemService = Depends(get_item_service)
) -> ItemResponse:
    item = await service.replace(id, payload)

    return ItemResponse.model_validate(item)


## DELETE /:id
@router.delete(
    "/{id}",
    summary="Delete an item by ID",
    description="Removes an item by its ID. Returns the deleted resource for confirmation. Returns 404 if the item is not found.",
    response_model=ItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No item exists with the provided identifier.",
            "model": ErrorResponse,
        },
    },
)
@transactional
async def delete(
    id: EntityId, service: ItemService = Depends(get_item_service)
) -> ItemResponse:
    item = await service.delete(id)

    return ItemResponse.model_validate(item)
