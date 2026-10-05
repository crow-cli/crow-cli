import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { cloneElement, forwardRef, isValidElement } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { Primitive as Primitive$1 } from "radix-ui/internal";
import { Slot } from "radix-ui";
//#region src/utils/Primitive.tsx
/**
* Thin wrapper around Radix `Primitive` that adds `render` prop support.
*
* When `render` is provided, it is converted to the equivalent `asChild` pattern:
*   render={<Comp props />} + children  →  asChild + <Comp props>{children}</Comp>
*
* All prop merging, ref composition, and event handler chaining remain handled
* by Radix's battle-tested Slot implementation — we add zero custom logic for that.
*/
const NODES = [
	"a",
	"button",
	"div",
	"form",
	"h2",
	"h3",
	"img",
	"input",
	"label",
	"li",
	"nav",
	"ol",
	"p",
	"select",
	"span",
	"svg",
	"ul"
];
/**
* Composes the children of a `render` element. Outer children win when supplied;
* the render element's own children are the fallback.
*/
function composeRenderElement(render, children) {
	return cloneElement(render, void 0, children !== void 0 ? children : render.props.children);
}
/**
* Composes a `render` element at a call site that has already computed its props.
*
* `withRenderProp` wraps a component; this covers the case where the props are
* already in hand and the composition happens inline.
*/
function renderSlot(render, children, props) {
	return /* @__PURE__ */ jsx(Slot.Root, {
		...props,
		children: composeRenderElement(render, children)
	});
}
function withRenderProp(Component) {
	const Wrapped = forwardRef((t0, ref) => {
		const $ = c(17);
		let asChild;
		let children;
		let render;
		let rest;
		if ($[0] !== t0) {
			({render, asChild, children, ...rest} = t0);
			$[0] = t0;
			$[1] = asChild;
			$[2] = children;
			$[3] = render;
			$[4] = rest;
		} else {
			asChild = $[1];
			children = $[2];
			render = $[3];
			rest = $[4];
		}
		const Comp = Component;
		if (render && isValidElement(render)) {
			const t1 = rest;
			let t2;
			if ($[5] !== children || $[6] !== render) {
				t2 = composeRenderElement(render, children);
				$[5] = children;
				$[6] = render;
				$[7] = t2;
			} else t2 = $[7];
			let t3;
			if ($[8] !== ref || $[9] !== t1 || $[10] !== t2) {
				t3 = /* @__PURE__ */ jsx(Comp, {
					...t1,
					asChild: true,
					ref,
					children: t2
				});
				$[8] = ref;
				$[9] = t1;
				$[10] = t2;
				$[11] = t3;
			} else t3 = $[11];
			return t3;
		}
		const t1 = rest;
		let t2;
		if ($[12] !== asChild || $[13] !== children || $[14] !== ref || $[15] !== t1) {
			t2 = /* @__PURE__ */ jsx(Comp, {
				...t1,
				asChild,
				ref,
				children
			});
			$[12] = asChild;
			$[13] = children;
			$[14] = ref;
			$[15] = t1;
			$[16] = t2;
		} else t2 = $[16];
		return t2;
	});
	Wrapped.displayName = typeof Component === "string" ? Component : Component.displayName ?? Component.name ?? "Component";
	return Wrapped;
}
function createPrimitive(node) {
	const RadixComp = Primitive$1[node];
	const Component = withRenderProp(RadixComp);
	Component.displayName = `Primitive.${node}`;
	return Component;
}
const Primitive = NODES.reduce((acc, node) => {
	acc[node] = createPrimitive(node);
	return acc;
}, {});
//#endregion
export { Primitive, renderSlot, withRenderProp };
