import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { normalizeSearchQuery, parseNamespaceSearchInput } from '@/shared/lib/search-query'
import { SearchBar } from '@/features/search/search-bar'
import { NamespaceSearchFilter } from '@/features/search/namespace-search-filter'
import { LandingQuickStartSection } from '@/shared/components/landing-quick-start'
import { SkillCard } from '@/features/skill/skill-card'
import { SkeletonList } from '@/shared/components/skeleton-loader'
import { useSearchSkills } from '@/shared/hooks/use-skill-queries'
import { useInView } from '@/shared/hooks/use-in-view'
import { Button } from '@/shared/ui/button'

/**
 * Marketing-style landing page for unauthenticated and first-time visitors.
 *
 * The page mixes static positioning content with live skill queries so popular and latest skills
 * stay aligned with the current registry state.
 */
export function LandingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [namespace, setNamespace] = useState('')

  const { data: popularSkills, isLoading: isLoadingPopular } = useSearchSkills({
    sort: 'downloads',
    size: 6,
  })

  const { data: latestSkills, isLoading: isLoadingLatest } = useSearchSkills({
    sort: 'newest',
    size: 6,
  })

  const handleSkillClick = (namespace: string, slug: string) => {
    navigate({ to: `/space/${namespace}/${encodeURIComponent(slug)}` })
  }

  const heroView = useInView()
  const quickStartView = useInView()
  const popularView = useInView()
  const latestView = useInView()

  const handleSearch = (query: string) => {
    const parsed = parseNamespaceSearchInput(query)
    const selectedNamespace = parsed.namespace || namespace
    navigate({
      to: '/search',
      search: {
        q: normalizeSearchQuery(parsed.query),
        ...(selectedNamespace ? { namespace: selectedNamespace } : {}),
        sort: 'relevance', page: 0, starredOnly: false,
      },
    })
  }

  return (
    <>
      {/* Hero Section */}
      <main ref={heroView.ref} className={`relative z-10 flex flex-col items-center pt-16 pb-20 px-4 md:pt-24 scroll-fade-up${heroView.inView ? ' in-view' : ''}`}>
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-brand-gradient mb-4">
          SkillHub
        </h1>
        <h2
          className="text-xl md:text-2xl font-semibold tracking-tight text-center mb-3"
          style={{ color: 'hsl(var(--foreground))' }}
        >
          {t('landing.hero.title')}
        </h2>
        <p
          className="text-base md:text-lg text-center max-w-2xl mb-10 leading-relaxed"
          style={{ color: 'hsl(var(--text-secondary))' }}
        >
          {t('landing.hero.subtitle')}
        </p>

        {/* Search box */}
        <div className="w-full max-w-2xl mb-8">
          <SearchBar
            placeholder={t('landing.hero.searchPlaceholder')}
            onSearch={handleSearch}
            leadingControl={<NamespaceSearchFilter value={namespace} onValueChange={setNamespace} />}
          />
        </div>

        {/* CTA buttons */}
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            to="/search"
            search={{ q: '', sort: 'relevance', page: 0, starredOnly: false }}
            className="px-8 py-3.5 rounded-xl text-base font-medium text-white bg-brand-gradient shadow-sm hover:opacity-95 transition-opacity"
          >
            {t('landing.hero.exploreSkills')}
          </Link>
          <Link
            to="/dashboard/publish"
            className="px-8 py-3.5 rounded-xl text-base font-medium border transition-colors"
            style={{
              background: 'hsl(var(--secondary))',
              borderColor: 'hsl(var(--muted-foreground))',
              color: 'hsl(var(--muted-foreground))',
            }}
          >
            {t('landing.hero.publishSkill', { defaultValue: '开始构建' })}
          </Link>
        </div>

      </main>

      {/* Quick Start */}
      <div ref={quickStartView.ref} className={`scroll-fade-up${quickStartView.inView ? ' in-view' : ''}`}>
        <LandingQuickStartSection />
      </div>

      {/* Popular Downloads Section */}
      <section ref={popularView.ref} className={`relative z-10 w-full py-20 md:py-24 px-6 scroll-fade-up${popularView.inView ? ' in-view' : ''}`} style={{ background: 'var(--bg-page, hsl(var(--background)))' }}>
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-bold tracking-tight mb-2" style={{ color: 'hsl(var(--foreground))' }}>
                {t('home.popularTitle')}
              </h2>
              <p style={{ color: 'hsl(var(--text-secondary))' }}>{t('home.popularDescription')}</p>
            </div>
            <Button
              variant="ghost"
              onClick={() => navigate({ to: '/search', search: { q: '', sort: 'downloads', page: 0, starredOnly: false } })}
            >
              {t('home.viewAll')}
            </Button>
          </div>
          {isLoadingPopular ? (
            <SkeletonList count={6} />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {popularSkills?.items.map((skill, idx) => (
                <div key={skill.id} className={`animate-fade-up delay-${Math.min(idx + 1, 6)}`}>
                  <SkillCard
                    skill={skill}
                    onClick={() => handleSkillClick(skill.namespace, skill.slug)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Latest Releases Section */}
      <section ref={latestView.ref} className={`relative z-10 w-full py-20 md:py-24 px-6 scroll-fade-up${latestView.inView ? ' in-view' : ''}`} style={{ background: 'var(--bg-page, hsl(var(--background)))' }}>
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-bold tracking-tight mb-2" style={{ color: 'hsl(var(--foreground))' }}>
                {t('home.latestTitle')}
              </h2>
              <p style={{ color: 'hsl(var(--text-secondary))' }}>{t('home.latestDescription')}</p>
            </div>
            <Button
              variant="ghost"
              onClick={() => navigate({ to: '/search', search: { q: '', sort: 'newest', page: 0, starredOnly: false } })}
            >
              {t('home.viewAll')}
            </Button>
          </div>
          {isLoadingLatest ? (
            <SkeletonList count={6} />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {latestSkills?.items.map((skill, idx) => (
                <div key={skill.id} className={`animate-fade-up delay-${Math.min(idx + 1, 6)}`}>
                  <SkillCard
                    skill={skill}
                    onClick={() => handleSkillClick(skill.namespace, skill.slug)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  )
}
