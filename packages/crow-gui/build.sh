#!/usr/bin/env bash
# Build crow's IDE ("crowdium"): the desktop app and the web server, from the
# vendored VSCodium pipeline in ./vscodium with crow's branding from ./crow.env.
#
#   ./build.sh                desktop app + web server (linux x64, stable pin)
#   ./build.sh --arch arm64
#   ./build.sh --no-web       desktop app only
#   ./build.sh --reh          also build the remote/ssh server (reh)
#   ./build.sh --latest       track newest upstream VS Code instead of the pin
#   ./build.sh --assets       also roll release tarballs into vscodium/assets/
#   ./build.sh --prepare-only fetch + patch + npm ci, stop before gulp
#   ./build.sh --fresh        delete vscodium/vscode/ and start the checkout over
#
# Artifacts land in ./vscodium (all gitignored there):
#   VSCode-linux-<arch>/            desktop app; bin/crow launches Electron
#   vscode-reh-web-linux-<arch>/    web server; bin/crow-server serves it
#   vscode-reh-linux-<arch>/        remote server (--reh only)
#   assets/*.tar.gz                 (--assets only)
#
# First run needs network (npm ci, cargo, electron/reh deps) and takes a while;
# a rebuild after a source change is mostly gulp. Requires: bash, git, jq, node
# + npm matching vscode/.nvmrc, python3, libx11/libxkbfile/libsecret headers,
# and rustup + cargo for the CLI.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
HERE="$(pwd)"

ARCH="x64"
BUILD_OS="${OS_NAME:-linux}"
REH="no"
REH_WEB="yes"
ASSETS="no"
PREPARE_ONLY="no"
FRESH="no"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--arch)      ARCH="$2"; shift 2 ;;
    --os)           BUILD_OS="$2"; shift 2 ;;
    --reh)          REH="yes"; shift ;;
    --no-web)       REH_WEB="no"; shift ;;
    --latest)       export VSCODE_LATEST=yes; shift ;;
    --assets)       ASSETS="yes"; shift ;;
    --prepare-only) PREPARE_ONLY="yes"; shift ;;
    --fresh)        FRESH="yes"; shift ;;
    -h|--help)      sed -n '2,23p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)              echo "crow-gui: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# shellcheck source=./crow.env
source ./crow.env

# vscode/.nvmrc is a hard contract (node 24.x for this pin) but
# prepare_vscode.sh exports VSCODE_SKIP_NODE_VERSION_CHECK on linux, so a wrong
# node fails deep inside gulp instead of up front. Check here, and switch via
# fnm when it is available.
REQUIRED_NODE="$(cat vscodium/.nvmrc)"
CURRENT_NODE="$(node -v 2>/dev/null || echo none)"
if [[ "${CURRENT_NODE#v}" != "${REQUIRED_NODE}" ]]; then
  if command -v fnm >/dev/null 2>&1; then
    eval "$(fnm env)"
    fnm install "${REQUIRED_NODE}" >/dev/null 2>&1 || true
    fnm use "${REQUIRED_NODE}" >/dev/null
    echo "crow-gui: node $(node -v) (fnm; .nvmrc wants ${REQUIRED_NODE})"
  else
    echo "crow-gui: node is ${CURRENT_NODE} but vscodium/.nvmrc wants v${REQUIRED_NODE}." >&2
    echo "  install fnm, or put node v${REQUIRED_NODE} on PATH, and re-run." >&2
    exit 1
  fi
fi

export SHOULD_BUILD=yes
export CI_BUILD=no
export OS_NAME="${BUILD_OS}"
export VSCODE_ARCH="${ARCH}"
export VSCODE_QUALITY=stable
export SHOULD_BUILD_REH="${REH}"
export SHOULD_BUILD_REH_WEB="${REH_WEB}"
export MAX_OLD_SPACE_SIZE="${MAX_OLD_SPACE_SIZE:-8192}"

# The pinned VS Code commit is a ~340MB fetch from GitHub. Seed it from a local
# clone instead when one has the commit: CROW_VSCODE_SRC=<path> forces a source,
# otherwise a sibling vscode/ checkout in the workspace is used if it matches.
if [[ -n "${CROW_VSCODE_SRC:-}" ]]; then
  export VSCODE_ORIGIN="${CROW_VSCODE_SRC}"
  echo "crow-gui: vscode source ${VSCODE_ORIGIN} (CROW_VSCODE_SRC)"
