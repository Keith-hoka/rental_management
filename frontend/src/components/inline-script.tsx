/**
 * Runs `html` synchronously while the browser parses the document, before the
 * first paint. React warns when a render produces a <script>, so the type is
 * text/javascript on the server and inert text/plain on the client, which is
 * what suppressHydrationWarning is covering.
 *
 * See node_modules/next/dist/docs/01-app/02-guides/preventing-flash-before-hydration.md
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
