import { useSyncExternalStore } from "@assistant-ui/tap/react-shim";
//#region src/store/runtime-clients/useSubscribable.ts
const useSubscribable = (subscribable) => {
	return useSyncExternalStore(subscribable.subscribe, subscribable.getState, subscribable.getServerSnapshot);
};
//#endregion
export { useSubscribable };
