import { BaseSubscribable } from "../../subscribable/subscribable.js";
//#region src/runtimes/remote-thread-list/optimistic-state.ts
const pipeTransforms = (initialState, extraParam, transforms) => {
	return transforms.reduce((state, transform) => {
		return transform?.(state, extraParam) ?? state;
	}, initialState);
};
var OptimisticState = class extends BaseSubscribable {
	_pendingTransforms = [];
	/**
	* Completed optimistic callbacks stay applied on top of the base value while
	* any transform is pending, so a state replacement made meanwhile cannot hide
	* them. They are dropped when the last transform settles, so `update()` must
	* be given a state that already contains the completed effects, such as one
	* derived from `baseValue`. While transforms are pending, callbacks apply
	* in invocation order. A transform that settles with `then` has every
	* completed callback replayed over its result, so an earlier-invoked update
	* can win over it.
	*
	* Correctness requirement: `optimistic` callbacks must be idempotent.
	*/
	_completedOptimistics = [];
	_nextTransformOrder = 0;
	_epoch = 0;
	_baseValue;
	_cachedValue;
	constructor(initialState) {
		super();
		this._baseValue = initialState;
		this._cachedValue = initialState;
	}
	_updateState() {
		const activeTransforms = [...this._pendingTransforms.map((transform) => ({
			order: transform.order,
			apply: (state) => pipeTransforms(state, transform.task, [transform.loading, transform.optimistic])
		})), ...this._completedOptimistics.map(({ order, optimistic }) => ({
			order,
			apply: optimistic
		}))].sort((a, b) => a.order - b.order);
		this._cachedValue = activeTransforms.reduce((state, transform) => transform.apply(state), this._baseValue);
		this._notifySubscribers();
	}
	get baseValue() {
		return this._baseValue;
	}
	get value() {
		return this._cachedValue;
	}
	update(state) {
		this._baseValue = state;
		this._updateState();
	}
	reset(state) {
		this._epoch++;
		this._pendingTransforms.length = 0;
		this._completedOptimistics.length = 0;
		this._baseValue = state;
		this._cachedValue = state;
		this._notifySubscribers();
	}
	async optimisticUpdate(transform) {
		const epoch = this._epoch;
		const order = this._nextTransformOrder++;
		const task = transform.execute();
		const pendingTransform = {
			...transform,
			order,
			task
		};
		try {
			this._pendingTransforms.push(pendingTransform);
			this._updateState();
			const result = await task;
			if (epoch !== this._epoch) return result;
			this._baseValue = pipeTransforms(this._baseValue, result, [transform.optimistic, transform.then]);
			for (const completed of this._completedOptimistics) if (transform.then || completed.order > pendingTransform.order) this._baseValue = completed.optimistic(this._baseValue);
			if (transform.optimistic) {
				this._completedOptimistics.push({
					order: pendingTransform.order,
					optimistic: transform.optimistic
				});
				this._completedOptimistics.sort((a, b) => a.order - b.order);
			}
			return result;
		} finally {
			const index = this._pendingTransforms.indexOf(pendingTransform);
			if (index > -1) this._pendingTransforms.splice(index, 1);
			if (this._pendingTransforms.length === 0) this._completedOptimistics.length = 0;
			this._updateState();
		}
	}
};
//#endregion
export { OptimisticState };
