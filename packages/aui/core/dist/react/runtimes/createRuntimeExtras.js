"use client";
import { createRuntimeExtrasBrand } from "../../runtime/utils/runtime-extras-brand.js";
import { useAuiState } from "@assistant-ui/store";
//#region src/react/runtimes/createRuntimeExtras.ts
/** @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice. */
const unstable_createRuntimeExtrasFromBrand = (brand) => {
	const { provide, is, tryGet, assert } = brand;
	const get = (client) => assert(client.thread.getState().extras);
	function use(select, ...rest) {
		const hasFallback = rest.length > 0;
		const fallback = rest[0];
		return useAuiState((s) => {
			const extras = s.thread.extras;
			if (is(extras)) return select ? select(extras) : extras;
			if (hasFallback) return fallback;
			return assert(extras);
		});
	}
	return {
		provide,
		is,
		tryGet,
		get,
		use
	};
};
/** @deprecated Internal API for external-store adapter authors. Not part of the public API; may change or be removed without notice. */
const createRuntimeExtras = (runtimeName) => unstable_createRuntimeExtrasFromBrand(createRuntimeExtrasBrand(runtimeName));
//#endregion
export { createRuntimeExtras, unstable_createRuntimeExtrasFromBrand };
