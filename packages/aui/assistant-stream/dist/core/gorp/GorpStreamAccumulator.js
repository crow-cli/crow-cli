import { assertSafePathSegment } from "./changeTree.js";
//#region src/core/gorp/GorpStreamAccumulator.ts
var GorpStreamAccumulator = class {
	_state;
	_strict;
	_logged = /* @__PURE__ */ new Set();
	_warnedClamp = false;
	constructor(initialValue = null, options = {}) {
		this._state = initialValue;
		this._strict = options.strict ?? true;
	}
	get state() {
		return this._state;
	}
	logOnce(key, log) {
		if (this._logged.has(key) || this._logged.size >= 20) return;
		this._logged.add(key);
		log();
	}
	append(ops) {
		this._state = ops.reduce((state, op) => {
			if (this._strict) return this.apply(state, op);
			try {
				return this.apply(state, op);
			} catch (error) {
				this.logOnce(`skip:${String(error)}`, () => console.error(`Skipped unappliable gorp operation: ${String(error)}`, op));
				return state;
			}
		}, this._state);
	}
	apply(state, op) {
		const type = op.type;
		switch (type) {
			case "set": return this.updatePath(state, op.path, () => op.value);
			case "append-text": return this.updatePath(state, op.path, (current) => {
				if (typeof current !== "string") throw new Error(`Expected string at path [${op.path.join(", ")}]`);
				return current + op.value;
			});
			default: throw new Error(`Invalid operation type: ${type}`);
		}
	}
	updatePath(state, path, updater) {
		if (path.length === 0) return updater(state);
		const frames = [];
		let current = state;
		for (let depth = 0; depth < path.length; depth++) {
			current ??= {};
			if (typeof current !== "object") throw new Error(`Invalid path: [${path.slice(depth).join(", ")}]`);
			const key = path[depth];
			assertSafePathSegment(key);
			if (Array.isArray(current)) {
				let index = Number(key);
				if (!Number.isInteger(index) || String(index) !== String(key)) throw new Error(`Expected array index at [${path.slice(depth).join(", ")}]`);
				if (index < 0) throw new Error(`Insert array index out of bounds`);
				if (index > current.length) {
					if (this._strict) throw new Error(`Insert array index out of bounds`);
					if (!this._warnedClamp) {
						this._warnedClamp = true;
						console.warn(`Clamped out-of-bounds gorp array index ${index} to ${current.length}`);
					}
					index = current.length;
				}
				frames.push({
					kind: "array",
					state: current,
					key: index
				});
				current = Object.hasOwn(current, index) ? current[index] : void 0;
			} else {
				const object = current;
				frames.push({
					kind: "object",
					state: object,
					key
				});
				current = Object.hasOwn(object, key) ? object[key] : void 0;
			}
		}
		let updated = updater(current);
		for (let index = frames.length - 1; index >= 0; index--) {
			const frame = frames[index];
			if (frame.kind === "array") {
				const next = [...frame.state];
				next[frame.key] = updated;
				updated = next;
			} else {
				const next = { ...frame.state };
				next[frame.key] = updated;
				updated = next;
			}
		}
		return updated;
	}
};
//#endregion
export { GorpStreamAccumulator };
