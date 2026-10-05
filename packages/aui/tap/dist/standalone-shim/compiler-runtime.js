import { peekResourceFiber } from "../core/helpers/execution-context.js";
import { useMemoCache } from "../react-hooks/useMemoCache.js";
//#region src/standalone-shim/compiler-runtime.ts
const throwOutsideTap = (name) => {
	throw new Error(`${name} from @assistant-ui/tap/standalone-shim was called outside a tap resource render. The standalone shim has no React fallback; host this code inside createTapRoot.`);
};
const c = (size) => peekResourceFiber() !== null ? useMemoCache(size) : throwOutsideTap("c");
//#endregion
export { c };
