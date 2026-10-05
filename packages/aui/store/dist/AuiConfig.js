//#region src/AuiConfig.ts
/**
* Builds a config for {@link AuiProvider}; the `config` prop only accepts
* configs built with this helper.
*
* A config is plain data: it can be hoisted to module scope, created inline
* per render, or memoized — the provider never relies on config identity.
*
* @example
* ```tsx
* const aui = useAui();
* const config = AuiConfig({
*   message: Derived({
*     source: "thread",
*     query: { index: 0 },
*     get: (aui) => aui.thread.message({ index: 0 }),
*   }),
* });
*
* <AuiProvider extends={aui} config={config}>{children}</AuiProvider>;
* ```
*/
const AuiConfig = (config) => config;
//#endregion
export { AuiConfig };
