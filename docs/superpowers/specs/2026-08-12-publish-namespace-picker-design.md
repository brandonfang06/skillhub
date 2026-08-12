# Publish Namespace Picker Design

Date: 2026-08-12

## Problem

The publish page renders every namespace in a plain Radix Select. Users who can
publish into more than 100 namespaces cannot efficiently find a target because
the field has no filter and the long option list does not provide a reliable,
obvious scrolling experience.

## Goals

- Let users search publishable namespaces by display name or slug.
- Match case-insensitively after trimming the search text.
- Keep the result list bounded to approximately 320 pixels and scrollable with
  mouse wheel, keyboard, and touch.
- Preserve route-prefilled namespace values and the existing ability to clear
  the selection.
- Preserve the existing publish payload, visibility behavior, and namespace
  authorization/data source.
- Work at desktop and mobile viewport widths without horizontal overflow.

## Non-Goals

- No backend API, pagination, permission, sorting, or database changes.
- No changes to the shared Select primitive or unrelated dropdowns.
- No virtualization; the current expected scale of hundreds of rows is small
  enough for client-side filtering.

## Design

Create a publish-specific `NamespacePicker` under `web/src/features/publish/`.
It receives the `ManagedNamespace[]`, selected slug, and change callback. The
publish page continues to own `namespaceSlug` and passes it unchanged to the
existing publish mutation.

The picker uses the existing Radix dropdown-menu wrapper so it inherits portal,
focus, escape, and outside-click behavior without adding a dependency. Its
trigger uses the shared Select trigger styling and displays either the selected
`Display Name (@slug)` label or the existing namespace placeholder.

The opened panel contains:

1. A focused search input with a localized accessible label and placeholder.
2. A clear-selection item that preserves the existing clearable behavior.
3. A result region capped at `20rem` with vertical scrolling and overscroll
   containment.
4. Namespace items in the server-provided order, each showing display name and
   slug, with a check marker on the selected item.
5. A localized empty-result message when no namespace matches.

Search compares a normalized query against normalized display name and slug.
Search state is cleared when the panel closes. Selecting or clearing invokes the
callback once and closes the panel.

## Keyboard And Accessibility

- The trigger remains a real button with the namespace field label associated
  through `aria-labelledby`.
- Opening moves focus to the search input.
- Typing stays in the input instead of triggering Radix menu typeahead.
- Arrow Down or Arrow Up from the input moves to the first or last visible
  result; Radix handles navigation between menu items.
- Enter selects a focused item; Escape closes and returns focus to the trigger.
- Empty results are exposed as a status message.

## Testing

- Unit-test normalization and filtering against more than 100 namespaces.
- Component-test search by display name and slug, case-insensitive matching,
  empty results, selection, clearing, and keyboard entry into results.
- Keep publish page tests for route prefill and visibility unchanged except for
  replacing the mocked namespace control.
- Run full frontend Vitest, TypeScript, ESLint, and production build gates.
- Verify the authenticated publish page in desktop and mobile viewports with a
  100-plus namespace response, including scrolling, filtering, selection,
  clearing, and no horizontal overflow.

## Side-Effect Boundaries

The change is isolated to the publish feature and translation resources. It does
not modify namespace fetching, permissions, publish requests, route state,
visibility choices, or shared Select behavior. A selected namespace that is no
longer present still displays its slug so a route-prefilled value is not silently
discarded while data loads or changes.
