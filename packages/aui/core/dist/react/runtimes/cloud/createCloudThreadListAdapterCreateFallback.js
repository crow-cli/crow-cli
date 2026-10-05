//#region src/react/runtimes/cloud/createCloudThreadListAdapterCreateFallback.ts
const createCloudThreadListAdapterCreateFallback = (create, threadListItem) => async function createThread() {
	if (create) return create();
	if (threadListItem.source) return threadListItem.initialize();
	return { externalId: void 0 };
};
//#endregion
export { createCloudThreadListAdapterCreateFallback };
