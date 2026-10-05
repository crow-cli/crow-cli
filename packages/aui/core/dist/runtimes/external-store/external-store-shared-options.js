//#region src/runtimes/external-store/external-store-shared-options.ts
const pickExternalStoreSharedOptions = (options) => ({
	isDisabled: options.isDisabled,
	isSendDisabled: options.isSendDisabled,
	unstable_capabilities: options.unstable_capabilities,
	suggestions: options.suggestions
});
//#endregion
export { pickExternalStoreSharedOptions };
