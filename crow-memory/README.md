# crow-memory

Crow's memory service. A FastAPI HTTP service backed by **LanceDB** with two
resident multivector embedders:

- **ColBERT** (`lightonai/GTE-ModernColBERT-v1`) — text embeddings for messages.
- **ColQwen2 / ColPali** (`vidore/colqwen2-v1.0`) — image embeddings (vision-language
  late-interaction, same MaxSim mechanism as ColBERT).

## Why a service

`query_memory` runs in the *crow-mcp* process while sessions run in *crow-cli*
processes. They are different processes that must share **one** memory store and
**one** copy of ~5GB of models. In-process embedding would load the models per
process and lose shared-memory semantics. So: a service.

## Tables (LanceDB)

| table      | contents                                                        | embedding          |
|------------|-----------------------------------------------------------------|--------------------|
| `prompts`  | id, name, template, created_at                                  | —                  |
| `agents`   | agent_id, session_id, agent_idx, cwd, prompt_args, tools, …     | —                  |
| `messages` | one row = one message (JSON, **images extracted**), token counts | ColBERT (text)     |
| `images`   | image_id (sha256), mime, raw bytes, w, h                        | ColQwen2 (patches) |

Images are **content-addressed** (`sha256` of decoded bytes): free dedupe,
cache-stable, and the message record stays lean (a tiny `image_ref` replaces the
inline base64 blob).

## Image ingest flow

```
message with inline base64 image
  -> decode bytes -> sha256 -> image_id
  -> if new: resize(max_dim) -> ColQwen2 embed -> store {image_id, mime, bytes, w, h, mv} in images
  -> replace inline block with {"type":"image_ref","image_id":...,"mime":...,"w":..,"h":..}
  -> ColBERT embed the (image-free) text -> store message with mv
```

## Measured latency (RTX 3070Ti, 8GB)

- text embed: ~10 ms/doc (sync) · image embed: ~250 ms/image after resize (sync is fine next to an LLM call)
- both models resident: 5.3 GB / 8.2 GB, ~2.9 GB headroom
- search: text→text 18 ms · text→image 44 ms · image→image 19 ms
