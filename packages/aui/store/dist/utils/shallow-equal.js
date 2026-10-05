//#region src/utils/shallow-equal.ts
const shallowEqual = (a, b) => {
	if (Array.isArray(a) !== Array.isArray(b)) return false;
	if (Array.isArray(a) && Array.isArray(b)) {
		if (a.length !== b.length) return false;
		for (let i = 0; i < a.length; i++) if (!Object.is(a[i], b[i])) return false;
		return true;
	}
	const aKeys = Object.keys(a);
	return aKeys.length === Object.keys(b).length && aKeys.every((key) => Object.hasOwn(b, key) && Object.is(a[key], b[key]));
};
//#endregion
export { shallowEqual };
