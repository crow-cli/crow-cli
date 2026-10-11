#!/usr/bin/env bash
# Install crow's bundled extensions (./bundled-exts.json) into every packaged
# tree under ./vscodium as BUILT-INS.
#
#   ./bundle-exts.sh [os] [arch]     default: linux x64
#
# Built-ins are scanned from a tree's extensions dir at startup, so bundling the
# Jupyter + Python stack this way means the notebook kernel picker and the
# interpreter/environment pickers work with no marketplace install and no
# first-run network -- in the desktop app and in the web build alike.
#
# vsix downloads are cached in .build/exts/, so only the first run (or a version
# bump in the manifest) needs the network. ./build.sh calls this after gulp and
# before --deb, so the .deb carries the extensions too.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

OS_NAME="${1:-linux}"
ARCH="${2:-x64}"
PLATFORM="${OS_NAME}-${ARCH}"
MANIFEST="./bundled-exts.json"
CACHE="./.build/exts"

[[ -f "${MANIFEST}" ]] || { echo "crow-gui: no ${MANIFEST}" >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "crow-gui: bundle-exts.sh needs unzip" >&2; exit 1; }

# Only the trees this build actually produced (a --no-web build has no reh-web,
# reh exists only with --reh).
TARGETS=()
for d in "vscodium/VSCode-${OS_NAME}-${ARCH}/resources/app/extensions" \
         "vscodium/vscode-reh-web-${OS_NAME}-${ARCH}/extensions" \
         "vscodium/vscode-reh-${OS_NAME}-${ARCH}/extensions"; do
  if [[ -d "${d}" ]]; then TARGETS+=("${d}"); fi
done
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "crow-gui: no packaged tree for ${PLATFORM} under ./vscodium — nothing to bundle into" >&2
  exit 1
fi

GALLERY="$(jq -r '.gallery' "${MANIFEST}")"
mkdir -p "${CACHE}"

while read -r id version tp; do
  [[ -n "${id}" ]] || continue
  if [[ "${tp}" == "auto" ]]; then tp="${PLATFORM}"; fi
  ns="${id%%.*}"; name="${id#*.}"
  slug="${id}-${version}${tp:+@${tp}}"
  vsix="${CACHE}/${slug}.vsix"

  if [[ ! -f "${vsix}" ]]; then
    api="${GALLERY}/${ns}/${name}${tp:+/${tp}}/${version}"
    url="$(curl -fsSL "${api}" | jq -r '.files.download // empty')"
    if [[ -z "${url}" ]]; then
      echo "crow-gui: Open VSX has no download for ${slug} (${api})" >&2
      exit 1
    fi
    echo "crow-gui: fetching ${slug}.vsix"
    curl -fsSL --retry 3 -o "${vsix}.part" "${url}"
    mv "${vsix}.part" "${vsix}"
  fi

  # A vsix is a zip whose `extension/` member IS the extension directory.
  stage="$(mktemp -d)"
  unzip -q "${vsix}" 'extension/*' -d "${stage}"
  if [[ ! -f "${stage}/extension/package.json" ]]; then
    echo "crow-gui: ${slug}.vsix has no extension/package.json" >&2
    rm -rf "${stage}"; exit 1
  fi
  for d in "${TARGETS[@]}"; do
    rm -rf "${d:?}/${id}"
    cp -r "${stage}/extension" "${d}/${id}"
  done
  rm -rf "${stage}"
  echo "crow-gui: built-in ${id} ${version}${tp:+ (${tp})} → ${#TARGETS[@]} tree(s)"
done < <(jq -r '.extensions[] | [.id, .version, (.targetPlatform // "")] | @tsv' "${MANIFEST}")
