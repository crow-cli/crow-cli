# PLAN — image object store sprint (RustFS/S3 with FS fallback)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Build/test (ALL tiers mandatory, every run):

    cd /home/thomas/src/crow-team/crow-cli
    uv --project . run pytest tests -q

Every commit ends with the agent's `Session-Id:` trailer. Scope capture +
user quotes: TODO.md. Trajectory: 1 → 2 → 3 → 4.

One-liner: images move from content-addressed files to an S3 endpoint
(RustFS, shipped in compose.yaml) WHEN that endpoint is reachable; probe at
init, fall back to the current filesystem store otherwise; reads fall back
to FS so legacy images never break.

---

## Phase 1 — RustFS compose in defaults.py + init wiring — DONE 2026-08-25

- 1.1 Add the user-supplied RustFS compose (rustfs + volume-permission-helper
      services, rustfs_data_0..3 + logs volumes, rustfs-network) to
      `COMPOSE_YAML` in config/default/defaults.py. Deviation from supplied
      text: credentials as `${RUSTFS_ACCESS_KEY}` / `${RUSTFS_SECRET_KEY}`
      env refs instead of hardcoded `rustfsadmin` (house pattern; .env is
      chmod 600).
- 1.2 init_cmd.py: `setup_rustfs` gate mirroring setup_searxng (flag →
      env-var sniff → interactive Confirm.ask); RUSTFS_ACCESS_KEY/SECRET_KEY
      into env_vars (default rustfsadmin/rustfsadmin, prompt to change);
      compose writer must also carry `networks:` when rustfs is active.
- 1.3 config.py file-template map stays correct (compose.yaml → COMPOSE_YAML).
- Verify: unit suite green; new unit test — init with setup_rustfs renders
  compose.yaml containing rustfs service + 4 volumes + network; credentials
  land in .env not compose.
- Evidence: tests/unit/test_init_rustfs.py (template parse + run_init yes-mode
  rendering: compose has rustfs+helper+network+volumes, keys in .env only,
  config.yaml image_store.s3 block with env refs). 439 passed. GOTCHA: the
  healthcheck shell needs `\\"` in the Python template (YAML escaped quotes
  inside the flow sequence) — plain `"` terminates the scalar.

## Phase 2 — ImageStore seam, FS behavior unchanged — DONE 2026-08-25

- 2.1 New `src/crow_cli/memory/image_store.py`: `ImageStore` protocol
      (put(key, data) / get(key) -> bytes|None / exists(key));
      `FsImageStore(images_dir)` = exact current file logic.
- 2.2 `extract_images` / `hydrate_message` take `store: ImageStore`
      (keep images_dir param working via FsImageStore wrap if cheap, else
      update all call sites: writes.py, reads.py, agent/memory.py).
- 2.3 `agent/memory.py` MemoryClient resolves `self.image_store` where it
      resolves images_dir today.
- Verify: FULL suite green — this phase is a pure refactor; any image test
  failing means behavior changed. Round-trip test through FsImageStore.
- Evidence: memory/image_store.py (ImageStore protocol + FsImageStore);
  extract_images/hydrate_message take the store; writes/reads/agent-memory
  thread `store=`; test_store.py round-trip + dedupe green through the seam.
  439 passed. image_ref "path" field KEPT as the key (DB compat).

## Phase 3 — S3 store + probe/fallback + config — DONE 2026-08-25

- 3.1 boto3 dependency; `S3ImageStore(endpoint, bucket, access_key,
      secret_key)` — head_bucket probe (~2s timeout), create bucket if 404,
      put/get/exists; sync calls wrapped via asyncio.to_thread at async call
      sites.
- 3.2 config.yaml `image_store.s3:` block (endpoint/bucket/access_key/
      secret_key, ${ENV} expansion like other secrets); Config dataclass
      parses it; absent block = FS only.
- 3.3 resolve_image_store(cfg): s3 configured + probe OK → S3 (with FS
      read-fallback wrapper); probe fails → FsImageStore + logged warning.
      Decision logged ONCE at init.
- Verify: unit green incl. moto-backed S3 round-trip (mock justified:
  network service); fallback test — configured but dead endpoint →
  FsImageStore chosen; hybrid read — object only in FS still hydrates.
- Evidence: tests/memory/test_image_store.py — 7 green against a REAL local
  S3 (moto ThreadedMotoServer; mock_aws does NOT intercept custom
  endpoint_url — verified). S3ImageStore probes via head_bucket, creates
  bucket on 404; resolve_image_store logs the decision once; MemoryClient
  add_message/load wrapped in asyncio.to_thread (S3 = network I/O);
  apply_config_overrides expands ${RUSTFS_*} refs. boto3 dep added.
  446 passed.

## Phase 4 — live e2e + docs

- 4.1 Real rustfs container (docker run SNSD or compose up in tmp config
      dir); MemoryClient save message-with-image → object in bucket; load +
      hydrate → identical base64; kill container → next init falls back FS.
      Script lives in scripts/ (like e2e_memory_live.py), committed.
- 4.2 config.yaml template comment for image_store; README note;
      CONFIG_YAML in defaults.py updated.
- Verify: script passes against live container; full suite green; commit.
