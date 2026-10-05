/**
 * A mermaid fence rendered as a diagram instead of as code.
 *
 * Wired through `componentsByLanguage`, so only fences tagged ```mermaid come
 * here; everything else keeps the highlighter. mermaid is imported lazily —
 * it is the heaviest thing in the bundle and most threads never draw a
 * diagram. While the message streams the source is still partial syntax, so
 * a failed parse shows the source rather than an error box; the final text
 * parses and the diagram appears.
 */
import { useEffect, useId, useState, type FC } from "react";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";

import { useColorScheme } from "@/lib/theme";

let counter = 0;

export const MermaidDiagram: FC<SyntaxHighlighterProps> = ({
  code,
  components: { Pre, Code },
}) => {
  const id = useId();
  const scheme = useColorScheme();
  const [svg, setSvg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setSvg(null);
    void (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: scheme === "dark" ? "dark" : "default",
      });
      try {
        await mermaid.parse(code);
        const rendered = await mermaid.render(`mermaid-${id}-${counter++}`, code);
        if (alive) setSvg(rendered.svg);
      } catch {
        if (alive) setSvg(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [code, scheme, id]);

  if (!svg) {
    return (
      <Pre>
        <Code>{code}</Code>
      </Pre>
    );
  }
  return (
    <div
      className="bg-background text-foreground flex justify-center overflow-x-auto rounded-b-xl p-3"
      // mermaid's own sanitizer (securityLevel: strict) has already stripped
      // scripts and foreign objects out of this svg.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};
