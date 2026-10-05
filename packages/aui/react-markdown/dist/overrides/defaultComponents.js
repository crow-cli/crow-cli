import { jsx } from "react/jsx-runtime";
//#region src/overrides/defaultComponents.tsx
const DefaultPre = ({ node, ...rest }) => /* @__PURE__ */ jsx("pre", { ...rest });
const DefaultCode = ({ node, ...rest }) => /* @__PURE__ */ jsx("code", { ...rest });
const DefaultCodeBlockContent = ({ node, components: { Pre, Code }, code }) => /* @__PURE__ */ jsx(Pre, { children: /* @__PURE__ */ jsx(Code, {
	node,
	children: code
}) });
const DefaultCodeHeader = () => null;
//#endregion
export { DefaultCode, DefaultCodeBlockContent, DefaultCodeHeader, DefaultPre };