elif [[ -z "${VSCODE_ORIGIN:-}" && "${VSCODE_LATEST:-no}" != "yes" ]]; then
  PINNED_COMMIT="$(jq -r '.commit' vscodium/upstream/stable.json)"
  for candidate in "${HERE}/../../vscode" "${HOME}/src/crow-gui/vscode"; do
    [[ -e "${candidate}/.git" ]] || continue
    if git -C "${candidate}" cat-file -e "${PINNED_COMMIT}^{commit}" 2>/dev/null; then
      export VSCODE_ORIGIN="$(cd "${candidate}" && pwd)"
      echo "crow-gui: vscode source ${VSCODE_ORIGIN} @ ${PINNED_COMMIT:0:9} (local clone)"
      break
    fi
  done
fi

# The vendored pipeline reads many optional variables (RELEASE_VERSION,
# SHOULD_BUILD_CLI, npm_config_arch, …) and uses grep-in-pipeline, so it is not
# written for `set -u`/pipefail. Everything above keeps them; the sourced stages
# below do not.
set +u
set +o pipefail

cd vscodium

if [[ "${FRESH}" == "yes" && -d vscode ]]; then
  echo "crow-gui: --fresh — deleting vscode/ ($(du -sh vscode | cut -f1))"
  rm -rf vscode
fi

# get_repo.sh cannot run over an existing vscode/ (it git-inits and re-adds the
# remote), and prepare_vscode.sh cannot patch a tree twice, so resume from a
# prepared checkout when there is one. --fresh starts over.
if [[ -f vscode/.crow-prepared ]]; then
  export RELEASE_VERSION="$(cat vscode/.crow-prepared)"
  export MS_COMMIT="$(git -C vscode rev-parse HEAD)"
  export MS_TAG="$(jq -r '.tag' "upstream/${VSCODE_QUALITY}.json")"
  echo "crow-gui: reusing prepared vscode/ @ ${MS_COMMIT:0:9} (${RELEASE_VERSION})"
else
  # shellcheck disable=SC1091
  . ./get_repo.sh
  echo "crow-gui: RELEASE_VERSION=${RELEASE_VERSION} MS_TAG=${MS_TAG} MS_COMMIT=${MS_COMMIT:0:9}"
fi

if [[ "${PREPARE_ONLY}" == "yes" ]]; then
  # shellcheck disable=SC1091
  . ./prepare_vscode.sh
  echo "${RELEASE_VERSION}" > vscode/.crow-prepared   # so a later run resumes
  echo "crow-gui: prepared vscodium/vscode (patched, npm ci done) — stopping before gulp"
  exit 0
fi

# shellcheck disable=SC1091
. ./build.sh

if [[ "${ASSETS}" == "yes" ]]; then
  # CI_BUILD=yes keeps stores/snapcraft out of it; deb/rpm need packaging tools
  # crow does not require, the tarballs are what `crow-cli install crow` wants.
  (
    export CI_BUILD=yes SHOULD_BUILD_DEB=no SHOULD_BUILD_RPM=no SHOULD_BUILD_TAR=yes
    # shellcheck disable=SC1091
    . ./prepare_assets.sh
  )
fi

echo
echo "crow-gui: build complete"
echo "  desktop app : vscodium/VSCode-${VSCODE_PLATFORM:-linux}-${VSCODE_ARCH}/bin/${BINARY_NAME}"
if [[ "${SHOULD_BUILD_REH_WEB}" != "no" ]]; then
  echo "  web server  : vscodium/vscode-reh-web-${VSCODE_PLATFORM:-linux}-${VSCODE_ARCH}/bin/${BINARY_NAME}-server"
fi
if [[ "${SHOULD_BUILD_REH}" != "no" ]]; then
  echo "  remote srv  : vscodium/vscode-reh-${VSCODE_PLATFORM:-linux}-${VSCODE_ARCH}/bin/${BINARY_NAME}-server"
fi
[[ "${ASSETS}" == "yes" ]] && echo "  assets      : vscodium/assets/"
exit 0
