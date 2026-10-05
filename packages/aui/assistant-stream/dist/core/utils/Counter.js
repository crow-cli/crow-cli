//#region src/core/utils/Counter.ts
var Counter = class {
	value = -1;
	up() {
		return ++this.value;
	}
};
//#endregion
export { Counter };
