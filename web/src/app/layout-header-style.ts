import { cn } from '@/shared/lib/utils'

export const APP_HEADER_BASE_CLASS_NAME =
  'sticky top-0 z-50 flex items-center justify-between border-b border-border/70 bg-background/90 px-4 py-4 backdrop-blur-xl transition-[background-color,border-color,box-shadow] duration-200 supports-[backdrop-filter]:bg-background/80 sm:px-6 md:px-12'

export const APP_HEADER_ELEVATED_CLASS_NAME =
  'shadow-[0_12px_30px_-24px_hsl(var(--foreground)/0.45)]'

export function getAppHeaderClassName(isElevated: boolean): string {
  return cn(APP_HEADER_BASE_CLASS_NAME, isElevated && APP_HEADER_ELEVATED_CLASS_NAME)
}
