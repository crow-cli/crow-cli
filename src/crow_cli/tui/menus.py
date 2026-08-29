from typing import NamedTuple


class MenuItem(NamedTuple):
    """An entry in a Menu."""

    description: str
    action: str | None
    key: str | None = None


CONVERSATION_MENUS: dict[str, list[MenuItem]] = {
    "fence": [MenuItem("Run this code", "run", "r")]
}
