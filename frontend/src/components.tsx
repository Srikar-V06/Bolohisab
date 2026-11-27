import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { LoaderCircle, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ApiError } from './api'

export function Sheet({ title, children, close, locked }: {
  title: string; children: ReactNode; close: () => void; locked?: boolean
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const { t } = useTranslation()
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => { element?.close() }
  }, [])

  return (
    <dialog ref={dialog} className="sheet" aria-label={title}
      onCancel={(event) => { event.preventDefault(); if (!locked) close() }}
      onClick={(event) => { if (event.target === event.currentTarget && !locked) close() }}>
      <div className="sheet-body">
        <header className="sheet-header">
          <h2>{title}</h2>
          <button type="button" className="icon-button" aria-label={t('common.close')} onClick={close} disabled={locked}>
            <X size={22} aria-hidden="true" />
          </button>
        </header>
        <div className="sheet-content">{children}</div>
      </div>
    </dialog>
  )
}

export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<unknown>()
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(undefined)
    load(controller.signal).then(setData, (cause: unknown) => {
      if (!controller.signal.aborted) setError(cause)
    })
    return () => controller.abort()
  }, [load, revision])
  return { data, error, setData, retry: () => setRevision((value) => value + 1) }
}

export function Loading({ text }: { text: string }) {
  return <p className="notice" role="status"><LoaderCircle size={18} className="spinner" aria-hidden="true" /> {text}</p>
}

export function LoadError({ error, retry }: { error: unknown; retry: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="notice notice-error" role="alert">
      <p>{t(error instanceof ApiError && error.code === 'PRECISION' ? 'common.precision' : 'common.loadFailed')}</p>
      <button className="button button-secondary" type="button" onClick={retry}>{t('common.retry')}</button>
    </div>
  )
}
