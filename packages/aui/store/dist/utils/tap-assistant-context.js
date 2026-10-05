import { getClientInstanceId, isScopeAvailable } from "./client-accessor.js";
import { useClientStack } from "./tap-client-stack-context.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, use, useEffect, useEffectEvent } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
//#region src/utils/tap-assistant-context.ts
const AssistantTapContext = createContext(null);
const UNAPPLIED = Symbol("aui.scope-effect-unapplied");
const useAssistantTapContextProvider = (value, fn) => {
	return useContextProvider(AssistantTapContext, value, fn);
};
const useAssistantTapContext = () => {
	const ctx = use(AssistantTapContext);
	if (!ctx) throw new Error("AssistantTapContext is not available");
	return ctx;
};
const useAssistantClientRef = () => {
	return useAssistantTapContext().clientRef;
};
/**
* Runs a registration effect that follows the bound client instance of one
* scope: when a structural change remounts or replaces that instance, the
* previous cleanup runs and the effect runs again against the replacement.
* Value updates on the same instance do not re-run it, and while the scope
* is unavailable only cleanup runs, so the effect always executes against a
* bound scope. A migration whose effect throws stays unapplied, so the next
* notification retries it. The client ref is committed before effects run,
* so reads through it inside the effect see the finalized client.
*/
const useAssistantScopeEffect = (scope, effect, deps) => {
	const $ = c(8);
	const { clientRef } = useAssistantTapContext();
	let t0;
	if ($[0] !== clientRef || $[1] !== effect || $[2] !== scope) {
		t0 = () => {
			const client = clientRef.current;
			if (client === null) throw new Error("useAssistantScopeEffect ran before the client was committed. This is likely an internal bug in assistant-ui.");
			const identityOf = () => {
				const accessor = clientRef.current?.[scope];
				return accessor !== void 0 && isScopeAvailable(accessor) ? getClientInstanceId(accessor) : void 0;
			};
			let applied = UNAPPLIED;
			let cleanup;
			const apply = (next) => {
				cleanup?.();
				cleanup = void 0;
				applied = UNAPPLIED;
				if (next !== void 0) {
					const result = effect();
					cleanup = typeof result === "function" ? result : void 0;
				}
				applied = next;
			};
			apply(identityOf());
			const unsubscribe = client.subscribe(() => {
				const next_0 = identityOf();
				if (next_0 === applied) return;
				apply(next_0);
			});
			return () => {
				unsubscribe();
				cleanup?.();
			};
		};
		$[0] = clientRef;
		$[1] = effect;
		$[2] = scope;
		$[3] = t0;
	} else t0 = $[3];
	let t1;
	if ($[4] !== clientRef || $[5] !== deps || $[6] !== scope) {
		t1 = [
			clientRef,
			scope,
			...deps
		];
		$[4] = clientRef;
		$[5] = deps;
		$[6] = scope;
		$[7] = t1;
	} else t1 = $[7];
	useEffect(t0, t1);
};
const useAssistantEmit = () => {
	const $ = c(3);
	const { emit } = useAssistantTapContext();
	const clientStack = useClientStack();
	let t0;
	if ($[0] !== clientStack || $[1] !== emit) {
		t0 = (event, payload) => {
			emit(event, payload, clientStack);
		};
		$[0] = clientStack;
		$[1] = emit;
		$[2] = t0;
	} else t0 = $[2];
	return useEffectEvent(t0);
};
//#endregion
export { useAssistantClientRef, useAssistantEmit, useAssistantScopeEffect, useAssistantTapContextProvider };
