export { resource } from "./core/resource.js";
export { withKey } from "./core/withKey.js";
export { createTapRoot } from "./core/createTapRoot.js";
export { flushTapSync } from "./core/scheduler.js";
export { useContextProvider } from "./core/context.js";
/**
 * @deprecated Internal API kept for older @assistant-ui/store versions; do not use.
 */
export declare const useMemoCache: (size: number) => unknown[];
export { useResource } from "./hooks/useResource.js";
export { useResources } from "./hooks/useResources.js";
export { useTapRoot } from "./hooks/useTapRoot.js";
export { useTapHost } from "./hooks/useTapHost.js";
export type { Resource, ResourceElement } from "./core/types.js";