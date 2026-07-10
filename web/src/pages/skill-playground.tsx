import { useState } from 'react'
import { Link, useParams, useSearch } from '@tanstack/react-router'
import { ArrowLeft, FileText, LockKeyhole } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { PlaygroundChat } from '@/features/playground/playground-chat'
import { usePlayground } from '@/features/playground/use-playground'
import { useSkillDetail, useSkillVersions } from '@/shared/hooks/use-skill-queries'
import { cn } from '@/shared/lib/utils'


export function SkillPlaygroundPage() {
  const { t } = useTranslation()
  const { namespace, slug } = useParams({ strict: false }) as {
    namespace: string
    slug: string
  }
  const search = useSearch({ strict: false }) as { version?: string }
  const { data: skill } = useSkillDetail(namespace, slug)
  const { data: versions } = useSkillVersions(namespace, slug)
  const version =
    search.version ||
    skill?.publishedVersion?.version ||
    skill?.ownerPreviewVersion?.version ||
    versions?.[0]?.version
  const playground = usePlayground({
    namespace,
    slug,
    version,
    enabled: Boolean(version),
  })
  const [requestedPath, setRequestedPath] = useState<string | null>(null)
  const contextFiles = playground.session?.contextFiles ?? []
  const selectedFile =
    contextFiles.find((file) => file.path === requestedPath) ?? contextFiles[0]
  const displayName = playground.session?.skill.displayName || skill?.displayName || slug

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/space/$namespace/$slug"
            params={{ namespace, slug }}
            className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {t('playground.backToSkill')}
          </Link>
          <h1 className="truncate text-xl font-semibold text-foreground">
            {displayName} · {t('playground.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {namespace}/{slug}
            {version ? ` @ ${version}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-muted-foreground">
            <LockKeyhole className="h-3.5 w-3.5" />
            {t('playground.readOnly')}
          </span>
          <span className="inline-flex h-7 items-center rounded-md bg-secondary px-2 text-xs text-secondary-foreground">
            {t('playground.promptOnly')}
          </span>
        </div>
      </header>

      <div className="grid min-h-[560px] overflow-hidden border border-border bg-background lg:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]">
        <aside className="min-w-0 border-b border-border lg:border-b-0 lg:border-r">
          <div className="flex h-14 items-center border-b border-border px-4">
            <h2 className="text-sm font-semibold text-foreground">
              {t('playground.context')}
            </h2>
          </div>
          <div className="grid min-h-[505px] grid-cols-[112px_minmax(0,1fr)] lg:block">
            <nav className="border-r border-border p-2 lg:border-b lg:border-r-0">
              {contextFiles.length === 0 ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">
                  {t('playground.noContext')}
                </p>
              ) : (
                contextFiles.map((file) => (
                  <button
                    key={file.path}
                    type="button"
                    onClick={() => setRequestedPath(file.path)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs transition-colors',
                      selectedFile?.path === file.path
                        ? 'bg-secondary text-foreground'
                        : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                    )}
                    title={file.path}
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{file.path}</span>
                  </button>
                ))
              )}
            </nav>
            <div className="max-h-[455px] min-w-0 overflow-auto p-4">
              {selectedFile ? (
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-5 text-foreground">
                  {selectedFile.content}
                </pre>
              ) : (
                <div className="text-xs text-muted-foreground">
                  {t('playground.noContext')}
                </div>
              )}
            </div>
          </div>
        </aside>

        <PlaygroundChat
          state={playground.state}
          messages={playground.messages}
          isSending={playground.isSending}
          onSend={playground.send}
          onReset={playground.reset}
        />
      </div>
    </div>
  )
}
