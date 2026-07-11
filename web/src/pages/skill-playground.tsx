import { useState } from 'react'
import { Link, useParams, useSearch } from '@tanstack/react-router'
import { ArrowLeft, LockKeyhole } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { PlaygroundChat } from '@/features/playground/playground-chat'
import {
  PlaygroundContextDrawer,
  PlaygroundContextPanel,
} from '@/features/playground/playground-context'
import { usePlayground } from '@/features/playground/use-playground'
import { useSkillDetail, useSkillVersions } from '@/shared/hooks/use-skill-queries'


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
  const selectedPath =
    contextFiles.find((file) => file.path === requestedPath)?.path ??
    contextFiles[0]?.path ??
    null
  const displayName = playground.session?.skill.displayName || skill?.displayName || slug

  return (
    <div className="mx-auto w-full max-w-[1440px] px-3 py-3 sm:px-6 sm:py-5">
      <div
        data-playground-workspace
        className="overflow-hidden rounded-lg border border-[#25272D] bg-[#09090B] text-[#F7F8F8]"
      >
        <header className="flex min-h-16 items-center gap-3 border-b border-[#25272D] px-3 sm:px-4">
          <Link
            to="/space/$namespace/$slug"
            params={{ namespace, slug }}
            className="inline-flex h-11 shrink-0 items-center gap-1 rounded-md px-2 text-xs text-[#A4A9B3] transition-colors hover:bg-[#17181D] hover:text-[#F7F8F8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">{t('playground.backToSkill')}</span>
          </Link>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold text-[#F7F8F8] sm:text-base">
              {displayName}
            </h1>
            <p className="flex min-w-0 items-center gap-1 font-mono text-xs text-[#858B96]">
              <span className="truncate">
                {namespace}/{slug}
                {version ? ` @ ${version}` : ''}
              </span>
              <span
                data-playground-mobile-limits
                className="shrink-0 font-sans text-[11px] text-[#A4A9B3] md:hidden"
              >
                {t('playground.readOnly')} · {t('playground.promptOnly')}
              </span>
            </p>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <span className="inline-flex h-7 items-center gap-1 rounded-md border border-[#343740] px-2 text-xs text-[#A4A9B3]">
              <LockKeyhole className="h-3.5 w-3.5" />
              {t('playground.readOnly')}
            </span>
            <span className="inline-flex h-7 items-center rounded-md bg-[#17181D] px-2 text-xs text-[#A4A9B3]">
              {t('playground.promptOnly')}
            </span>
          </div>
          <PlaygroundContextDrawer
            files={contextFiles}
            selectedPath={selectedPath}
            onSelectedPathChange={setRequestedPath}
          />
        </header>

        <div className="grid h-[calc(100dvh-13rem)] min-h-0 min-[900px]:h-[clamp(28rem,calc(100dvh-13rem),48rem)] min-[900px]:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]">
          <PlaygroundChat
            state={playground.state}
            messages={playground.messages}
            isSending={playground.isSending}
            namespace={namespace}
            slug={slug}
            errorCode={playground.errorCode}
            onSend={playground.send}
            onReset={playground.reset}
          />
          <PlaygroundContextPanel
            files={contextFiles}
            selectedPath={selectedPath}
            onSelectedPathChange={setRequestedPath}
          />
        </div>
      </div>
    </div>
  )
}
