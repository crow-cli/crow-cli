import { peekResourceFiber } from "../core/helpers/execution-context.js";
import { useMemoCache } from "../react-hooks/useMemoCache.js";
import { reactC } from "./useReactMemoCache.js";
//#region src/react-shim/compiler-runtime.ts
const inTap = () => peekResourceFiber() !== null;
const c = (size) => inTap() ? useMemoCache(size) : reactC(size);
//#endregion
export { c };
