import type { Browser, BrowserContext, Page, TestInfo } from '@playwright/test'
import { createFreshSession, loginWithCredentials, registerSession } from './session'
import {
  E2eTestDataBuilder,
  type SeededReviewData,
  type SeedSkillOptions,
} from './test-data-builder'

function getOptionalEnv(name: string): string | undefined {
  const value = process.env[name]?.trim()
  return value ? value : undefined
}

function adminCredentials() {
  return {
    username: getOptionalEnv('E2E_ADMIN_USERNAME') ?? getOptionalEnv('BOOTSTRAP_ADMIN_USERNAME') ?? 'admin',
    password: getOptionalEnv('E2E_ADMIN_PASSWORD') ?? getOptionalEnv('BOOTSTRAP_ADMIN_PASSWORD') ?? 'ChangeMe!2026',
  }
}

function matchCandidateUsername(
  candidate: { userId: string; displayName: string; email?: string },
  username: string,
) {
  return candidate.userId === username
    || candidate.displayName === username
    || candidate.email === `${username}@example.test`
}

export async function createNamespaceReviewData(
  browser: Browser,
  page: Page,
  testInfo: TestInfo,
  skillOptions?: SeedSkillOptions,
): Promise<SeededReviewData & { reviewTaskId: number; cleanup: () => Promise<void> }> {
  const reviewerCredentials = await registerSession(page, testInfo, { allowMockSession: false })
  const baseURL = getOptionalEnv('E2E_BASE_URL') ?? String(testInfo.project.use.baseURL)

  let adminContext: BrowserContext | undefined
  let submitterContext: BrowserContext | undefined
  let adminBuilder: E2eTestDataBuilder | undefined
  let submitterBuilder: E2eTestDataBuilder | undefined

  const cleanup = async () => {
    let cleanupError: unknown
    try {
      await submitterBuilder?.cleanup()
    } catch (error) {
      cleanupError = error
    }
    try {
      await adminBuilder?.cleanup()
    } catch (error) {
      cleanupError ??= error
    }
    try {
      await submitterContext?.close()
    } catch (error) {
      cleanupError ??= error
    }
    try {
      await adminContext?.close()
    } catch (error) {
      cleanupError ??= error
    }
    if (cleanupError) {
      throw cleanupError
    }
  }

  try {
    adminContext = await browser.newContext({ baseURL })
    const adminPage = await adminContext.newPage()
    adminBuilder = new E2eTestDataBuilder(adminPage, testInfo)
    submitterContext = await browser.newContext({ baseURL })
    const submitterPage = await submitterContext.newPage()
    submitterBuilder = new E2eTestDataBuilder(submitterPage, testInfo)

    await loginWithCredentials(adminPage, adminCredentials(), testInfo)
    await adminBuilder.init()
    await createFreshSession(submitterPage, testInfo)
    await submitterBuilder.init()

    const namespace = await adminBuilder.createNamespace('e2e-team')
    const reviewerCandidates = await adminBuilder.searchNamespaceMemberCandidates(
      namespace.slug,
      reviewerCredentials.username,
    )
    const reviewerCandidate = reviewerCandidates.find((candidate) => (
      matchCandidateUsername(candidate, reviewerCredentials.username)
    ))
    if (!reviewerCandidate) {
      throw new Error(`No namespace member candidate found for reviewer ${reviewerCredentials.username}`)
    }
    await adminBuilder.addNamespaceMember(namespace.slug, reviewerCandidate.userId, 'ADMIN')

    const submitterResponse = await submitterPage.context().request.get('/api/v1/auth/me')
    const submitter = await submitterResponse.json() as { data?: { userId?: string } }
    const submitterId = submitter.data?.userId
    if (!submitterId) {
      throw new Error('No authenticated submitter found for review data')
    }
    await adminBuilder.addNamespaceMember(namespace.slug, submitterId, 'MEMBER')

    const skill = await submitterBuilder.publishSkill(namespace.slug, skillOptions)
    const reviewTaskId = await adminBuilder.waitForPendingReview(namespace.slug, skill.slug, skill.version)

    return { namespace, skill, reviewTaskId, cleanup }
  } catch (error) {
    try {
      await cleanup()
    } catch {
      // Preserve the setup failure; cleanup is best-effort on this path.
    }
    throw error
  }
}
