/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { PORTAL_ROOT_ID } from '@/shared/lib/portal-container'
import { Dialog, DialogContent, DialogTitle } from './dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem } from './dropdown-menu'
import { Select, SelectContent, SelectItem } from './select'

function NavigatingDialog() {
  const [route, setRoute] = useState<'dialog' | 'next'>('dialog')

  if (route === 'next') {
    return <p>Next route</p>
  }

  return (
    <Dialog open>
      <DialogContent>
        <DialogTitle>Confirm navigation</DialogTitle>
        <button type="button" onClick={() => setRoute('next')}>Continue</button>
      </DialogContent>
    </Dialog>
  )
}

describe('overlay portal isolation', () => {
  let portalRoot: HTMLDivElement

  beforeEach(() => {
    portalRoot = document.createElement('div')
    portalRoot.id = PORTAL_ROOT_ID
    document.body.appendChild(portalRoot)
  })

  afterEach(() => {
    cleanup()
    portalRoot.remove()
  })

  it('mounts and unmounts dialog content inside the dedicated portal root', () => {
    const result = render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Confirm action</DialogTitle>
        </DialogContent>
      </Dialog>,
    )

    expect(portalRoot.querySelector('[role="dialog"]')).toBeTruthy()
    result.unmount()
    expect(portalRoot.childElementCount).toBe(0)
  })

  it('mounts Radix select and dropdown content inside the dedicated portal root', () => {
    render(
      <>
        <Select open value="one">
          <SelectContent>
            <SelectItem value="one">One</SelectItem>
          </SelectContent>
        </Select>
        <DropdownMenu open>
          <DropdownMenuContent>
            <DropdownMenuItem>Profile</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </>,
    )

    expect(portalRoot.textContent).toContain('One')
    expect(portalRoot.textContent).toContain('Profile')
  })

  it('tears down an open dialog when route navigation removes its owner', () => {
    render(<NavigatingDialog />)

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByText('Next route')).toBeTruthy()
    expect(portalRoot.childElementCount).toBe(0)
  })
})
