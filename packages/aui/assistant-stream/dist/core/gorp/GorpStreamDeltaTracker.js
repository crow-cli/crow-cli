import { createChangeNode, diffKeys, lookupChange, lookupValue, markChanged } from "./changeTree.js";
import { GorpStreamAccumulator } from "./GorpStreamAccumulator.js";
//#region src/core/gorp/GorpStreamDeltaTracker.ts
var GorpStreamDeltaTracker = class {
	accumulator;
	previousState;
	changes = createChangeNode();
	constructor(initialValue = null) {
		this.accumulator = new GorpStreamAccumulator(initialValue);
		this.previousState = this.accumulator.state;
	}
	get state() {
		return this.accumulator.state;
	}
	append(operations) {
		const previousState = this.accumulator.state;
		let changes = createChangeNode();
		for (const op of operations) changes = markChanged(changes, op.path);
		this.accumulator.append(operations);
		this.previousState = previousState;
		this.changes = changes;
	}
	isChangedAt(path) {
		const node = lookupChange(this.changes, path);
		if (node === true) return true;
		return node !== false && Object.keys(node).length > 0;
	}
	getChangedKeys(path) {
		const node = lookupChange(this.changes, path);
		if (node === false) return [];
		if (node === true) return diffKeys(lookupValue(this.accumulator.state, path), lookupValue(this.previousState, path));
		return Object.keys(node);
	}
};
//#endregion
export { GorpStreamDeltaTracker };
