"use client";

import { useTheme } from "next-themes";
import { useEffect, useId, useState } from "react";

type RenderResult = {
  key: string;
  svg?: string;
  error?: true;
};

export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replaceAll(":", "");
  const { resolvedTheme } = useTheme();
  const renderKey = `${resolvedTheme ?? "light"}:${chart}`;
  const [result, setResult] = useState<RenderResult>();
  const currentResult = result?.key === renderKey ? result : undefined;

  useEffect(() => {
    let isCurrent = true;

    async function renderDiagram() {
      try {
        const { default: mermaid } = await import("mermaid");
        // Load Mermaid only on pages that actually contain a diagram.
        const token = (name: string) =>
          getComputedStyle(document.documentElement)
            .getPropertyValue(`--color-fd-${name}`)
            .trim();
        const colors = {
          background: token("background"),
          primaryColor: token("accent"),
          primaryTextColor: token("accent-foreground"),
          primaryBorderColor: token("primary"),
          lineColor: token("muted-foreground"),
          secondaryColor: token("secondary"),
          tertiaryColor: token("card"),
          textColor: token("foreground"),
          fontFamily: getComputedStyle(document.body).fontFamily,
        };
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: colors,
        });

        const rendered = await mermaid.render(
          `mermaid-${id}`,
          chart.replaceAll("\\n", "\n"),
        );
        if (isCurrent) setResult({ key: renderKey, svg: rendered.svg });
      } catch {
        if (isCurrent) setResult({ key: renderKey, error: true });
      }
    }

    void renderDiagram();

    return () => {
      isCurrent = false;
    };
  }, [chart, id, renderKey, resolvedTheme]);

  return (
    <figure className="not-prose my-6 max-w-full overflow-x-auto rounded-xl border border-fd-border bg-fd-card p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none">
      {currentResult?.svg ? (
        <div
          role="img"
          aria-label="Diagram alur"
          dangerouslySetInnerHTML={{ __html: currentResult.svg }}
        />
      ) : (
        <div aria-live="polite">
          <p className="m-0 text-sm text-fd-muted-foreground">
            {currentResult?.error
              ? "Diagram tidak dapat ditampilkan. Sumber diagram tersedia di bawah."
              : "Memuat diagram…"}
          </p>
          {currentResult?.error && (
            <pre className="mt-3 overflow-x-auto rounded-md bg-fd-muted p-3 text-sm text-fd-muted-foreground">
              <code>{chart}</code>
            </pre>
          )}
        </div>
      )}
    </figure>
  );
}
