//#region src/attachTransformScopes.ts
const TRANSFORM_SCOPES = Symbol("assistant-ui.transform-scopes");
function attachTransformScopes(hook, transform) {
	const h = hook;
	if (h[TRANSFORM_SCOPES]) throw new Error("transformScopes is already attached to this resource");
	h[TRANSFORM_SCOPES] = transform;
}
function forwardTransformScopes(target, source) {
	const sourceTransform = getTransformScopes(source);
	if (!sourceTransform) return;
	const t = target;
	const existingTransform = t[TRANSFORM_SCOPES];
	if (existingTransform) t[TRANSFORM_SCOPES] = (scopes, parent) => {
		sourceTransform(scopes, parent);
		existingTransform(scopes, parent);
	};
	else t[TRANSFORM_SCOPES] = sourceTransform;
}
function getTransformScopes(hook) {
	return hook[TRANSFORM_SCOPES];
}
//#endregion
export { attachTransformScopes, forwardTransformScopes, getTransformScopes };
