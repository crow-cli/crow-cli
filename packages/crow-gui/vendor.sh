#!/usr/bin/env bash
# Re-create ./vscodium from upstream VSCodium at the pinned commit, then replay
# crow's modifications to the pipeline (crow-patches/vscodium-pipeline.patch).
#
#   ./vendor.sh                       clone VSCodium from GitHub (needs network)
#   ./vendor.sh /path/to/vscodium     use an existing local clone
#   ./vendor.sh <clone> --diff        show pristine vs. current ./vscodium
#   ./vendor.sh <clone> --make-patch  regenerate crow-patches/vscodium-pipeline.patch
#                                     from the current ./vscodium (run after editing
#                                     the vendored pipeline, then commit both)
#
# Plain `./vendor.sh` DELETES ./vscodium and rebuilds it, so an edit made
# directly inside ./vscodium is lost unless --make-patch captured it first.
#
# Bumping the pin: change VSCODIUM_COMMIT, re-run, fix the hunks that no longer
# apply, --make-patch, commit.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
HERE="$(pwd)"
PATCH_FILE="${HERE}/crow-patches/vscodium-pipeline.patch"

# VSCodium/vscodium @ 5b01560 — pins VS Code 1.135.0 (upstream/stable.json).
VSCODIUM_COMMIT="5b01560f8419b3cbbe4b1aa0ce07183ef8c45b0f"
VSCODIUM_REPO="https://github.com/VSCodium/vscodium.git"

SRC=""
MODE="vendor"
for arg in "$@"; do
  case "${arg}" in
    --diff)       MODE="diff" ;;
    --make-patch) MODE="make-patch" ;;
    -*)           echo "vendor.sh: unknown flag ${arg}" >&2; exit 2 ;;
    *)            SRC="${arg}" ;;
  esac
done

if [[ "${MODE}" != "vendor" && -z "${SRC}" ]]; then
  echo "vendor.sh: --diff/--make-patch need a pristine VSCodium clone path" >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

if [[ -n "${SRC}" ]]; then
  [[ -e "${SRC}/.git" ]] || { echo "vendor.sh: ${SRC} is not a git clone" >&2; exit 1; }
  git -C "${SRC}" cat-file -e "${VSCODIUM_COMMIT}^{commit}" 2>/dev/null || {
    echo "vendor.sh: ${SRC} does not contain ${VSCODIUM_COMMIT}" >&2; exit 1; }
  git -C "${SRC}" archive "${VSCODIUM_COMMIT}" | tar -x -C "${TMP}" --one-top-level=tree
else
  echo "vendor.sh: cloning ${VSCODIUM_REPO} (blobless)"
  git clone --filter=blob:none --no-checkout "${VSCODIUM_REPO}" "${TMP}/clone"
  git -C "${TMP}/clone" archive "${VSCODIUM_COMMIT}" | tar -x -C "${TMP}" --one-top-level=tree
fi
# crow builds the stable channel only; src/insider is 15MB of installer bitmaps.
rm -rf "${TMP}/tree/src/insider"
TREE="${TMP}/tree"

case "${MODE}" in
  diff)
    diff -ruN "${TREE}" "${HERE}/vscodium" || true
    exit 0
    ;;
  make-patch)
    : > "${PATCH_FILE}"
    # diff/git-diff exit 1 when they FIND differences, which set -e + pipefail
    # would treat as failure; both are wrapped so only real errors abort.
    { diff -rq "${TREE}" "${HERE}/vscodium" || true; } | while IFS= read -r line; do
      case "${line}" in
        'Files '*' and '*' differ')
          rel="${line#Files }"; rel="${rel%% and *}"
          rel="${rel#"${TREE}/"}"
          { git --no-pager diff --no-index "${TREE}/${rel}" "${HERE}/vscodium/${rel}" || true; } \
            | sed -e "s|^diff --git .*|diff --git a/${rel} b/${rel}|" \
                  -e "s|^--- .*|--- a/${rel}|" \
                  -e "s|^+++ .*|+++ b/${rel}|" \
            >> "${PATCH_FILE}"
          echo "vendor.sh: captured ${rel}"
          ;;
        *)
          echo "vendor.sh: NOT captured (add/remove by hand): ${line}" >&2
          ;;
      esac
    done
    echo "vendor.sh: wrote ${PATCH_FILE} ($(wc -l < "${PATCH_FILE}") lines)"
    exit 0
    ;;
esac

rm -rf "${HERE}/vscodium"
mv "${TREE}" "${HERE}/vscodium"
cd "${HERE}/vscodium"
git apply --stat ../crow-patches/vscodium-pipeline.patch
git apply ../crow-patches/vscodium-pipeline.patch
echo "vendor.sh: vscodium/ re-created at ${VSCODIUM_COMMIT:0:7} + crow pipeline patch"
