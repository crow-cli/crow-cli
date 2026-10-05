//#region src/utils/client-keys.ts
const isIgnoredClientKey = (key) => {
	return key === "optional" || key === "subscribe" || key === "on" || key === "__proto__" || typeof key === "symbol";
};
const clientScopeKeys = (client) => {
	const keys = [];
	for (const key in client) if (!isIgnoredClientKey(key)) keys.push(key);
	return keys;
};
//#endregion
export { clientScopeKeys, isIgnoredClientKey };
