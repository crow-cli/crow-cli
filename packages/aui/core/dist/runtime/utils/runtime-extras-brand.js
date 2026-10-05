//#region src/runtime/utils/runtime-extras-brand.ts
/**
* Creates the framework-neutral half of a runtime extras channel: the brand
* symbol with its provide/read primitives. A runtime factory provides extras
* through the brand on any framework; the React entry wraps the same brand
* with a `use()` hook. The symbol is per-instance, so the adapter package
* creates the brand once and every binding imports that instance.
*
* @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice.
*/
const createRuntimeExtrasBrand = (runtimeName) => {
	const brand = Symbol(`${runtimeName} extras`);
	const is = (extras) => typeof extras === "object" && extras !== null && brand in extras;
	const assert = (extras) => {
		if (!is(extras)) throw new Error(`The current thread is not backed by the ${runtimeName} runtime.`);
		return extras;
	};
	const provide = (value) => {
		Object.defineProperty(value, brand, {
			value: true,
			enumerable: false,
			configurable: true
		});
		return value;
	};
	const tryGet = (extras) => is(extras) ? extras : void 0;
	return {
		provide,
		is,
		tryGet,
		assert
	};
};
//#endregion
export { createRuntimeExtrasBrand };
