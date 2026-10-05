//#region src/utils/record.ts
/**
* Builds a dictionary with no prototype from the own entries of its arguments.
* Bracket assignment on a plain object routes a `__proto__` key through the
* `Object.prototype` setter instead of defining an own property, so a record
* assigned into by a key the app does not control is built this way.
*/
const nullProtoRecord = (base, ...rest) => Object.assign(Object.create(null), base, ...rest);
//#endregion
export { nullProtoRecord };
