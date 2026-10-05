"use strict";

const { test, expect } = require("bun:test");
const { buildArgs, parsePort } = require("./launcher.cjs");

const SERVING_LINE =
  "crow-web serving /srv/www on http://127.0.0.1:45678 (sh for terminals, acp via ws://127.0.0.1:2769/acp)";

test("buildArgs always asks for an ephemeral port", () => {
  expect(buildArgs()).toEqual(["--port", "0"]);
});

test("buildArgs appends the launch options after --port 0", () => {
  expect(
    buildArgs({ root: "/srv/www", acpUrl: "ws://127.0.0.1:2769/acp" }),
  ).toEqual(["--port", "0", "--root", "/srv/www", "--acp-url", "ws://127.0.0.1:2769/acp"]);
});

test("parsePort reads the bound address from the serving line", () => {
  expect(parsePort(SERVING_LINE)).toBe(45678);
});

test("parsePort returns null for a line with no http address", () => {
  expect(parsePort("hello world")).toBeNull();
});
