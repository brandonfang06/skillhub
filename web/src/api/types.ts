import type { components } from './generated/schema'
import type { components as complianceComponents } from './generated/compliance-schema'
import type { components as reviewComponents } from './generated/reviews-schema'
import type {
  components as namespaceAnalyticsComponents,
  operations as namespaceAnalyticsOperations,
} from './generated/namespace-analytics-schema'
import type { components as SourceImportComponents } from './generated/source-import-schema'

export type SourceProvenance = SourceImportComponents['schemas']['SourceProvenanceResponse']

export interface VersionAttribution {
  type: 'NATIVE_SUBMISSION' | 'OSS_IMPORT'
  submittedBy: string
  submittedByName?: string | null
  submittedAt: string
}

export interface PlaygroundCapability {
  token: string
  expiresAt: number
}

export type User = Omit<components['schemas']['AuthMeResponse'], 'userId' | 'displayName' | 'platformRoles'> & {
  userId: string
  displayName: string
  email?: string
  avatarUrl?: string
  oauthProvider?: string
  canChangePassword?: boolean
  platformRoles: string[]
}

export type OAuthProvider = Omit<components['schemas']['AuthProviderResponse'], 'id' | 'name' | 'authorizationUrl'> & {
  id: string
  name: string
  authorizationUrl: string
}

export interface AuthMethod {
  id: string
  methodType: 'PASSWORD' | 'OAUTH_REDIRECT' | 'DIRECT_PASSWORD' | 'SESSION_BOOTSTRAP' | string
  provider: string
  displayName: string
  actionUrl: string
}

export type ApiToken = Omit<components['schemas']['TokenSummaryResponse'], 'id' | 'name' | 'tokenPrefix' | 'createdAt'> & {
  id: number
  name: string
  tokenPrefix: string
  createdAt: string
  expiresAt?: string
  lastUsedAt?: string
}

export type CreateTokenRequest = Omit<components['schemas']['TokenCreateRequest'], 'name'> & {
  name: string
  scopes?: string[]
  expiresAt?: string
}

export type CreateTokenResponse = Omit<components['schemas']['TokenCreateResponse'], 'token' | 'id' | 'name' | 'tokenPrefix' | 'createdAt'> & {
  token: string
  id: number
  name: string
  tokenPrefix: string
  createdAt: string
  expiresAt?: string
}

export interface LocalLoginRequest {
  username: string
  password: string
}

export interface LocalRegisterRequest extends LocalLoginRequest {
  email: string
}

export interface ChangePasswordRequest {
  currentPassword: string
  newPassword: string
}

export interface PasswordResetRequest {
  email: string
}

export interface PasswordResetConfirmRequest {
  email: string
  code: string
  newPassword: string
}

export type CreateNamespaceRequest = Omit<components['schemas']['NamespaceRequest'], 'slug' | 'displayName'> & {
  slug: string
  displayName: string
  description?: string
}

export interface MergeInitiateRequest {
  secondaryIdentifier: string
}

export interface MergeInitiateResponse {
  mergeRequestId: number
  secondaryUserId: string
  verificationToken: string
  expiresAt: string
}

export interface MergeVerifyRequest {
  mergeRequestId: number
  verificationToken: string
}

export interface MergeConfirmRequest {
  mergeRequestId: number
}

// Namespace types
export type NamespaceStatus = 'ACTIVE' | 'FROZEN' | 'ARCHIVED' | string
export type NamespaceRole = 'OWNER' | 'ADMIN' | 'MEMBER' | string

export interface Namespace {
  id: number
  slug: string
  displayName: string
  description?: string
  type: 'GLOBAL' | 'TEAM'
  avatarUrl?: string
  status: NamespaceStatus
  createdAt: string
  updatedAt?: string
}

export interface ManagedNamespace extends Namespace {
  createdBy?: string
  currentUserRole?: NamespaceRole
  immutable: boolean
  canFreeze: boolean
  canUnfreeze: boolean
  canArchive: boolean
  canRestore: boolean
  deleteAuthorized?: boolean
  canDelete: boolean
  deleteBlockers?: {
    skillCount: number
    reviewTaskCount: number
    promotionRequestCount: number
  }
}

