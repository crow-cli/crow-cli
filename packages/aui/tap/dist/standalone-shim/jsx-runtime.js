//#region src/standalone-shim/jsx-runtime.ts
const throwRender = () => {
	throw new Error("JSX from @assistant-ui/tap/standalone-shim was rendered without React. The standalone shim only makes react-coupled modules loadable; rendering them requires real React.");
};
const Fragment = Symbol.for("react.fragment");
const jsx = throwRender;
const jsxs = throwRender;
//#endregion
export { Fragment, jsx, jsxs, throwRender };
