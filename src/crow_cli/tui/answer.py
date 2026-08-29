from typing import Literal, NamedTuple


"""
allow_once - Allow this operation only this time
allow_always - Allow this operation and remember the choice
reject_once - Reject this operation only this time
reject_always - Reject this operation and remember the choice
"""


class Answer(NamedTuple):
    """An answer to a question posed by the agent."""

    text: str
    """The textual response."""
    id: str
    """The id of the response."""
    kind: (
        Literal["allow_once", "allow_always", "reject_once", "reject_always"] | None
    ) = None
    """Enumeration to potentially influence UI"""
