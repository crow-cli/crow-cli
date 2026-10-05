//#region src/store/runtime-clients/liveRef.ts
const liveRef = (get) => ({ get current() {
	return get();
} });
//#endregion
export { liveRef };