export interface NamespaceMember {
  id: number
  userId: string
  displayName?: string
  email?: string
  role: NamespaceRole
  createdAt: string
}

export interface NamespaceCandidateUser {
  userId: string
  displayName: string
  email?: string
  status: string
}

export interface BatchMemberResult {
  userId: string
  role: string
  success: boolean
  error?: string
}

export interface BatchMemberResponse {
  totalCount: number
  successCount: number
  failureCount: number
  results: BatchMemberResult[]
}

// Skill types
type GeneratedSkillSummary = components['schemas']['SkillSummaryResponse']
type SkillSummaryRequired = {
  id: number
  slug: string
  displayName: string
  summary?: string
  visibility?: string
  status?: string
  downloadCount: number
  starCount: number
  ratingAvg?: number
  ratingCount: number
  namespace: string
  updatedAt: string
  canSubmitPromotion: boolean
  headlineVersion?: SkillLifecycleVersion
  publishedVersion?: SkillLifecycleVersion
  ownerPreviewVersion?: SkillLifecycleVersion
  resolutionMode?: string
}
export type SkillSummary = Omit<GeneratedSkillSummary, keyof SkillSummaryRequired>
  & SkillSummaryRequired
  & ComplianceProjection

export type LabelItem = Omit<components['schemas']['SkillLabelDto'], 'slug' | 'type' | 'displayName'> & {
  slug: string
  type: 'RECOMMENDED' | 'PRIVILEGED' | string
  displayName: string
}

export type LabelTranslation = Omit<components['schemas']['LabelTranslationResponse'], 'locale' | 'displayName'> & {
  locale: string
  displayName: string
}

export type LabelDefinition = Omit<
  components['schemas']['LabelDefinitionResponse'],
  'slug' | 'type' | 'translations' | 'sortOrder' | 'visibleInFilter'
> & {
  slug: string
  type: 'RECOMMENDED' | 'PRIVILEGED' | string
  visibleInFilter: boolean
  sortOrder: number
  translations: LabelTranslation[]
}

export interface AdminLabelInput {
  slug: string
  type: 'RECOMMENDED' | 'PRIVILEGED'
  visibleInFilter: boolean
  sortOrder: number
  translations: LabelTranslation[]
}

export interface DownloadEventItem {
  id: number
  skillId: number
  skillVersionId: number
  namespace: string
  slug: string
  version: string
  source: 'api' | 'web' | 'cli' | string
  userId?: string | null
  username?: string | null
  requestId?: string | null
  ipAddress?: string | null
  userAgent?: string | null
  createdAt: string
}

export type NamespaceAnalyticsData = namespaceAnalyticsComponents['schemas']['NamespaceAnalyticsData']
export type NamespaceAnalyticsItem = namespaceAnalyticsComponents['schemas']['NamespaceAnalyticsItem']
export type NamespaceAnalyticsSummary = namespaceAnalyticsComponents['schemas']['NamespaceAnalyticsSummary']
export type NamespaceAnalyticsPeriod = namespaceAnalyticsComponents['schemas']['NamespaceAnalyticsPeriod']
export type NamespaceAnalyticsParams = NonNullable<
  namespaceAnalyticsOperations['list_namespace_analytics_route_api_v1_admin_namespace_analytics_get']['parameters']['query']
>

export interface SkillLifecycleVersion {
  id: number
  version: string
  status: string
}

export type ComplianceEvidence = complianceComponents['schemas']['ComplianceEvidenceResponse']
export type ComplianceMapping = complianceComponents['schemas']['ComplianceMappingResponse']
export type ComplianceProjection = complianceComponents['schemas']['ComplianceProjection']
export type ComplianceSnapshot = complianceComponents['schemas']['ComplianceSnapshotResponse']

export interface SkillDetail {
  id: number
  slug: string
  displayName: string
  ownerId?: string
  ownerDisplayName?: string
  summary?: string
  visibility: string
  status: string
  downloadCount: number
  starCount: number
  ratingAvg?: number
  ratingCount: number
  hidden: boolean
  namespace: string
  labels?: LabelItem[]
  canManageLifecycle: boolean
  platformAdminOverride?: boolean
  canSubmitPromotion: boolean
  canInteract: boolean
  canReport: boolean
  headlineVersion?: SkillLifecycleVersion
  publishedVersion?: SkillLifecycleVersion
  ownerPreviewVersion?: SkillLifecycleVersion
  ownerPreviewReviewComment?: string
  resolutionMode?: string
}

