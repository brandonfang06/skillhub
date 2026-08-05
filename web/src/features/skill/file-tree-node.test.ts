/** @vitest-environment jsdom */
import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as mod from './file-tree-node'
import type { FileTreeNode } from './file-tree-builder'

afterEach(() => {
  cleanup()
})

/**
 * file-tree-node.tsx exports the FileTreeNodeComponent React component.
 * It contains two module-private helpers (formatFileSize and getIconComponent)
 * that are pure functions but cannot be imported for direct testing.
 *
 * We verify the module shape so downstream consumers break fast
 * if the export contract changes.
 *
 * Note: FileTreeNodeComponent is wrapped with React.memo, so typeof returns 'object'
 * instead of 'function'. We check for both to handle the memo wrapper.
 */
describe('file-tree-node module exports', () => {
  it('exports the FileTreeNodeComponent component', () => {
    expect(mod.FileTreeNodeComponent).toBeDefined()
    // React.memo wraps the component in an object, so typeof is 'object'
    expect(['function', 'object']).toContain(typeof mod.FileTreeNodeComponent)
  })

  it('renders a file as a keyboard-accessible button', () => {
    const onFileClick = vi.fn()
    const node: FileTreeNode = {
      id: 'SKILL.md',
      name: 'SKILL.md',
      path: 'SKILL.md',
      type: 'file',
      depth: 0,
      file: {
        id: 1,
        filePath: 'SKILL.md',
        fileSize: 96,
        contentType: 'text/markdown',
        sha256: 'hash',
      },
    }

    render(createElement(mod.FileTreeNodeComponent, { node, onFileClick }))

    const fileButton = screen.getByRole('button', { name: /SKILL\.md/ })
    fireEvent.click(fileButton)
    expect(onFileClick).toHaveBeenCalledWith(node)
  })
})
