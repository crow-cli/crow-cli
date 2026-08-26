# TODO — image object store sprint (RustFS/S3 with FS fallback)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Unordered scope capture. Ordered execution lives in PLAN.md.

## The ask (user's words)

- "basically I just use boto3 with a custom URL is what I am hearing. set up
  rustfs in our compose.yaml. use that instead of filesystem."
- "can we have it set up to check if there's an s3 and if there's not to fall
  back to the current filesystem approach? let's scope that."
- "We have a compose.yaml in config/default/defaults.py ... let's add this"
  (user supplied the full RustFS compose — single node, 4 volumes,
  `RUSTFS_VOLUMES=/data/rustfs{0...3}`, console on 9001,
  volume-permission-helper, healthchecks).
- RustFS chosen over libreFS/Garage/SeaweedFS: Apache 2.0, real velocity
  (1.0.0-rc.3-preview.2 as of 2026-08-21), MinIO CE archived Dec 2025.

## Current design being replaced (verified)

`memory/messages.py`: inline base64 image blocks → extracted at write time to
`<images_dir>/<sha256hex><ext>` (content-addressed, free dedupe); sqlite
stores `image_ref` blocks; `hydrate_message` swaps refs back to data URLs at
read time. `images_dir` resolved in `agent/memory.py` (db parent / "images",
or config_dir/"images" for non-file backends).

## Items

- [x] Add the user-supplied RustFS compose to `COMPOSE_YAML` in
      config/default/defaults.py; wire init_cmd selective include (flag like
      setup_searxng), .env keys RUSTFS_ACCESS_KEY/RUSTFS_SECRET_KEY.
      Credentials via env vars, NOT hardcoded (house pattern: DASHSCOPE_API_KEY).
      (2026-08-25: done — tests/unit/test_init_rustfs.py, 439 green.)
- [ ] Extract `ImageStore` seam (put/get/exists) in memory/; FsImageStore =
      current behavior, zero change. Thread store through extract_images /
      hydrate_message / MemoryClient in place of images_dir.
- [ ] S3ImageStore (boto3, custom endpoint_url) + config.yaml `image_store.s3`
      block (endpoint/bucket/access_key/secret_key).
- [ ] Probe-and-fallback: config has s3 → head_bucket probe (~2s) → S3 if up,
      FS if down/absent. Log the decision.
- [ ] Hybrid READ: get() tries S3 then FS, so legacy FS images survive the
      switch with zero migration. Write path = chosen backend only.
- [ ] Bucket bootstrap: create `crow-images` if missing.
- [ ] boto3 is sync in an async codebase — wrap in asyncio.to_thread at the
      async call sites (save_message/load paths are async).
- [ ] Tests: store seam round-trip (FS real, S3 via moto — mock justified:
      network service), probe/fallback with dead endpoint, init_cmd compose
      rendering, live e2e vs real rustfs container (integration tier).
- [ ] Docs: config.yaml template comment for image_store; README note.

## Decisions (locked)

- Key format unchanged: `<sha256hex><ext>`; bucket `crow-images`.
- Backend choice logged once at MemoryClient init; no per-call probing.
- SNSD/4-vol single-node compose as supplied = erasure coding within the node.
- No migration of existing FS images — hybrid read covers them forever.