export type ResourceDiagnosticStatus =
  | 'HEALTHY'
  | 'MISSING_DB_FILES'
  | 'MISSING_STORAGE_KEYS'
  | 'MISSING_OBJECTS'
  | 'PARTIAL'
  | 'UNVERIFIED'

export interface SkillResourceDiagnostics {
  skillId: number
  namespace: string
  slug: string
  namespaceStatus: string
  latestVersionId?: number
  versionCount: number
  fileCount: number
  versionsWithoutFiles: number[]
  blankStorageKeyCount: number
  checkedObjectCount: number
  checkedFileObjectCount: number
  uncheckedFileObjectCount: number
  missingObjects: Array<{ path: string; storageKey: string }>
  storageProbeError?: { code: string } | null
  diagnosticStatus: ResourceDiagnosticStatus
}

export interface SubmitPromotionRequest {
  sourceSkillId: number
  sourceVersionId: number
  targetNamespaceId: number
}

export type PromotionStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type PromotionSortDirection = 'ASC' | 'DESC'
export type PromotionSortBy = 'reviewedAt'

type GeneratedSkillVersion = components['schemas']['SkillVersionResponse']
type SkillVersionRequired = {
  id: number
  version: string
  status: string
  changelog?: string
  fileCount: number
  totalSize: number
  publishedAt: string
  downloadAvailable: boolean
}
export type SkillVersion = Omit<GeneratedSkillVersion, keyof SkillVersionRequired>
  & SkillVersionRequired
  & ComplianceProjection

type GeneratedSkillVersionDetail = components['schemas']['SkillVersionDetailResponse']
type SkillVersionDetailRequired = {
  id: number
  version: string
  status: string
  changelog?: string
  fileCount: number
  totalSize: number
  publishedAt: string
  parsedMetadataJson?: string
  manifestJson?: string
  sourceProvenance?: SourceProvenance | null
  versionAttribution?: VersionAttribution | null
}
export type SkillVersionDetail = Omit<GeneratedSkillVersionDetail, keyof SkillVersionDetailRequired>
  & SkillVersionDetailRequired
  & ComplianceProjection

export interface SkillFile {
  id: number
  filePath: string
  fileSize: number
  contentType: string
  sha256: string
}

export interface SkillVersionCompareLine {
  type: 'CONTEXT' | 'ADD' | 'DELETE' | string
  content: string
  oldLineNumber: number | null
  newLineNumber: number | null
}

export interface SkillVersionCompareHunk {
  oldStart: number
  oldLines: number
  newStart: number
  newLines: number
  lines: SkillVersionCompareLine[]
}

export interface SkillVersionCompareFile {
  path: string
  changeType: 'ADDED' | 'MODIFIED' | 'REMOVED' | string
  oldSize: number | null
  newSize: number | null
  binary: boolean
  truncated: boolean
  hunks: SkillVersionCompareHunk[]
}

export interface SkillVersionCompareSummary {
  totalFiles: number
  addedFiles: number
  modifiedFiles: number
  removedFiles: number
  addedLines: number
  removedLines: number
}

export interface SkillVersionCompare {
  from: string
  to: string
  summary: SkillVersionCompareSummary
  files: SkillVersionCompareFile[]
}

export interface SkillTag {
  id: number
  tagName: string
  versionId: number
  createdAt: string
}

// Search and pagination
export interface SearchParams {
  q?: string
  namespace?: string
  label?: string
  sort?: string
  page?: number
  size?: number
  starredOnly?: boolean
}

export interface SearchableNamespace {
  slug: string
  displayName: string
  visibleSkillCount: number
}

export interface PagedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
}

// Publish
export interface PublishResult {
  skillId: number
  namespace: string
  slug: string
  version: string
  status: string
  fileCount: number
  totalSize: number
}

export interface SkillDeleteResult {
  skillId?: number
  namespace?: string
  slug?: string
  deleted?: boolean
}

type GeneratedReviewTask = reviewComponents['schemas']['ReviewTaskResponse']

