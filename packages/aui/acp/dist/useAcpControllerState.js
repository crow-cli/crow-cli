"use client";
import { useSyncExternalStore } from "react";
//#region src/useAcpControllerState.ts
const useAcpControllerState = (controller) => useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);
//#endregion
export { useAcpControllerState };
