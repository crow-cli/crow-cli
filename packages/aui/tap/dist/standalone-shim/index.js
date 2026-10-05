import { peekResourceFiber } from "../core/helpers/execution-context.js";
import { useEffect as useEffect$1 } from "../react-hooks/useEffect.js";
import { useRef as useRef$1 } from "../react-hooks/useRef.js";
import { attachDefaultValueToContext, useContext as useContext$1 } from "../core/context.js";
import { useReducer as useReducer$1 } from "../react-hooks/useReducer.js";
import { useState as useState$1 } from "../react-hooks/useState.js";
import { useMemo as useMemo$1 } from "../react-hooks/useMemo.js";
import { useCallback as useCallback$1 } from "../react-hooks/useCallback.js";
import { useInsertionEffect as useInsertionEffect$1 } from "../react-hooks/useInsertionEffect.js";
import { useEffectEvent as useEffectEvent$1 } from "../react-hooks/useEffectEvent.js";
import { use as use$1 } from "../react-hooks/use.js";
import { useSyncExternalStore as useSyncExternalStore$1 } from "../react-hooks/useSyncExternalStore.js";
import { useDebugValue as useDebugValue$1 } from "../react-hooks/useDebugValue.js";
import { useId as useId$1 } from "../react-hooks/useId.js";
import { useImperativeHandle as useImperativeHandle$1 } from "../react-hooks/useImperativeHandle.js";
//#region src/standalone-shim/index.ts
const inTap = () => peekResourceFiber() !== null;
const throwOutsideTap = (name) => {
	throw new Error(`${name} from @assistant-ui/tap/standalone-shim was called outside a tap resource render. The standalone shim has no React fallback; host this code inside createTapRoot.`);
};
const useState = (initialState) => inTap() ? useState$1(initialState) : throwOutsideTap("useState");
const useReducer = (reducer, initialArg, init) => inTap() ? useReducer$1(reducer, initialArg, init) : throwOutsideTap("useReducer");
const useRef = (initialValue) => inTap() ? useRef$1(initialValue) : throwOutsideTap("useRef");
const useMemo = (factory, deps) => inTap() ? useMemo$1(factory, deps) : throwOutsideTap("useMemo");
const useCallback = (callback, deps) => inTap() ? useCallback$1(callback, deps) : throwOutsideTap("useCallback");
const useEffect = (effect, deps) => inTap() ? useEffect$1(effect, deps) : throwOutsideTap("useEffect");
const useLayoutEffect = (effect, deps) => inTap() ? useEffect$1(effect, deps) : throwOutsideTap("useLayoutEffect");
const useInsertionEffect = (effect, deps) => inTap() ? useInsertionEffect$1(effect, deps) : throwOutsideTap("useInsertionEffect");
const useEffectEvent = (callback) => inTap() ? useEffectEvent$1(callback) : throwOutsideTap("useEffectEvent");
const useSyncExternalStore = (subscribe, getSnapshot, getServerSnapshot) => inTap() ? useSyncExternalStore$1(subscribe, getSnapshot, getServerSnapshot) : throwOutsideTap("useSyncExternalStore");
const useDebugValue = (value, format) => inTap() ? /* @__PURE__ */ useDebugValue$1(value, format) : throwOutsideTap("useDebugValue");
const useId = () => inTap() ? useId$1() : throwOutsideTap("useId");
const useImperativeHandle = (ref, create, deps) => inTap() ? useImperativeHandle$1(ref, create, deps) : throwOutsideTap("useImperativeHandle");
const createContext = (defaultValue) => {
	const context = {};
	attachDefaultValueToContext(context, defaultValue);
	return context;
};
const use = (usable) => inTap() ? use$1(usable) : throwOutsideTap("use");
const useContext = (context) => inTap() ? useContext$1(context) : throwOutsideTap("useContext");
const forwardRef = (render) => ({
	$$typeof: Symbol.for("react.forward_ref"),
	render
});
const memo = (type, compare) => ({
	$$typeof: Symbol.for("react.memo"),
	type,
	compare: compare ?? null
});
const Fragment = Symbol.for("react.fragment");
const throwNoReact = (name) => {
	throw new Error(`${name} from @assistant-ui/tap/standalone-shim was called without React. The standalone shim only makes react-coupled modules loadable; rendering them requires real React.`);
};
const createElement = () => throwNoReact("createElement");
const cloneElement = () => throwNoReact("cloneElement");
const isValidElement = (_value) => false;
const lazy = (load) => ({
	$$typeof: Symbol.for("react.lazy"),
	_payload: {
		_status: -1,
		_result: load
	},
	_init: () => throwNoReact("lazy")
});
const Children = {
	map: () => throwNoReact("Children.map"),
	forEach: () => throwNoReact("Children.forEach"),
	count: () => throwNoReact("Children.count"),
	toArray: () => throwNoReact("Children.toArray"),
	only: () => throwNoReact("Children.only")
};
const Suspense = Symbol.for("react.suspense");
const useDeferredValue = () => throwNoReact("useDeferredValue");
const StandaloneRuntime = Object.freeze({
	useState,
	useReducer,
	useRef,
	useMemo,
	useCallback,
	useEffect,
	useLayoutEffect,
	useInsertionEffect,
	useEffectEvent,
	useSyncExternalStore,
	useDebugValue,
	useId,
	useImperativeHandle,
	createContext,
	use,
	useContext,
	forwardRef,
	memo,
	Fragment,
	createElement,
	cloneElement,
	isValidElement,
	lazy,
	Children,
	Suspense,
	useDeferredValue
});
//#endregion
export { Children, Fragment, Suspense, cloneElement, createContext, createElement, StandaloneRuntime as default, forwardRef, isValidElement, lazy, memo, use, useCallback, useContext, useDebugValue, useDeferredValue, useEffect, useEffectEvent, useId, useImperativeHandle, useInsertionEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore };
