#!/usr/bin/env bash

APP_NAME="${APP_NAME:-VSCodium}"
APP_NAME_LC="$( echo "${APP_NAME}" | awk '{print tolower($0)}' )"
ASSETS_REPOSITORY="${ASSETS_REPOSITORY:-VSCodium/vscodium}"
BINARY_NAME="${BINARY_NAME:-codium}"
GH_REPO_PATH="${GH_REPO_PATH:-VSCodium/vscodium}"
ORG_NAME="${ORG_NAME:-VSCodium}"
TUNNEL_APP_NAME="${TUNNEL_APP_NAME:-"${BINARY_NAME}-tunnel"}"

# crow: branding-derived URLs/identifiers. Defaults keep VSCodium behaviour;
# a downstream brand (see packages/crow-gui/crow.env) exports its own.
SITE_URL="${SITE_URL:-https://vscodium.com}"
REPO_URL="${REPO_URL:-https://github.com/${GH_REPO_PATH}}"
LICENSE_URL="${LICENSE_URL:-${REPO_URL}/blob/master/LICENSE}"
REPORT_ISSUE_URL="${REPORT_ISSUE_URL:-${REPO_URL}/issues/new}"
UPDATE_URL="${UPDATE_URL:-https://raw.githubusercontent.com/VSCodium/versions/refs/heads/master}"
DARWIN_BUNDLE_IDENTIFIER="${DARWIN_BUNDLE_IDENTIFIER:-com.${APP_NAME_LC}}"

if [[ "${VSCODE_QUALITY}" == "insider" ]]; then
  GLOBAL_DIRNAME="${GLOBAL_DIRNAME:-"${APP_NAME_LC}"}-insiders"
else
  GLOBAL_DIRNAME="${GLOBAL_DIRNAME:-"${APP_NAME_LC}"}"
fi

# All common functions can be added to this file

apply_actions() {
  jq -c '.[]' "$1" | while IFS= read -r ENTRY; do
    ENTRY_ACTION=$( jq -r '.action // empty' <<< "${ENTRY}" )

    case "${ENTRY_ACTION}" in
      remove)
        jq -r '.paths[]' <<< "${ENTRY}" | while IFS= read -r ENTRY_PATH; do
          ENTRY_PATH="${ENTRY_PATH%$'\r'}"

          if [[ -e "${ENTRY_PATH}" ]]; then
            if rm -rf -- "${ENTRY_PATH}"; then
              echo "Removed: ${ENTRY_PATH}"
            else
              echo "Failed to remove: ${ENTRY_PATH}" >&2
              exit 4
            fi
          else
            echo "Not found: ${ENTRY_PATH}" >&2
            exit 4
          fi
        done
      ;;
    esac
  done
}

apply_patch() {
  if [[ -z "$2" ]]; then
    echo applying patch: "$1";
  fi
  # grep '^+++' "$1"  | sed -e 's#+++ [ab]/#./vscode/#' | while read line; do shasum -a 256 "${line}"; done

  cp $1{,.bak}

  replace "s|!!APP_NAME!!|${APP_NAME}|g" "$1"
  replace "s|!!APP_NAME_LC!!|${APP_NAME_LC}|g" "$1"
  replace "s|!!ASSETS_REPOSITORY!!|${ASSETS_REPOSITORY}|g" "$1"
  replace "s|!!BINARY_NAME!!|${BINARY_NAME}|g" "$1"
  replace "s|!!GH_REPO_PATH!!|${GH_REPO_PATH}|g" "$1"
  replace "s|!!GLOBAL_DIRNAME!!|${GLOBAL_DIRNAME}|g" "$1"
  replace "s|!!ORG_NAME!!|${ORG_NAME}|g" "$1"
  replace "s|!!RELEASE_VERSION!!|${RELEASE_VERSION}|g" "$1"
  replace "s|!!TUNNEL_APP_NAME!!|${TUNNEL_APP_NAME}|g" "$1"

  if ! git apply --ignore-whitespace "$1"; then
    echo failed to apply patch "$1" >&2
    exit 1
  fi

  mv -f $1{.bak,}
}

exists() { type -t "$1" &> /dev/null; }

is_gnu_sed() {
  sed --version &> /dev/null
}

replace() {
  if is_gnu_sed; then
    sed -i -E "${1}" "${2}"
  else
    sed -i '' -E "${1}" "${2}"
  fi
}

if ! exists gsed; then
  if is_gnu_sed; then
    function gsed() {
      sed -i -E "$@"
    }
  else
    function gsed() {
      sed -i '' -E "$@"
    }
  fi
fi
