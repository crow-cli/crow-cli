//#region src/utils/promiseWithResolvers.ts
const promiseWithResolvers = () => {
	let resolve;
	let reject;
	const promise = new Promise((res, rej) => {
		resolve = res;
		reject = rej;
	});
	if (!resolve || !reject) throw new Error("Failed to create promise");
	return {
		promise,
		resolve,
		reject
	};
};
//#endregion
export { promiseWithResolvers };
