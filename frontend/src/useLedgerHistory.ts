import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { HistoryEntry } from './api'

export function useLedgerHistory(customerId: number) {
  const [entries, setEntries] = useState<HistoryEntry[]>()
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [error, setError] = useState<unknown>()
  const [loading, setLoading] = useState(true)
  const active = useRef<AbortController>(null)

  const load = useCallback(async (cursor: string | null) => {
    if (active.current) return
    const request = new AbortController()
    active.current = request
    setError(undefined)
    setLoading(true)
    try {
      const page = await api.ledger(customerId, cursor, request.signal)
      if (request.signal.aborted) return
      setEntries((previous) => {
        const merged = cursor && previous ? previous.slice() : []
        const ids = new Set(merged.map(({ id }) => id))
        for (const entry of page.items) {
          if (!ids.has(entry.id)) {
            ids.add(entry.id)
            merged.push(entry)
          }
        }
        return merged
      })
      setNextCursor(page.has_more ? page.next_cursor : null)
    } catch (cause) {
      if (!request.signal.aborted) setError(cause)
    } finally {
      if (active.current === request) {
        active.current = null
        setLoading(false)
      }
    }
  }, [customerId])

  useEffect(() => {
    void load(null)
    return () => {
      active.current?.abort()
      active.current = null
    }
  }, [load])

  return { entries, error, loading, nextCursor, loadNext: () => void load(nextCursor) }
}
