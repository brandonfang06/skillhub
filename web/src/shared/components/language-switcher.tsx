import { useTranslation } from 'react-i18next'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { ChevronDown, Globe } from 'lucide-react'

interface LanguageSwitcherProps {
  className?: string
}

export const languages = [
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'zh', name: '简体中文' },
  { code: 'en', name: 'English' },
] as const

export type SupportedLanguageCode = (typeof languages)[number]['code']

export function resolveSupportedLanguageCode(language?: string): SupportedLanguageCode {
  if (language === 'zh-TW' || language?.startsWith('zh-Hant') || language === 'zh-HK' || language === 'zh-MO') {
    return 'zh-TW'
  }
  if (language?.startsWith('zh')) {
    return 'zh'
  }
  if (language?.startsWith('en')) {
    return 'en'
  }
  return 'zh-TW'
}

export function LanguageSwitcher({ className }: LanguageSwitcherProps) {
  const { i18n } = useTranslation()

  const currentLangCode = resolveSupportedLanguageCode(i18n.language)
  const currentLanguage = languages.find((lang) => lang.code === currentLangCode) || languages[0]

  const changeLanguage = (langCode: string) => {
    i18n.changeLanguage(langCode)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn('cursor-pointer gap-2 text-muted-foreground hover:text-foreground', className)}
        >
          <Globe className="h-4 w-4" />
          <span className="text-sm text-inherit">{currentLanguage.name}</span>
          <ChevronDown className="h-3.5 w-3.5 opacity-70" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="flex min-w-[9rem] flex-col gap-1.5 p-2">
        {languages.map((lang) => (
          <DropdownMenuItem
            key={lang.code}
            onClick={() => changeLanguage(lang.code)}
            className={cn(
              'cursor-pointer rounded-md px-3 py-2',
              currentLangCode === lang.code ? 'bg-accent' : ''
            )}
          >
            {lang.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
