"use client";
import { create } from "zustand";
import { notifyEventListeners } from "@assistant-ui/core/internal";
//#region src/context/stores/ThreadViewport.ts
const createSizeRegistry = (onChange) => {
	const entries = /* @__PURE__ */ new Map();
	const recalculate = () => {
		let total = 0;
		for (const height of entries.values()) total += height;
		onChange(total);
	};
	return { register: () => {
		const id = Symbol();
		entries.set(id, 0);
		return {
			setHeight: (height) => {
				if (entries.get(id) !== height) {
					entries.set(id, height);
					recalculate();
				}
			},
			unregister: () => {
				entries.delete(id);
				recalculate();
			}
		};
	} };
};
const makeThreadViewportStore = (options = {}) => {
	const scrollToBottomListeners = /* @__PURE__ */ new Set();
	const viewportRegistry = createSizeRegistry((total) => {
		store.setState({ height: {
			...store.getState().height,
			viewport: total
		} });
	});
	const insetRegistry = createSizeRegistry((total) => {
		store.setState({ height: {
			...store.getState().height,
			inset: total
		} });
	});
	const registerElementSlot = (key, element) => {
		store.setState({ element: {
			...store.getState().element,
			[key]: element
		} });
		return () => {
			if (store.getState().element[key] !== element) return;
			store.setState({ element: {
				...store.getState().element,
				[key]: null
			} });
		};
	};
	const store = create(() => ({
		isAtBottom: true,
		scrollToBottom: ({ behavior = "auto" } = {}) => {
			notifyEventListeners(scrollToBottomListeners, () => ({ behavior }), "Thread viewport");
		},
		onScrollToBottom: (callback) => {
			scrollToBottomListeners.add(callback);
			return () => {
				scrollToBottomListeners.delete(callback);
			};
		},
		turnAnchor: options.turnAnchor ?? "bottom",
		topAnchorMessageClamp: {
			tallerThan: options.topAnchorMessageClamp?.tallerThan ?? "10em",
			visibleHeight: options.topAnchorMessageClamp?.visibleHeight ?? "6em"
		},
		height: {
			viewport: 0,
			inset: 0
		},
		element: {
			viewport: null,
			anchor: null,
			target: null
		},
		targetConfig: null,
		topAnchorTurn: null,
		registerViewport: viewportRegistry.register,
		registerContentInset: insetRegistry.register,
		registerViewportElement: (element) => registerElementSlot("viewport", element),
		registerAnchorElement: (element) => registerElementSlot("anchor", element),
		registerAnchorTargetElement: (element, config) => {
			store.setState({
				element: {
					...store.getState().element,
					target: element
				},
				targetConfig: element && config ? config : null
			});
			return () => {
				if (store.getState().element.target !== element) return;
				store.setState({
					element: {
						...store.getState().element,
						target: null
					},
					targetConfig: null
				});
			};
		},
		setTopAnchorTurn: (topAnchorTurn) => {
			store.setState({ topAnchorTurn });
		}
	}));
	return store;
};
//#endregion
export { makeThreadViewportStore };
