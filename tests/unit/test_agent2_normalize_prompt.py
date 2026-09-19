"""What a v2 prompt block becomes on the way to the model (hermetic).

A client attaches something to a prompt for two reasons: a ``ResourceLink`` is
BASELINE — the spec requires every agent to accept text and resource links,
capability or no — and ``initialize`` advertised ``prompt.image`` and
``prompt.embeddedContext`` for the rest.
:func:`crow_cli.agent2.llm.normalize_prompt` is the code that honours all three,
and it is a port: v2 renamed two of v1's blocks and retyped every
``uri`` from ``str`` to ``AnyUrl``. Neither miss raises — the block is dropped
behind an ``except`` that logs, and the model answers as though the attachment
was never sent. From the wire it looks like a model that ignored the user.

Real v2 schema models and real files on disk. No mocks and no network: the one
branch that fetches over http is not the branch the port broke, and a test that
needed a socket to prove a string coercion would be testing the socket.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from acp.experimental.v2 import schema as v2

from crow_cli.agent2.llm import normalize_prompt

# Not a real PNG. Nothing on this path decodes the bytes; they only have to
# survive the trip through a data URL and back out the other side.
B64 = base64.b64encode(b"\x89PNG-not-really").decode()


def make_file(tmp_path: Path, name: str, text: str) -> Path:
    target = tmp_path / name
    target.write_text(text)
    return target


async def test_an_image_block_keeps_the_mime_type_it_arrived_with():
    """``mime_type``, not v1's ``mimeType``.

    Read the wrong one and the lookup returns None, the fallback kicks in, and
    every jpeg the user attaches is announced to the provider as a png.
    """
    out = await normalize_prompt([v2.ImageContentBlock(data=B64, mime_type="image/jpeg")])
    assert out == [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{B64}"}}
    ]


async def test_a_resource_link_becomes_the_file_it_names(tmp_path):
    """The regression this file exists for.

    ``ResourceContentBlock.uri`` is an ``AnyUrl``, ``context_fetcher`` runs a
    regex over it, the ``TypeError`` lands in the ``except``, and the file the
    user attached is dropped with one log line to show for it.
    """
    notes = make_file(tmp_path, "notes.md", "# hello\n\nbody\n")
    out = await normalize_prompt([v2.ResourceContentBlock(name="notes", uri=notes.as_uri())])

    assert len(out) == 1
    assert out[0]["type"] == "text"
    text = out[0]["text"]
    assert text.startswith(str(notes))
    assert "0\t# hello" in text
    assert "2\tbody" in text


async def test_a_resource_link_keeps_its_line_range(tmp_path):
    """``#L2:3`` has to survive being parsed as a URL and printed back out.

    The range grammar is the reason a client sends a link instead of the whole
    file, and a fragment is exactly what a URL parser is most likely to eat.
    """
    source = make_file(tmp_path, "code.py", "one\ntwo\nthree\nfour\n")
    out = await normalize_prompt(
        [v2.ResourceContentBlock(name="code", uri=source.as_uri() + "#L2:3")]
    )

    text = out[0]["text"]
    assert "1\ttwo" in text
    assert "2\tthree" in text
    assert "0\tone" not in text
    assert "3\tfour" not in text


async def test_an_image_named_by_a_uri_is_fetched_and_encoded(tmp_path):
    """The second place the ``AnyUrl`` retyping bit: ``uri.startswith`` raised.

    v2 requires ``data`` on an image block, so this is the empty-data case —
    a client that would rather name the bytes than inline them.
    """
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG-bytes")
    out = await normalize_prompt(
        [v2.ImageContentBlock(data="", mime_type="image/png", uri=shot.as_uri())]
    )

    expected = base64.b64encode(b"\x89PNG-bytes").decode()
    assert out == [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{expected}"}}
    ]


async def test_a_path_with_a_space_survives_the_encoding_round_trip(tmp_path):
    """``str()`` is the right coercion, and it is not a lossy one.

    ``str(AnyUrl)`` percent-encodes what the plain string did not —
    ``file:///.../my%20notes.md`` — and ``uri_to_path`` unquotes on the way
    back, so the file that gets opened is the file that was named.
    """
    notes = make_file(tmp_path, "my notes.md", "spaced\n")
    out = await normalize_prompt([v2.ResourceContentBlock(name="n", uri=notes.as_uri())])

    assert out[0]["text"].startswith(str(notes))
    assert "0\tspaced" in out[0]["text"]


async def test_an_embedded_text_resource_carries_its_location():
    """Embedded context needs no fetch — the payload is in the block.

    The location still travels with the content, which is v1's shape kept: it
    is what lets the model cite the file a passage came from.
    """
    out = await normalize_prompt(
        [
            v2.EmbeddedResourceContentBlock(
                resource=v2.TextResourceContents(
                    uri="file:///etc/hosts", text="127.0.0.1 localhost"
                )
            )
        ]
    )
    assert out == [
        {"type": "text", "text": "file_location:file:///etc/hosts\n127.0.0.1 localhost"}
    ]


async def test_an_embedded_blob_becomes_an_image_only_if_it_is_one():
    """v2 can receive an embedded blob; v1 could not.

    An image becomes an ``image_url``. Anything else is dropped with a warning
    rather than pasted in, because base64 in a text block is a way of spending
    context to say nothing.
    """
    image = await normalize_prompt(
        [
            v2.EmbeddedResourceContentBlock(
                resource=v2.BlobResourceContents(
                    uri="file:///tmp/shot.png", blob=B64, mime_type="image/png"
                )
            )
        ]
    )
    assert image == [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{B64}"}}
    ]

    pdf = await normalize_prompt(
        [
            v2.EmbeddedResourceContentBlock(
                resource=v2.BlobResourceContents(
                    uri="file:///tmp/doc.pdf", blob=B64, mime_type="application/pdf"
                )
            )
        ]
    )
    assert pdf == []


async def test_what_crow_cannot_use_is_dropped_loudly_not_raised(tmp_path, caplog):
    """One bad block costs the block, never the prompt.

    Loudly matters as much as the drop: a client that was told
    ``prompt.embeddedContext`` is supported has no other way to learn that
    crow could not read what it sent.
    """
    missing = tmp_path / "gone.md"
    with caplog.at_level(logging.WARNING, logger="crow_cli.agent2.llm"):
        out = await normalize_prompt(
            [
                v2.AudioContentBlock(data=B64, mime_type="audio/wav"),
                v2.OtherContentBlock(type="crow_something"),
                v2.ResourceContentBlock(name="gone", uri=missing.as_uri()),
                v2.TextContentBlock(text="still here"),
            ]
        )

    assert out == [{"type": "text", "text": "still here"}]
    warnings = [record.getMessage() for record in caplog.records]
    assert any("audio" in line for line in warnings)
    assert any("crow_something" in line for line in warnings)
    assert any("could not fetch resource" in line for line in warnings)


async def test_the_blocks_may_arrive_as_plain_dicts():
    """The duck-typing contract: this module imports no protocol package.

    That is what lets a caller hand it whatever the wire produced, and it is a
    promise the type annotations do not carry — so it is pinned here.
    """
    out = await normalize_prompt(
        [
            {"type": "text", "text": "from a dict"},
            {"type": "image", "data": B64, "mime_type": "image/gif"},
        ]
    )
    assert out == [
        {"type": "text", "text": "from a dict"},
        {"type": "image_url", "image_url": {"url": f"data:image/gif;base64,{B64}"}},
    ]


async def test_a_text_block_with_nothing_in_it_never_reaches_the_api():
    """The API rejects an empty text block, so it is dropped here instead.

    Whitespace-only is kept: whether that counts as empty is the provider's
    call, and ``normalize_blocks`` drops it at request time if it disagrees.
    """
    assert await normalize_prompt([v2.TextContentBlock(text="")]) == []
    assert await normalize_prompt([]) == []
    assert await normalize_prompt(None) == []
