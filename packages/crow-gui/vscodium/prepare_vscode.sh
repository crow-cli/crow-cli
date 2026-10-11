#!/usr/bin/env bash
# shellcheck disable=SC1091,2154

set -e

if [[ "${VSCODE_QUALITY}" == "insider" ]]; then
  cp -rp src/insider/* vscode/
else
  cp -rp src/stable/* vscode/
fi

cp -f LICENSE vscode/LICENSE.txt

cd vscode || { echo "'vscode' dir not found"; exit 1; }

{ set +x; } 2>/dev/null

# crow: the branding vars (APP_NAME, BINARY_NAME, *_URL…) are needed by the
# product.json block below, so utils.sh is sourced here instead of further down.
. ../utils.sh

# {{{ product.json
cp product.json{,.bak}

setpath() {
  local jsonTmp
  { set +x; } 2>/dev/null
  jsonTmp=$( jq --arg 'value' "${3}" "setpath(path(.${2}); \$value)" "${1}.json" )
  echo "${jsonTmp}" > "${1}.json"
  set -x
}

setpath_json() {
  local jsonTmp
  { set +x; } 2>/dev/null
  jsonTmp=$( jq --argjson 'value' "${3}" "setpath(path(.${2}); \$value)" "${1}.json" )
  echo "${jsonTmp}" > "${1}.json"
  set -x
}

setpath "product" "checksumFailMoreInfoUrl" "https://go.microsoft.com/fwlink/?LinkId=828886"
setpath "product" "documentationUrl" "https://go.microsoft.com/fwlink/?LinkID=533484#vscode"
setpath_json "product" "extensionsGallery" '{"serviceUrl": "https://open-vsx.org/vscode/gallery", "itemUrl": "https://open-vsx.org/vscode/item", "latestUrlTemplate": "https://open-vsx.org/vscode/gallery/{publisher}/{name}/latest", "controlUrl": "https://raw.githubusercontent.com/EclipseFdn/publish-extensions/refs/heads/master/extension-control/extensions.json"}'

setpath "product" "introductoryVideosUrl" "https://go.microsoft.com/fwlink/?linkid=832146"
setpath "product" "keyboardShortcutsUrlLinux" "https://go.microsoft.com/fwlink/?linkid=832144"
setpath "product" "keyboardShortcutsUrlMac" "https://go.microsoft.com/fwlink/?linkid=832143"
setpath "product" "keyboardShortcutsUrlWin" "https://go.microsoft.com/fwlink/?linkid=832145"
setpath "product" "licenseUrl" "${LICENSE_URL}"
setpath_json "product" "linkProtectionTrustedDomains" '["https://open-vsx.org"]'
setpath "product" "releaseNotesUrl" "https://go.microsoft.com/fwlink/?LinkID=533483#vscode"
setpath "product" "reportIssueUrl" "${REPORT_ISSUE_URL}"
setpath "product" "requestFeatureUrl" "https://go.microsoft.com/fwlink/?LinkID=533482"
setpath "product" "tipsAndTricksUrl" "https://go.microsoft.com/fwlink/?linkid=852118"
setpath "product" "twitterUrl" "https://go.microsoft.com/fwlink/?LinkID=533687"

if [[ "${DISABLE_UPDATE}" != "yes" ]]; then
  setpath "product" "updateUrl" "${UPDATE_URL}"
  setpath "product" "downloadUrl" "${DOWNLOAD_URL:-${REPO_URL}/releases}"

  # if [[ "${OS_NAME}" == "windows" ]]; then
  #   setpath_json "product" "win32VersionedUpdate" "true"
  # fi
fi

# crow: the insider channel is NOT vendored (src/insider is absent from
# packages/crow-gui/vscodium), so this branch is unreachable dead code kept for
# upstream diffability. crow builds VSCODE_QUALITY=stable only.
if [[ "${VSCODE_QUALITY}" == "insider" ]]; then
  setpath "product" "nameShort" "VSCodium - Insiders"
  setpath "product" "nameLong" "VSCodium - Insiders"
  setpath "product" "applicationName" "codium-insiders"
  setpath "product" "dataFolderName" ".vscodium-insiders"
  setpath "product" "linuxIconName" "vscodium-insiders"
  setpath "product" "quality" "insider"
  setpath "product" "urlProtocol" "vscodium-insiders"
  setpath "product" "serverApplicationName" "codium-server-insiders"
  setpath "product" "serverDataFolderName" ".vscodium-server-insiders"
  setpath "product" "darwinBundleIdentifier" "com.vscodium.VSCodiumInsiders"
  setpath "product" "win32AppUserModelId" "VSCodium.VSCodiumInsiders"
  setpath "product" "win32DirName" "VSCodium Insiders"
  setpath "product" "win32MutexName" "vscodiuminsiders"
  setpath "product" "win32NameVersion" "VSCodium Insiders"
  setpath "product" "win32RegValueName" "VSCodiumInsiders"
  setpath "product" "win32ShellNameShort" "VSCodium Insiders"
  setpath "product" "win32AppId" "{{EF35BB36-FA7E-4BB9-B7DA-D1E09F2DA9C9}"
  setpath "product" "win32x64AppId" "{{B2E0DDB2-120E-4D34-9F7E-8C688FF839A2}"
  setpath "product" "win32arm64AppId" "{{44721278-64C6-4513-BC45-D48E07830599}"
  setpath "product" "win32UserAppId" "{{ED2E5618-3E7E-4888-BF3C-A6CCC84F586F}"
  setpath "product" "win32x64UserAppId" "{{20F79D0D-A9AC-4220-9A81-CE675FFB6B41}"
  setpath "product" "win32arm64UserAppId" "{{2E362F92-14EA-455A-9ABD-3E656BBBFE71}"
  setpath "product" "tunnelApplicationName" "codium-insiders-tunnel"
  setpath "product" "win32TunnelServiceMutex" "vscodiuminsiders-tunnelservice"
  setpath "product" "win32TunnelMutex" "vscodiuminsiders-tunnel"
  setpath "product" "win32ContextMenu.x64.clsid" "90AAD229-85FD-43A3-B82D-8598A88829CF"
  setpath "product" "win32ContextMenu.arm64.clsid" "7544C31C-BDBF-4DDF-B15E-F73A46D6723D"
else
  setpath "product" "nameShort" "${APP_NAME}"
  setpath "product" "nameLong" "${APP_NAME}"
  setpath "product" "applicationName" "${BINARY_NAME}"
  setpath "product" "dataFolderName" ".${GLOBAL_DIRNAME}"
  setpath "product" "linuxIconName" "${GLOBAL_DIRNAME}"
  setpath "product" "quality" "stable"
  setpath "product" "urlProtocol" "${GLOBAL_DIRNAME}"
  setpath "product" "serverApplicationName" "${BINARY_NAME}-server"
  setpath "product" "serverDataFolderName" ".${GLOBAL_DIRNAME}-server"
  # crow: the Rust CLI resolves the server launcher (bin/<serverApplicationName>)
  # through tunnelServerQualities; without it, it falls back to "code-server-oss"
  # and `serve-web` cannot find the server inside our own reh-web archive.
  setpath_json "product" "tunnelServerQualities" "{\"stable\":{\"serverApplicationName\":\"${BINARY_NAME}-server\"}}"
  setpath "product" "darwinBundleIdentifier" "${DARWIN_BUNDLE_IDENTIFIER}"
  setpath "product" "win32AppUserModelId" "${ORG_NAME}.${APP_NAME}"
  setpath "product" "win32DirName" "${APP_NAME}"
  setpath "product" "win32MutexName" "${APP_NAME_LC}"
  setpath "product" "win32NameVersion" "${APP_NAME}"
  setpath "product" "win32RegValueName" "${APP_NAME}"
  setpath "product" "win32ShellNameShort" "${APP_NAME}"
  # crow: fresh AppIds/CLSIDs — VSCodium's belong to VSCodium installs and would
  # make a Windows crow installer collide with them.
  setpath "product" "win32AppId" "{{6BAB6AFD-0983-4BFE-A614-0675AE08ADA6}"
  setpath "product" "win32x64AppId" "{{7A552D8C-FB4F-4656-A5EB-F0F2BC6CC0A5}"
  setpath "product" "win32arm64AppId" "{{CE92087B-7BCB-40CE-87A5-3B64A1F38A6F}"
  setpath "product" "win32UserAppId" "{{18800242-530B-47E9-8738-18540721AB07}"
  setpath "product" "win32x64UserAppId" "{{BAF20EBD-5223-41F2-B234-96F0DD1B8791}"
  setpath "product" "win32arm64UserAppId" "{{D4FCBF7D-9824-4D36-88C4-9212AF300BFE}"
  setpath "product" "tunnelApplicationName" "${TUNNEL_APP_NAME}"
  setpath "product" "win32TunnelServiceMutex" "${APP_NAME_LC}-tunnelservice"
  setpath "product" "win32TunnelMutex" "${APP_NAME_LC}-tunnel"
  setpath "product" "win32ContextMenu.x64.clsid" "7C94F930-FDC6-4DA3-81B9-7708CA026300"
  setpath "product" "win32ContextMenu.arm64.clsid" "C6C48041-3734-427A-889A-34FFE730BD96"
fi

setpath_json "product" "tunnelApplicationConfig" '{}'

# crow: VSCodium leaves Microsoft's help/telemetry endpoints in product.json,
# and the Help menu renders one entry per URL that is present. Point the useful
# ones at crow, drop the rest — a missing URL hides its menu item.
# defaultChatAgent would make the chat view onboard towards GitHub Copilot.
setpath "product" "documentationUrl" "${SITE_URL}"
setpath "product" "releaseNotesUrl" "${REPO_URL}/releases"
setpath "product" "requestFeatureUrl" "${REPORT_ISSUE_URL}"
setpath "product" "sharedDataFolderName" ".${GLOBAL_DIRNAME}-shared"
jsonTmp=$( jq 'del(.tipsAndTricksUrl, .introductoryVideosUrl, .twitterUrl, .keyboardShortcutsUrlMac, .keyboardShortcutsUrlLinux, .keyboardShortcutsUrlWin, .checksumFailMoreInfoUrl, .voiceWsUrl, .defaultChatAgent)' product.json )
echo "${jsonTmp}" > product.json && unset jsonTmp

jsonTmp=$( jq -s '.[0] * .[1]' product.json ../product.json )
echo "${jsonTmp}" > product.json && unset jsonTmp

cat product.json
# }}}

# {{{ apply patches

echo "APP_NAME=\"${APP_NAME}\""
echo "APP_NAME_LC=\"${APP_NAME_LC}\""
echo "ASSETS_REPOSITORY=\"${ASSETS_REPOSITORY}\""
echo "BINARY_NAME=\"${BINARY_NAME}\""
echo "GH_REPO_PATH=\"${GH_REPO_PATH}\""
echo "GLOBAL_DIRNAME=\"${GLOBAL_DIRNAME}\""
echo "ORG_NAME=\"${ORG_NAME}\""
echo "TUNNEL_APP_NAME=\"${TUNNEL_APP_NAME}\""

if [[ "${DISABLE_UPDATE}" == "yes" ]]; then
  apply_patch ../patches/00-update-disable.patch.yet
fi

for file in ../patches/*.json; do
  if [[ -f "${file}" ]]; then
    apply_actions "${file}"
  fi
done

for file in ../patches/*.patch; do
  if [[ -f "${file}" ]]; then
    apply_patch "${file}"
  fi
done

if [[ "${VSCODE_QUALITY}" == "insider" ]]; then
  for file in ../patches/insider/*.patch; do
    if [[ -f "${file}" ]]; then
      apply_patch "${file}"
    fi
  done
fi

if [[ -d "../patches/${OS_NAME}/" ]]; then
  for file in "../patches/${OS_NAME}/"*.patch; do
    if [[ -f "${file}" ]]; then
      apply_patch "${file}"
    fi
  done
fi

for file in ../patches/user/*.patch; do
  if [[ -f "${file}" ]]; then
    apply_patch "${file}"
  fi
done
# }}}

set -x

# {{{ install dependencies
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

if [[ "${OS_NAME}" == "linux" ]]; then
  export VSCODE_SKIP_NODE_VERSION_CHECK=1

  if [[ "${npm_config_arch}" == "arm" ]]; then
    export npm_config_arm_version=7
  fi
elif [[ "${OS_NAME}" == "windows" ]]; then
  if [[ "${npm_config_arch}" == "arm" ]]; then
    export npm_config_arm_version=7
  fi
else
  if [[ "${CI_BUILD}" != "no" ]]; then
    clang++ --version
  fi
fi

node build/npm/preinstall.ts

mv .npmrc .npmrc.bak
cp ../npmrc .npmrc

for i in {1..5}; do # try 5 times
  if [[ "${CI_BUILD}" != "no" && "${OS_NAME}" == "osx" ]]; then
    CXX=clang++ npm ci && break
  else
    npm ci && break
  fi

  if [[ $i == 5 ]]; then
    echo "Npm install failed too many times" >&2
    exit 1
  fi
  echo "Npm install failed $i, trying again..."

  sleep $(( 15 * (i + 1)))
done

mv .npmrc.bak .npmrc
# }}}

# package.json
cp package.json{,.bak}

setpath "package" "version" "${RELEASE_VERSION%-insider}"

replace "s|Microsoft Corporation|${ORG_NAME}|" package.json
replace "s|--max-old-space-size=8192|--max-old-space-size=${MAX_OLD_SPACE_SIZE}|" package.json

cp resources/server/manifest.json{,.bak}

if [[ "${VSCODE_QUALITY}" == "insider" ]]; then
  setpath "resources/server/manifest" "name" "${APP_NAME} - Insiders"
  setpath "resources/server/manifest" "short_name" "${APP_NAME} - Insiders"
else
  setpath "resources/server/manifest" "name" "${APP_NAME}"
  setpath "resources/server/manifest" "short_name" "${APP_NAME}"
fi

# announcements
replace "s|\\[\\/\\* BUILTIN_ANNOUNCEMENTS \\*\\/\\]|$( tr -d '\n' < ../announcements-builtin.json )|" src/vs/workbench/contrib/welcomeGettingStarted/browser/gettingStarted.ts

../undo_telemetry.sh

replace "s|Microsoft Corporation|${ORG_NAME}|" build/lib/electron.ts
replace "s|([0-9]) Microsoft|\1 ${ORG_NAME}|" build/lib/electron.ts

if [[ "${OS_NAME}" == "linux" ]]; then
  # microsoft adds their apt repo to sources
  # unless the app name is code-oss
  # as we are renaming the application to ${BINARY_NAME}
  # we need to edit a line in the post install template
  sed -i "s/code-oss/${BINARY_NAME}/" resources/linux/debian/postinst.template

  # fix the packages metadata
  # code.appdata.xml
  sed -i "s|Visual Studio Code|${APP_NAME}|g" resources/linux/code.appdata.xml
  sed -i "s|https://code.visualstudio.com/docs/setup/linux|${REPO_URL}#download-install|" resources/linux/code.appdata.xml
  sed -i "s|https://code.visualstudio.com/home/home-screenshot-linux-lg.png|${SITE_URL}/img/screenshot.png|" resources/linux/code.appdata.xml
  sed -i "s|https://code.visualstudio.com|${SITE_URL}|" resources/linux/code.appdata.xml

  # control.template
  sed -i "s|Microsoft Corporation <vscode-linux@microsoft.com>|${ORG_NAME} ${REPO_URL}/graphs/contributors|" resources/linux/debian/control.template
  sed -i "s|Visual Studio Code|${APP_NAME}|g" resources/linux/debian/control.template
  sed -i "s|https://code.visualstudio.com/docs/setup/linux|${REPO_URL}#download-install|" resources/linux/debian/control.template
  sed -i "s|https://code.visualstudio.com|${SITE_URL}|" resources/linux/debian/control.template

  # code.spec.template
  sed -i "s|Microsoft Corporation|${ORG_NAME}|" resources/linux/rpm/code.spec.template
  sed -i "s|Visual Studio Code Team <vscode-linux@microsoft.com>|${ORG_NAME} ${REPO_URL}/graphs/contributors|" resources/linux/rpm/code.spec.template
  sed -i "s|Visual Studio Code|${APP_NAME}|" resources/linux/rpm/code.spec.template
  sed -i "s|https://code.visualstudio.com/docs/setup/linux|${REPO_URL}#download-install|" resources/linux/rpm/code.spec.template
  sed -i "s|https://code.visualstudio.com|${SITE_URL}|" resources/linux/rpm/code.spec.template
elif [[ "${OS_NAME}" == "windows" ]]; then
  # code.iss
  sed -i "s|https://code.visualstudio.com|${SITE_URL}|" build/win32/code.iss
  sed -i "s|Microsoft Corporation|${ORG_NAME}|" build/win32/code.iss
fi

cd ..
