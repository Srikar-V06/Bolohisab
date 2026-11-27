import { useEffect, useId, useRef, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Sheet } from './components'

const desktopQuery = '(min-width: 64rem)'

function watchDesktop(callback: () => void) {
  const media = window.matchMedia?.(desktopQuery)
  media?.addEventListener('change', callback)
  return () => media?.removeEventListener('change', callback)
}

function isDesktop() {
  return window.matchMedia?.(desktopQuery).matches ?? false
}

export default function ResponsiveDetail({ title, children, close, locked }: {
  title: string; children: ReactNode; close: () => void; locked?: boolean
}) {
  const { t } = useTranslation()
  const desktop = useSyncExternalStore(watchDesktop, isDesktop)
  const heading = useRef<HTMLHeadingElement>(null)
  const id = useId()
  useEffect(() => {
    if (desktop) heading.current?.focus()
  }, [desktop])

  if (!desktop) return <Sheet title={title} close={close} locked={locked}>{children}</Sheet>

  return (
    <section className="inline-detail card" aria-labelledby={id} onKeyDown={(event) => {
      if (event.key === 'Escape' && !locked) {
        event.preventDefault()
        close()
      }
    }}>
      <header className="sheet-header">
        <h2 ref={heading} tabIndex={-1} id={id}>{title}</h2>
        <button type="button" className="icon-button" aria-label={t('common.close')} onClick={close} disabled={locked}>
          <X size={22} aria-hidden="true" />
        </button>
      </header>
      <div className="sheet-content">{children}</div>
    </section>
  )
}
