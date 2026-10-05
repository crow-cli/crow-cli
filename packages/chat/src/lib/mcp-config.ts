import { parse as parseYaml } from "yaml";
import type { AcpMcpServer } from "@assistant-ui/acp";

/**
 * Mirrors the mcpServers section of ~/.agents/crow/config.yaml — the tool
 * supply crow-cli agents get by default. The ACP agent has no builtin
 * fallback: whatever the client passes at session/new is all the tools the
 * session gets, so this ships as the default instead of an empty list.
 */
export const DEFAULT_MCP_CONFIG = `mcpServers:
  crow-mcp:
    transport: stdio
    command: /home/thomas/.agents/crow/src/crow-cli/.venv/bin/crow-cli
    args:
      - mcp2
`;

type Pair = { name: string; value: string };

function pairs(
  raw: unknown,
  where: string,
): { list: Pair[]; error?: string } {
  if (raw === undefined || raw === null) return { list: [] };
  if (Array.isArray(raw)) {
    const list = raw.map((entry) => ({
      name: String((entry as Pair).name ?? ""),
      value: String((entry as Pair).value ?? ""),
    }));
    return list.every((p) => p.name)
      ? { list }
      : { list: [], error: `${where}: list entries need {name, value}` };
  }
  if (typeof raw === "object") {
    return {
      list: Object.entries(raw as Record<string, unknown>).map(([name, value]) => ({
        name,
        value: String(value),
      })),
    };
  }
  return { list: [], error: `${where}: expected a mapping or a list` };
}

function normalize(name: string, cfg: unknown): { server?: AcpMcpServer; error?: string } {
  if (typeof cfg !== "object" || cfg === null) {
    return { error: `${name}: expected a mapping` };
  }
  const c = cfg as Record<string, unknown>;
  const transport = (c.transport as string | undefined) ?? (c.command ? "stdio" : c.url ? "http" : undefined);
  if (transport === "stdio" || (transport === undefined && c.command)) {
    if (typeof c.command !== "string") return { error: `${name}: stdio server needs a command` };
    const args = Array.isArray(c.args) ? c.args.map(String) : c.args === undefined ? [] : [String(c.args)];
    const env = pairs(c.env, `${name}.env`);
    if (env.error) return { error: env.error };
    return { server: { name, command: c.command, args, env: env.list } };
  }
  if (transport === "http" || transport === "sse") {
    if (typeof c.url !== "string") return { error: `${name}: ${transport} server needs a url` };
    const headers = pairs(c.headers, `${name}.headers`);
    if (headers.error) return { error: headers.error };
    return { server: { type: transport, name, url: c.url, headers: headers.list } };
  }
  return { error: `${name}: cannot tell the transport (stdio needs command, http/sse need url)` };
}

/** Accepts JSON or YAML, as a name->server map (config.yaml shape, with or
 *  without the wrapping mcpServers key) or as a list carrying name itself. */
export function parseMcpConfig(text: string): { servers: AcpMcpServer[]; error?: string } {
  const trimmed = text.trim();
  if (!trimmed) return { servers: [] };
  let doc: unknown;
  try {
    doc = parseYaml(trimmed);
  } catch (e) {
    return { servers: [], error: (e as Error).message.split("\n")[0] };
  }
  if (doc && typeof doc === "object" && !Array.isArray(doc) && "mcpServers" in doc) {
    doc = (doc as Record<string, unknown>).mcpServers;
  }
  const entries: [string, unknown][] = Array.isArray(doc)
    ? doc.map((entry) => [String((entry as { name?: string }).name ?? ""), entry])
    : doc && typeof doc === "object"
      ? Object.entries(doc as Record<string, unknown>)
      : [];
  if (!doc || entries.length === 0) {
    return { servers: [], error: "expected a mapping of name to server, or a list of servers" };
  }
  const servers: AcpMcpServer[] = [];
  for (const [name, cfg] of entries) {
    if (!name) return { servers: [], error: "every server needs a name" };
    const one = normalize(name, cfg);
    if (one.error) return { servers: [], error: one.error };
    servers.push(one.server as AcpMcpServer);
  }
  return { servers };
}
