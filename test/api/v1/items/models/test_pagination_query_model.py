import os
import unittest

os.environ.setdefault("APP_NAME", "QuickAPI")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")

from app.api.v1.items.models.pagination_query_model import (
    ItemPaginationQuery,
)
from app.common.models.converter import model_to
from app.database.repositories.item_repo import (
    ItemListQuery,
    ItemSort,
    SortOrder,
)


class ItemPaginationQueryTests(unittest.TestCase):
    def test_converts_default_query_to_repository_query(self) -> None:
        query = ItemPaginationQuery()

        result = model_to(ItemListQuery, query)

        self.assertEqual(
            result,
            ItemListQuery(
                limit=20,
                offset=0,
                search=None,
                sort=ItemSort.PRICE,
                order=SortOrder.asc,
                min_price=None,
                max_price=None,
            ),
        )

    def test_converts_page_to_database_offset(self) -> None:
        query = ItemPaginationQuery(page=3, limit=10, sort="created_at")

        result = model_to(ItemListQuery, query)

        self.assertEqual(result.offset, 20)
        self.assertEqual(result.sort, ItemSort.CREATED_AT)


if __name__ == "__main__":
    unittest.main()
