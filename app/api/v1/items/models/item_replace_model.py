from app.api.v1.items.models.item_model import ItemBase
from app.common.models.version_model import VersionInput


class ReplaceItemRequest(ItemBase, VersionInput):
    pass
