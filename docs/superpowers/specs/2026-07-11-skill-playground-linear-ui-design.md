# Skill Playground Linear-Adapted UI Design

## Status

Approved on 2026-07-11.

## Context

Skill Playground is a SkillHub React route backed by a separately deployed
runtime. SkillHub owns the product shell, route, authenticated capability, and
read-only context access. The sidecar owns ephemeral sessions, prompt assembly,
provider routing, and SSE responses. The sidecar has no frontend.

The current Playground is functionally complete but visually flat. Its context
browser, content preview, transcript, and composer use nearly identical light
surfaces and borders. On mobile, the context area appears before the chat and
pushes the primary trial interaction below the fold.

## Decision

Use a Linear-adapted product workspace inside the existing SkillHub shell.

Adopt Linear's compact controls, ordered surface hierarchy, hairline borders,
and restrained interaction treatment. Do not copy Linear's marketing site
wholesale: SkillHub keeps its current light product shell, existing fonts, zero
letter spacing, semantic colors, indigo accent, and brand identity.

Source reference:

- <https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/linear.app>

Rejected alternatives:

- Vercel-neutral is credible but would make the Playground look like a generic
  developer console and would suppress SkillHub's existing identity.
- Warp-terminal has a strong workbench character but implies shell or tool
  execution that the prompt-only V1 does not support.

## Goals

- Make the Playground feel like a focused product workspace within SkillHub.
- Preserve a clear visual connection to the skill detail page.
- Make chat the dominant interaction on every viewport.
- Give context, transcript, and composer distinct but quiet hierarchy.
- Keep read-only and prompt-only limits visible without dominating the page.
- Keep all backend, sidecar, token, and SSE contracts unchanged.

## Non-Goals

- No redesign of the SkillHub header, navigation, footer, or skill detail page.
- No dark mode conversion for the rest of SkillHub.
- No sidecar, Python backend, schema, API, capability, or SSE changes.
- No terminal, IDE, tool execution, file editing, or upload affordances.
- No model selector, durable transcript, or new session behavior.
- No resizable panes in this milestone.
- No proprietary Linear fonts or copied Linear assets.

## Product Relationship

The outer page remains unmistakably SkillHub:

- Keep the current SkillHub header and light page background.
- Keep the existing route and back link to the skill detail page.
- Keep SkillHub typography outside the workspace.
- Keep the footer naturally below the workspace; the first viewport should be
  occupied by the trial experience, not footer content.

The dark workspace is an in-product mode change, not a second brand or a
sidecar-owned website.

## Visual System

### Surfaces

Use a small, ordered dark surface ladder inside the Playground only:

| Role | Value | Use |
| --- | --- | --- |
| Workspace canvas | `#09090B` | Outer Playground work area |
| Surface 1 | `#0F1012` | Context and chat panels |
| Surface 2 | `#17181D` | Selected rows, composer, lifted controls |
| Hairline | `#25272D` | Panel and row separation |
| Hairline strong | `#343740` | Focused and hovered boundaries |
| Primary text | `#F7F8F8` | Headings and primary content |
| Secondary text | `#A4A9B3` | Metadata and explanatory text |
| Muted text | `#858B96` | Disabled and low-priority labels |

Use existing SkillHub semantic tokens for errors, warnings, and success. Do not
replace semantic state with lavender.

### Brand Accent

Keep SkillHub's current indigo primary as the single workspace accent. Reserve
it for:

- send action
- user message surface
- keyboard focus ring
- active context indicator
- install call to action

Do not use purple gradients, glow effects, or lavender panel backgrounds inside
the workspace.

### Typography

- Keep Inter for workspace UI, transcript, and controls.
- Keep JetBrains Mono for file paths and raw context content only.
- Use 14px as the default workspace body size and 12px for metadata.
- Use 500 or 600 weight for compact headings and control labels.
- Keep letter spacing at `0`.
- Do not use hero or marketing-scale type inside the workspace.

### Shape And Depth

- Use a 4px spacing base.
- Use 6px radius for compact controls and 8px for the workspace frame and
  composer.
- Use flat surfaces and hairline borders for hierarchy.
- Avoid nested cards, floating panels, heavy shadows, glass effects, and
  decorative gradients.

## Layout

### Desktop

At widths above 1024px:

- Keep a compact page title row above the workspace.
- Give the context area 300-320px and chat the remaining width.
- Chat should occupy at least 65% of the usable workspace width.
- Keep the workspace tall enough to fill the first viewport below the SkillHub
  header and page title.
- Size the workspace from `100dvh` with bounded minimum and maximum heights;
  do not rely on the current fixed 560px minimum as the mobile viewport model.
- Keep context and chat as flat sibling panels inside one workspace frame.
- Keep the composer anchored to the bottom of the chat panel while the
  transcript scrolls independently.

### Tablet

At 768-1024px:

- At 900-1024px, keep a 260px context panel and preserve chat as the larger
  panel.
- At 768-899px, default context to closed and open it with the same right-side
  drawer used on mobile.

### Mobile

Below 768px, chat is the first and default surface:

- Do not render the full context panel before the transcript.
- Open context from an icon button in the workspace title bar.
- Render context in an accessible full-height right-side drawer over the
  current chat.
- Keep file selection and content preview inside that drawer.
- Keep the composer visible at the bottom of the viewport when the on-screen
  keyboard permits.
