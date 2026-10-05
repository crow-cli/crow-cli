import { useContextProvider } from "./core/context.js";
import { useMemoCache as useMemoCache$1 } from "./react-hooks/useMemoCache.js";
import { flushTapSync } from "./core/scheduler.js";
import { useTapRoot } from "./hooks/useTapRoot.js";
import { createTapRoot } from "./core/createTapRoot.js";
import { resource } from "./core/resource.js";
import { withKey } from "./core/withKey.js";
import { useResource } from "./hooks/useResource.js";
import { useResources } from "./hooks/useResources.js";
import { useTapHost } from "./hooks/useTapHost.js";
//#region src/index.ts
/**
* @deprecated Internal API kept for older @assistant-ui/store versions; do not use.
*/
const useMemoCache = useMemoCache$1;
//#endregion
export { createTapRoot, flushTapSync, resource, useContextProvider, useMemoCache, useResource, useResources, useTapHost, useTapRoot, withKey };
