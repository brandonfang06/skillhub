export const SUPPORTED_INSTALL_AGENTS = [
  { id: 'claude-code', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'cursor', label: 'Cursor' },
  { id: 'github-copilot', label: 'GitHub Copilot' },
  { id: 'gemini-cli', label: 'Gemini CLI' },
  { id: 'openhands', label: 'OpenHands' },
  { id: 'windsurf', label: 'Windsurf' },
  { id: 'openclaw', label: 'OpenClaw' },
  { id: 'kiro-cli', label: 'Kiro CLI' },
  { id: 'roo', label: 'Roo' },
  { id: 'trae', label: 'Trae' },
  { id: 'trae-cn', label: 'Trae CN' },
  { id: 'opencode', label: 'OpenCode' },
  { id: 'kilo', label: 'Kilo' },
] as const

const SUPPORTED_INSTALL_AGENT_IDS = new Set<string>(
  SUPPORTED_INSTALL_AGENTS.map((agent) => agent.id),
)

export function normalizeInstallAgentIds(agentIds: readonly string[]): string[] {
  const selectedIds = new Set(agentIds.filter((agentId) => SUPPORTED_INSTALL_AGENT_IDS.has(agentId)))
  return SUPPORTED_INSTALL_AGENTS
    .map((agent) => agent.id)
    .filter((agentId) => selectedIds.has(agentId))
}
