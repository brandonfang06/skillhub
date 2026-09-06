import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/shared/hooks/use-theme'
import { cn } from '@/shared/lib/utils'

interface ThemeToggleProps {
  className?: string
}

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { t } = useTranslation()
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const label = isDark ? t('theme.switchToLight') : t('theme.switchToDark')

  return (
    <button
      type="button"
      role="switch"
      aria-label={t('theme.darkMode')}
      aria-checked={isDark}
      title={label}
      onClick={toggleTheme}
      className={cn(
        'group relative inline-flex h-11 w-16 shrink-0 items-center rounded-full border border-border bg-muted/70 px-1 text-muted-foreground shadow-sm transition-[background-color,border-color] duration-200 hover:border-primary/40 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'absolute left-1 top-1.5 h-8 w-7 rounded-full border border-border/80 bg-card shadow-[0_3px_10px_-4px_hsl(var(--foreground)/0.45)] transition-transform duration-200 ease-out motion-reduce:transition-none',
          isDark && 'translate-x-7',
        )}
      />
      <span className="relative z-10 inline-flex h-8 w-7 items-center justify-center">
        <Sun aria-hidden="true" className={cn('h-4 w-4 transition-colors duration-200', !isDark && 'text-foreground')} />
      </span>
      <span className="relative z-10 inline-flex h-8 w-7 items-center justify-center">
        <Moon aria-hidden="true" className={cn('h-4 w-4 transition-colors duration-200', isDark && 'text-foreground')} />
      </span>
    </button>
  )
}
