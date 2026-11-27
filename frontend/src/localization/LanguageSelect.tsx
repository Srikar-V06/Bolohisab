import { useId } from 'react'
import { ChevronDown, Languages } from 'lucide-react'
import { languageNames } from './languages'
import type { Locale } from './languages'

type Props = {
  label: string
  locales: readonly Locale[]
  value: Locale
  onChange: (locale: Locale) => void
  compact?: boolean
  disabled?: boolean
}

export default function LanguageSelect({ label, locales, value, onChange, compact, disabled }: Props) {
  const id = useId()

  return (
    <div className={compact ? 'min-w-0' : 'grid max-w-xs gap-1.5'}>
      <label htmlFor={id} className={compact ? 'sr-only' : 'text-sm font-extrabold'}>{label}</label>
      <div className="relative">
        <Languages size={17} aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-primary" />
        <select
          id={id}
          className="language-select"
          value={value}
          lang={value}
          disabled={disabled}
          onChange={(event) => {
            const selected = locales.find((locale) => locale === event.target.value)
            if (selected) onChange(selected)
          }}
        >
          {locales.map((locale) => (
            <option key={locale} value={locale} lang={locale}>
              {languageNames[locale][compact ? 'interface' : 'speech']}
            </option>
          ))}
        </select>
        <ChevronDown size={15} aria-hidden="true" className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted" />
      </div>
    </div>
  )
}
