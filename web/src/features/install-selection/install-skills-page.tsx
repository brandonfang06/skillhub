import { useEffect, useMemo, useRef } from 'react'
import { ArrowLeft, Check, Copy, Trash2 } from 'lucide-react'
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
  const selectedAgentIds = useInstallSelectionStore((state) => state.selectedAgentIds)
  const force = useInstallSelectionStore((state) => state.force)
  const removeSkill = useInstallSelectionStore((state) => state.removeSkill)
  const clearSelection = useInstallSelectionStore((state) => state.clearSelection)
  const setScope = useInstallSelectionStore((state) => state.setScope)
  const toggleAgent = useInstallSelectionStore((state) => state.toggleAgent)
  const setForce = useInstallSelectionStore((state) => state.setForce)
  const [copiedAll, copyAll] = useCopyToClipboard()
  const registryUrl = useMemo(() => getCliRegistryUrl(), [])
  const hasSelectedAgent = selectedAgentIds.length > 0
  const commands = useMemo(
    () => selectedSkills.map((skill) => ({
      skill,
      command: buildSkillhubInstallCommand(skill.namespace, skill.slug, registryUrl, {
        scope,
        agentIds: selectedAgentIds,
        force,
      }),
    })),
    [force, registryUrl, scope, selectedAgentIds, selectedSkills],
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
    <div className={`${APP_SHELL_PAGE_CLASS_NAME} max-w-5xl mx-auto`}>
      <div className="space-y-2">
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
        <h1 ref={headingRef} tabIndex={-1} className="text-3xl font-bold tracking-tight outline-none">
          {t('installSkills.title')}
        </h1>
        <p className="text-muted-foreground">
          {t('installSkills.subtitle')}
        </p>
      </div>

      {selectedSkills.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">{t('installSkills.empty')}</p>
        </Card>
      ) : (
        <>
          <Card className="p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">
                {t('installSkills.selectedHeading', { count: selectedSkills.length })}
              </h2>
              <Button type="button" variant="ghost" size="sm" onClick={clearSelection}>
                {t('installSelection.clear')}
              </Button>
            </div>
            <ul className="divide-y">
              {selectedSkills.map((skill) => (
                <li key={`${skill.namespace}/${skill.slug}`} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
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
          </Card>

          <Card className="space-y-6 p-5">
            <fieldset>
              <legend className="mb-3 font-semibold">{t('installSkills.scopeHeading')}</legend>
              <div className="flex flex-wrap gap-5">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="radio"
                    name="install-scope"
                    checked={scope === 'user'}
                    onChange={() => setScope('user')}
                    className="h-4 w-4 accent-primary"
                  />
                  {t('installSkills.scopeUser')}
                </label>
                <label className="flex cursor-pointer items-center gap-2">
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
                <p className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                  {t('installSkills.projectWarning')}
                </p>
              )}
            </fieldset>

            <fieldset>
              <legend className="mb-1 font-semibold">{t('installSkills.agentsHeading')}</legend>
              <p className="mb-3 text-sm text-muted-foreground">{t('installSkills.agentsHint')}</p>
              <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                {SUPPORTED_INSTALL_AGENTS.map((agent) => (
                  <label key={agent.id} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedAgentIds.includes(agent.id)}
                      onChange={() => toggleAgent(agent.id)}
                      className="h-4 w-4 accent-primary"
                    />
                    {agent.label}
                  </label>
                ))}
              </div>
              <p className="mt-3 text-sm text-muted-foreground">{t('installSkills.genericUnsupported')}</p>
              {!hasSelectedAgent && (
                <p role="alert" className="mt-2 text-sm font-medium text-destructive">
                  {t('installSkills.selectAgentRequired')}
                </p>
              )}
            </fieldset>
          </Card>

          <Card className="space-y-3 p-5">
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                aria-label={t('installSkills.forceLabel')}
                checked={force}
                onChange={(event) => setForce(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-primary"
              />
              <span>
                <span className="block font-semibold">{t('installSkills.forceLabel')}</span>
                <span className="block text-sm text-muted-foreground">{t('installSkills.forceHint')}</span>
              </span>
            </label>
            {force && (
              <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {t('installSkills.forceWarning')}
              </p>
            )}
          </Card>

          <Card className="space-y-3 p-5">
            <h2 className="text-lg font-semibold">{t('installSkills.identityHeading')}</h2>
            <p className="text-sm text-muted-foreground">{t('installSkills.identityHint')}</p>
            <pre className="overflow-x-auto rounded-lg border bg-muted/40 px-4 py-3 text-sm">
              <code className="font-mono">npx @astron-team/skillhub@latest whoami --registry {registryUrl}</code>
            </pre>
          </Card>

          <Card className="space-y-4 p-5">
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
              <div className="space-y-3">
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
              <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                {t('installSkills.selectAgentRequired')}
              </p>
            )}
            <p className="text-sm text-muted-foreground">{t('installSkills.resultHint')}</p>
          </Card>
        </>
      )}
    </div>
  )
}
