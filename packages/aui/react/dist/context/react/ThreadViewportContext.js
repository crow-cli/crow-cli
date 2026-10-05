"use client";
import { createContextHook } from "./utils/createContextHook.js";
import { createContextStoreHook } from "./utils/createContextStoreHook.js";
import { createContext } from "@assistant-ui/tap/react-shim";
//#region src/context/react/ThreadViewportContext.ts
const ThreadViewportContext = createContext(null);
const useThreadViewportContext = createContextHook(ThreadViewportContext, "ThreadPrimitive.Viewport");
const { useThreadViewport, useThreadViewportStore } = createContextStoreHook(useThreadViewportContext, "useThreadViewport");
//#endregion
export { ThreadViewportContext, useThreadViewport, useThreadViewportStore };
