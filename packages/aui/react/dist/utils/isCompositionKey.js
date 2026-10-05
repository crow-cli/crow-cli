//#region src/utils/isCompositionKey.ts
const isCompositionKey = (event) => event.isComposing || event.keyCode === 229;
//#endregion
export { isCompositionKey };
