import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const chat = path.resolve(import.meta.dirname, "../chat");
export default defineConfig({
  root: chat,
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.join(chat, "src") },
    dedupe: ["react", "react-dom", "@assistant-ui/react", "@assistant-ui/core"],
  },
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/webview"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rolldownOptions: {
      input: path.join(chat, "src/vscode.tsx"),
      output: {
        entryFileNames: "chat.js",
        assetFileNames: (asset) => asset.names.some((name) => name.endsWith(".css")) ? "chat.css" : "assets/[name]-[hash][extname]",
      },
    },
  },
});
