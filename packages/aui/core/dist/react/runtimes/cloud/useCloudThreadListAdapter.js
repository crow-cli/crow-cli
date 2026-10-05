import { autoCloud, createCloudThreadListAdapter, useCloudRuntimeAdapters } from "./createCloudThreadListAdapter.js";
import { useInsertionEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/cloud/useCloudThreadListAdapter.tsx
const useCloudThreadListAdapter = (adapter) => {
	const adapterRef = useRef(adapter);
	useInsertionEffect(() => {
		adapterRef.current = adapter;
	}, [adapter]);
	const [cloudRef] = useState(() => ({ get current() {
		return adapterRef.current.cloud ?? autoCloud;
	} }));
	const [unstable_useAdapters] = useState(() => function useCloudAdapters() {
		return useCloudRuntimeAdapters(cloudRef);
	});
	const cloud = adapter.cloud ?? autoCloud;
	const createAdapter = () => {
		let readOptions = () => adapter;
		const base = createCloudThreadListAdapter(() => ({
			...readOptions(),
			cloud
		}));
		readOptions = () => adapterRef.current;
		if (base.unstable_useAdapters === void 0) return base;
		return {
			...base,
			unstable_useAdapters
		};
	};
	const [pinned, setPinned] = useState(() => ({
		cloud,
		adapter: createAdapter()
	}));
	if (pinned.cloud !== cloud) {
		const next = {
			cloud,
			adapter: createAdapter()
		};
		setPinned(next);
		return next.adapter;
	}
	return pinned.adapter;
};
//#endregion
export { useCloudThreadListAdapter };
