import { Fragment, throwRender } from "./jsx-runtime.js";
//#region src/standalone-shim/jsx-dev-runtime.ts
const jsxDEV = throwRender;
//#endregion
export { Fragment, jsxDEV };
