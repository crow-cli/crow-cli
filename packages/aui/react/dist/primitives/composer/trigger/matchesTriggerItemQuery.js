//#region src/primitives/composer/trigger/matchesTriggerItemQuery.ts
function matchesTriggerItemQuery(item, lowerQuery) {
	if (!lowerQuery) return true;
	return item.id.toLowerCase().includes(lowerQuery) || item.label.toLowerCase().includes(lowerQuery) || (item.description?.toLowerCase().includes(lowerQuery) ?? false);
}
//#endregion
export { matchesTriggerItemQuery };
