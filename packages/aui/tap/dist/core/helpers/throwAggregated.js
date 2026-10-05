//#region src/core/helpers/throwAggregated.ts
const throwAggregated = (errors, message) => {
	if (errors.length === 0) return;
	if (errors.length === 1) throw errors[0];
	for (const error of errors) console.error(error);
	throw new AggregateError(errors, message);
};
//#endregion
export { throwAggregated };
