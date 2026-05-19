import { permanentRedirect } from "next/navigation";

/**
 * Stable SEO landing for the "Claude Code i18n" search term.
 * The canonical page is /agents (multi-agent: Claude Code, Cursor, Cline,
 * Windsurf, any MCP host). 308 preserves link equity into the new URL.
 */
export default function ClaudeCodeRedirect() {
  permanentRedirect("/agents");
}