- Include the bottom safe-area inset in composer spacing and avoid fixed
  viewport units that ignore mobile browser chrome.
- Truncate long skill coordinates and filenames without horizontal overflow.
- Keep touch targets at least 44px.

## Workspace Components

### Title Bar

The title bar contains:

- back to skill action
- skill display name
- namespace, slug, and version metadata
- compact read-only and prompt-only status
- mobile context toggle

Status should use quiet neutral treatment. It must explain the boundary without
looking like an error or promotional badge.

### Context Browser

- Use a compact file list with a clear selected state.
- Keep filenames single-line with truncation and a full-path tooltip.
- Use monospace only for paths and file content.
- Separate the file list and content preview with a hairline boundary.
- Keep context read-only; do not render edit, upload, run, or save controls.
- Preserve the existing allowlisted context returned by the sidecar session.

### Transcript

- Use an indigo surface for user messages.
- Render assistant responses on the neutral canvas with a subtle left hairline
  or low-contrast surface, not a second colored bubble.
- Keep message width constrained for readable line length.
- Preserve plain text wrapping and streaming cursor behavior.
- Keep speaker labels visually subordinate to message content.

### Composer

- Use one neutral lifted surface with a strong focus ring.
- Keep send as the only primary icon action.
- Keep reset in the chat header with an icon and tooltip.
- Disable input and send while connecting, generating, unavailable, or expired.
- Preserve Enter to send and Shift+Enter for a newline.

### Install Action

After the first completed assistant response, show a compact install call to
action. It should reuse SkillHub's existing install command behavior and must
not install automatically. The user still chooses whether to copy or run the
command. Completion is derived from the existing local transcript; this action
must not add an API call, sidecar event, durable state, or lifecycle mutation.

## Implementation Isolation

- Keep workspace colors and layout classes inside Playground page and feature
  components. Do not change global theme tokens or shared shell appearance.
- Implement the responsive context drawer directly in the Playground feature
  with `@radix-ui/react-dialog`; do not expand the current shared dialog API or
  hand-roll focus trapping.
- Keep `usePlayground` network/session behavior, generated API types, backend
  routes, and sidecar code unchanged. A local `completed` message marker may be
  derived from the existing `message.completed` event so the install action
  never treats provider errors as successful responses.
- Reuse the existing install command builders rather than duplicating registry
  URL or namespace rules.

## States And Errors

- `connecting`: show a quiet inline progress state in the transcript area.
- empty ready state: explain that the user can enter a prompt to try the skill.
- streaming: keep the composer disabled and show the existing streaming cursor.
- recoverable provider or message errors: show an inline error above the
  composer and keep the session usable.
- expired session: replace the transcript body with the current expiry message
  and a `Reload playground` action that reloads the current route and reuses the
  existing session creation flow.
- unavailable sidecar: keep the failure inside the workspace; SkillHub header,
  navigation, skill detail, and install behavior remain usable.

Do not add new error codes or change error classification in this visual
milestone.

## Data Flow And Ownership

The existing flow remains unchanged:

1. SkillHub Web requests a short-lived capability from the Python backend.
2. SkillHub Web creates an ephemeral sidecar session.
3. The sidecar loads allowlisted read-only skill context.
4. SkillHub Web opens the SSE stream.
5. The user sends prompts and the sidecar streams assistant events.
6. SkillHub Web renders local session state and deletes the session on cleanup.

The redesign may reorganize frontend presentation components, but
`usePlayground`, sidecar client functions, event names, capability claims, and
backend routes are not contract-change surfaces for this work.

## Accessibility

- Preserve semantic headings, navigation, form labels, and live transcript
  announcements.
- Give icon-only actions accessible names and tooltips.
- Maintain visible keyboard focus on every interactive control.
- Meet WCAG AA contrast for text, focus, error, disabled, and selected states.
- Keep drawer focus trapped while open and return focus to its trigger on close.
- Respect reduced-motion preferences; no essential state depends on animation.

## Verification

Required automated coverage:

- Playground page renders the dark workspace without changing the global shell.
- Context selection and mobile context drawer behavior.
- Empty, connecting, ready, streaming, recoverable error, unavailable, and
  expired states.
- Composer keyboard behavior and disabled state while generation is active.
- Install call to action appears only after a completed response.
- Existing `usePlayground` event and session tests continue to pass unchanged.

Required visual/browser verification:

- 1440x900 desktop: context 300-320px, chat at least 65%, composer anchored.
- 1024x768 tablet: readable 260px context split without overlap.
- 800x900 compact tablet: chat-first layout with context in the right-side
  drawer.
- 390x844 mobile: chat appears before context, no horizontal overflow, drawer
  is keyboard accessible, and title text does not overlap actions.
- Test empty, populated, streaming, provider-error, unavailable, and expired
  screenshots.
- Confirm the SkillHub detail page and all non-Playground routes are visually
  unchanged.

Required repository commands:

```powershell
cd web
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run build
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-playground-isolation.ps1
git diff --check
```

## Success Criteria

- The first viewport reads as a focused SkillHub trial workspace.
- Chat is visually and spatially primary on desktop, tablet, and mobile.
- Context remains discoverable, readable, and explicitly read-only.
- The design does not imply terminal, IDE, tool, or file-editing capability.
- The sidecar and Python backend contracts remain unchanged.
- Removing or disabling Playground still requires no SkillHub schema or runtime
  rollback.
