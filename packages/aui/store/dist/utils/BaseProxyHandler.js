//#region src/utils/BaseProxyHandler.ts
const INTROSPECTION_PROPS = /* @__PURE__ */ new Set([
	"$$typeof",
	"nodeType",
	"then",
	"__v_raw",
	"__v_isRef",
	"__v_isReactive",
	"__v_isReadonly",
	"__v_isShallow",
	"__v_skip"
]);
/**
* Handles common proxy introspection properties.
* Returns the appropriate value for toStringTag, toJSON, and props that should return undefined.
* Returns `false` if the prop should be handled by the subclass.
*/
const handleIntrospectionProp = (prop, name) => {
	if (prop === Symbol.toStringTag) return name;
	if (typeof prop === "symbol") return void 0;
	if (prop === "toJSON") return () => name;
	if (INTROSPECTION_PROPS.has(prop)) return void 0;
	return false;
};
var BaseProxyHandler = class {
	getOwnPropertyDescriptor(_, prop) {
		const value = this.get(_, prop);
		if (value === void 0) return void 0;
		return {
			value,
			writable: false,
			enumerable: true,
			configurable: true
		};
	}
	set() {
		return false;
	}
	setPrototypeOf() {
		return false;
	}
	defineProperty() {
		return false;
	}
	deleteProperty() {
		return false;
	}
	preventExtensions() {
		return false;
	}
};
//#endregion
export { BaseProxyHandler, handleIntrospectionProp };
