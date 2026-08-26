import { useEffect, useMemo, useRef } from 'react'
import { ArrowLeft, Check, ChevronDown, Copy, ListChecks, Trash2 } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { APP_SHELL_PAGE_CLASS_NAME } from '@/app/page-shell-style'
import { SUPPORTED_INSTALL_AGENTS } from '@/features/install-selection/install-agents'
import { useInstallSelectionStore } from '@/features/install-selection/install-selection-store'
import { buildSkillhubInstallCommand, getCliRegistryUrl } from '@/features/skill/install-command'
import { useCopyToClipboard } from '@/shared/lib/clipboard'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'

interface CommandRowProps {
  command: string
  skillName: string
  copyDisabled: boolean
}

function CommandRow({ command, skillName, copyDisabled }: CommandRowProps) {
  const { t } = useTranslation()
  const [copied, copy] = useCopyToClipboard()

  const handleCopy = async () => {
    try {
      await copy(command)
    } catch (error) {
      console.error('Failed to copy install command:', error)
    }
  }

  return (
    <div className="relative overflow-hidden rounded-lg border bg-muted/40">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        disabled={copyDisabled}
        aria-label={t('installSkills.copyCommand', { skill: skillName })}
        onClick={handleCopy}
        className="absolute right-2 top-2 h-8 w-8 bg-background/80"
      >
        {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
      </Button>
      <pre className="overflow-x-auto px-4 py-3 pr-14 text-sm">
        <code className="whitespace-pre-wrap break-all font-mono">{command}</code>
      </pre>
    </div>
  )
}

export function InstallSkillsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const previousSelectedCountRef = useRef<number | null>(null)
  const selectedSkills = useInstallSelectionStore((state) => state.selectedSkills)
  const scope = useInstallSelectionStore((state) => state.scope)
  const selectedAgentId = useInstallSelectionStore((state) => state.selectedAgentId)
  const removeSkill = useInstallSelectionStore((state) => state.removeSkill)
  const clearSelection = useInstallSelectionStore((state) => state.clearSelection)
  const setScope = useInstallSelectionStore((state) => state.setScope)
  const setAgent = useInstallSelectionStore((state) => state.setAgent)
  const [copiedAll, copyAll] = useCopyToClipboard()
  const registryUrl = useMemo(() => getCliRegistryUrl(), [])
  const hasSelectedAgent = selectedAgentId !== null
  const commands = useMemo(
    () => selectedSkills.map((skill) => ({
      skill,
      command: buildSkillhubInstallCommand(skill.namespace, skill.slug, registryUrl, {
        scope,
        agentId: selectedAgentId ?? undefined,
        force: true,
      }),
    })),
    [registryUrl, scope, selectedAgentId, selectedSkills],
  )

  useEffect(() => {
    const previousSelectedCount = previousSelectedCountRef.current
    previousSelectedCountRef.current = selectedSkills.length
    if (previousSelectedCount === null || (previousSelectedCount > 0 && selectedSkills.length === 0)) {
      headingRef.current?.focus()
    }
  }, [selectedSkills.length])

  const handleCopyAll = async () => {
    try {
      await copyAll(commands.map((item) => item.command).join('\n'))
    } catch (error) {
      console.error('Failed to copy install commands:', error)
    }
  }

  return (
    <div className={`${APP_SHELL_PAGE_CLASS_NAME} max-w-5xl mx-auto !space-y-4`}>
      <div className="space-y-1">
        <Button
          type="button"
          variant="ghost"
          className="-ml-3"
          onClick={() => navigate({
            to: '/search',
            search: { q: '', sort: 'relevance', page: 0, starredOnly: false },
          })}
        >
          <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
          {t('installSkills.backToSearch')}
        </Button>
        <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold tracking-tight outline-none">
          {t('installSkills.title')}
        </h1>
      </div>

      {selectedSkills.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">{t('installSkills.empty')}</p>
        </Card>
      ) : (
        <>
          <Card className="space-y-3 p-4">
            <h2 className="text-lg font-semibold">{t('installSkills.targetsHeading')}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <fieldset>
                <legend className="mb-2 text-sm font-semibold">{t('installSkills.scopeHeading')}</legend>
                <div className="flex flex-wrap gap-5">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="install-scope"
                      checked={scope === 'user'}
                      onChange={() => setScope('user')}
                      className="h-4 w-4 accent-primary"
                    />
                    {t('installSkills.scopeUser')}
                  </label>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="install-scope"
                      checked={scope === 'project'}
                      onChange={() => setScope('project')}
                      className="h-4 w-4 accent-primary"
                    />
                    {t('installSkills.scopeProject')}
                  </label>
                </div>
                {scope === 'project' && (
                  <p className="mt-2 text-xs font-medium text-amber-800">
                    {t('installSkills.projectWarning')}
                  </p>
                )}
              </fieldset>

              <div>
                <label htmlFor="install-agent" className="mb-2 block text-sm font-semibold">
                  {t('installSkills.agentsHeading')}
                </label>
                <select
                  id="install-agent"
                  value={selectedAgentId ?? ''}
                  onChange={(event) => setAgent(event.target.value || null)}
                  className="h-10 w-full rounded-lg border border-border/60 bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                >
                  <option value="">{t('installSkills.agentPlaceholder')}</option>
                  {SUPPORTED_INSTALL_AGENTS.map((agent) => (
                    <option key={agent.id} value={agent.id}>{agent.label}</option>
                  ))}
                </select>
                {!hasSelectedAgent && (
                  <p role="alert" className="mt-2 text-xs font-medium text-destructive">
                    {t('installSkills.selectAgentRequired')}
                  </p>
                )}
              </div>
            </div>
          </Card>

          <Card className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{t('installSkills.commandsHeading')}</h2>
                <p className="text-sm text-muted-foreground">{t('installSkills.commandsHint')}</p>
              </div>
              <Button type="button" disabled={!hasSelectedAgent} onClick={handleCopyAll}>
                {copiedAll ? <Check className="mr-2 h-4 w-4" aria-hidden="true" /> : <Copy className="mr-2 h-4 w-4" aria-hidden="true" />}
                {copiedAll ? t('copyButton.copied') : t('installSkills.copyAll')}
              </Button>
            </div>
            {hasSelectedAgent ? (
              <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                {commands.map(({ command, skill }) => (
                  <CommandRow
                    key={`${skill.namespace}/${skill.slug}`}
                    command={command}
                    skillName={skill.displayName}
                    copyDisabled={!hasSelectedAgent}
                  />
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed p-3 text-center text-sm text-muted-foreground">
                {t('installSkills.selectAgentRequired')}
              </p>
            )}
          </Card>

          <Card className="p-4">
            <details open className="group">
              <summary className="flex cursor-pointer list-none select-none items-center justify-between rounded-xl bg-muted/50 px-3 py-2.5 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <ListChecks className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span className="font-semibold">
                    {t('installSkills.selectedHeading', { count: selectedSkills.length })}
                  </span>
                </span>
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
              </summary>
              <div className="mt-2 flex items-center justify-end">
                <Button type="button" variant="ghost" size="sm" onClick={clearSelection}>
                  {t('installSelection.clear')}
                </Button>
              </div>
              <ul
                data-visible-skill-rows="3"
                className="max-h-48 divide-y overflow-y-auto border-t"
              >
                {selectedSkills.map((skill) => (
                  <li key={`${skill.namespace}/${skill.slug}`} className="flex min-h-16 items-center justify-between gap-4 py-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{skill.displayName}</p>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {skill.namespace}/{skill.slug}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('installSkills.removeSkill', { skill: skill.displayName })}
                      onClick={() => removeSkill(skill)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </li>
                ))}
              </ul>
            </details>
          </Card>
        </>
      )}
    </div>
  )
}