export type ReviewTask = Omit<
  GeneratedReviewTask,
  | 'id'
  | 'skillVersionId'
  | 'namespace'
  | 'skillSlug'
  | 'version'
  | 'status'
  | 'submittedBy'
  | 'submittedAt'
> & {
  id: number
  skillVersionId: number
  namespace: string
  skillSlug: string
  version: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  submittedBy: string
  submittedAt: string
}

export type ReviewBatchDecision = 'APPROVE' | 'REJECT'

export interface ReviewBatchDecisionRequest {
  reviewTaskIds: number[]
  decision: ReviewBatchDecision
  comment?: string
}

export interface ReviewBatchDecisionResultItem {
  reviewTaskId: number
  success: boolean
  status?: 'APPROVED' | 'REJECTED' | null
  errorCode?: string | null
}

export interface ReviewBatchDecisionResponse {
  totalCount: number
  successCount: number
  failureCount: number
  results: ReviewBatchDecisionResultItem[]
}

export interface ReviewSkillDetail {
  skill: SkillDetail
  versions: SkillVersion[]
  files: SkillFile[]
  documentationPath?: string
  documentationContent?: string
  downloadUrl: string
  activeVersion: string
  sourceProvenance?: SourceProvenance | null
}

export interface PromotionTask {
  id: number
  sourceSkillId: number
  sourceSkillDisplayName: string
  sourceSkillSummary?: string | null
  sourceNamespace: string
  sourceSkillSlug: string
  sourceVersion: string
  sourceVersionFileCount: number
  sourceVersionTotalSize: number
  sourceSkillDownloadCount: number
  sourceSkillStarCount: number
  targetNamespace: string
  targetSkillId?: number | null
  status: PromotionStatus
  submittedBy: string
  submittedByName?: string | null
  reviewedBy?: string | null
  reviewedByName?: string | null
  reviewComment?: string | null
  submittedAt: string
  reviewedAt?: string | null
}

export interface SkillReport {
  id: number
  skillId: number
  namespace?: string
  skillSlug?: string
  skillDisplayName?: string
  reporterId: string
  reason: string
  details?: string
  status: 'PENDING' | 'RESOLVED' | 'DISMISSED' | string
  handledBy?: string
  handleComment?: string
  createdAt: string
  handledAt?: string
}

export type ReportDisposition = 'RESOLVE_ONLY' | 'RESOLVE_AND_HIDE' | 'RESOLVE_AND_ARCHIVE'

export interface GovernanceSummary {
  pendingReviews: number
  pendingPromotions: number
  pendingReports: number
  unreadNotifications: number
}

export interface GovernanceInboxItem {
  type: 'REVIEW' | 'PROMOTION' | 'REPORT' | string
  id: number
  title: string
  subtitle?: string
  timestamp?: string
  namespace?: string
  skillSlug?: string
}

export interface GovernanceActivityItem {
  id: number
  action: string
  actorUserId?: string
  actorDisplayName?: string
  targetType?: string
  targetId?: string
  details?: string
  timestamp?: string
}

export interface GovernanceNotification {
  id?: number
  category: string
  entityType: string
  entityId: number
  title: string
  bodyJson?: string
  status: 'UNREAD' | 'READ' | string
  createdAt?: string
  readAt?: string
}

export interface AdminUser {
  userId: string
  username: string
  email?: string
  platformRoles: string[]
  status: string
  createdAt: string
}

export interface AuditLogItem {
  id: string
  userId?: string
  username?: string
  action: string
  details?: string
  requestId?: string
  resourceType?: string
  resourceId?: string
  timestamp: string
  ipAddress?: string
}

// Notification types
export interface NotificationItem {
  id: number
  category: 'PUBLISH' | 'REVIEW' | 'PROMOTION' | 'REPORT'
  eventType: string
  title: string
  bodyJson?: string
  entityType?: string
  entityId?: number
  targetType?: string
  targetId?: number
  targetRoute?: string
  status: 'UNREAD' | 'READ'
  createdAt: string
  readAt?: string
}

export interface NotificationPreferenceItem {
  category: string
  channel: string
  enabled: boolean
}

export interface NotificationUnreadCount {
  count: number
}
