import path from "node:path";
import { createRequire } from "node:module";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const CROW_WEB = process.env.CROW_WEB_URL ?? "ws://127.0.0.1:2770";

// Vite 8's rolldown dep optimizer emits only a default export for CJS deps
// (vitejs/vite#23030 family), so `export * from "react"` inside the linked
// monorepo dists (packages/tap/dist/react-shim) links to nothing in the
// browser: "does not provide an export named 'Component'". Bundled builds
// resolve the star export at bundle time, so this is dev-only: rewrite it
// into explicit interop re-exports enumerated from the CJS module itself.
function reactStarExportInterop(): Plugin {
  const require_ = createRequire(import.meta.url);
  return {
    name: "react-star-export-interop",
    apply: "serve",
    transform(code, id) {
      if (!id.includes("/dist/") || !/export \* from ["']react["']/.test(code)) {
        return null;
      }
      const own = new Set<string>();
      for (const m of code.matchAll(/export \{([^}]*)\}/g)) {
        for (const part of m[1].split(",")) {
          const as = part.trim().split(/\s+as\s+/);
          own.add((as[1] ?? as[0]).trim());
        }
      }
      const reactExports = Object.keys(require_("react")).filter(
        (name) => name !== "default" && !own.has(name),
      );
      const interop = [
        'import __react_cjs from "react";',
        ...reactExports.map(
          (name) => `export const ${name} = __react_cjs.${name};`,
        ),
      ].join("\n");
      return { code: code.replace(/export \* from ["']react["'];?/, interop), map: null };
    },
  };
}

export default defineConfig({
  plugins: [reactStarExportInterop(), react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
    // one React and one @assistant-ui/* in the graph — the vendored aui
    // packages must not pull a second copy from npm
    dedupe: ["react", "react-dom", "@assistant-ui/react", "@assistant-ui/core"],
  },
  optimizeDeps: {
    include: ["remark-gfm"],
  },
  server: {
    port: 5173,
    // crow-web owns the file buffers and the ptys. Proxying keeps the browser
    // on one origin, so the server's loopback-Origin rule still sees
    // localhost:5173 and the client can use relative ws URLs.
    proxy: {
      "/fs": { target: CROW_WEB, ws: true },
      "/pty": { target: CROW_WEB, ws: true },
    },
    fs: {
      // the workspace packages (aui, editor) live above the app root
      allow: [path.resolve(import.meta.dirname, "../..")],
    },
  },
});
