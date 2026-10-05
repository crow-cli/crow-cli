import { isDevelopment } from "../../store/env.js";
import { useRuntimeAdapters, useRuntimeAdaptersProvider, useStableRuntimeAdapters } from "../runtimes/useRuntimeAdapters.js";
import { useClientResource } from "@assistant-ui/store/client";
import { useEffect, useMemo } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/react/client/AdaptedRemoteThread.ts
const useAdaptedRemoteThread = ({ useAdapters, thread }) => {
	const parent = useRuntimeAdapters();
	const stableAdapters = useStableRuntimeAdapters(useAdapters());
	const unkeyedHistory = stableAdapters?.history != null && thread.key === void 0;
	useEffect(() => {
		if (!isDevelopment || !unkeyedHistory) return;
		console.warn("[assistant-ui] RemoteThreadList received a history adapter, but the thread factory is unkeyed. Key the thread resource by thread id (withKey) so switching threads reloads history.");
	}, [unkeyedHistory]);
	const merged = useMemo(() => stableAdapters == null ? parent : {
		...parent,
		...stableAdapters
	}, [parent, stableAdapters]);
	return useRuntimeAdaptersProvider(merged, function useBoundRemoteThread() {
		return useClientResource(thread).methods;
	});
};
const AdaptedRemoteThread = resource(useAdaptedRemoteThread);
//#endregion
export { AdaptedRemoteThread };
