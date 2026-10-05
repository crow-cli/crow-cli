//#region src/adapters/directive-formatter.ts
const DIRECTIVE_RE = /:([\w-]{1,64})\[([^\]\n]{1,1024})\](?:\{name=([^}\n]{1,1024})\})?/gu;
/**
* Default directive formatter using the `:type[label]{name=id}` syntax.
*
* When `id` equals `label`, the `{name=…}` attribute is omitted for brevity.
*/
const unstable_defaultDirectiveFormatter = {
	serialize(item) {
		const attrs = item.id !== item.label ? `{name=${item.id}}` : "";
		return `:${item.type}[${item.label}]${attrs}`;
	},
	parse(text) {
		const segments = [];
		let lastIndex = 0;
		for (const match of text.matchAll(DIRECTIVE_RE)) {
			if (match.index > lastIndex) segments.push({
				kind: "text",
				text: text.slice(lastIndex, match.index)
			});
			const label = match[2];
			segments.push({
				kind: "mention",
				type: match[1],
				label,
				id: match[3] ?? label
			});
			lastIndex = match.index + match[0].length;
		}
		if (lastIndex < text.length) segments.push({
			kind: "text",
			text: text.slice(lastIndex)
		});
		return segments;
	}
};
//#endregion
export { unstable_defaultDirectiveFormatter };
