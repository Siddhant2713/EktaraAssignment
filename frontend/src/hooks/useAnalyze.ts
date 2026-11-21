import { useRef, useState } from 'react'
import { streamAnalyze } from '../api/analyze'
import type { AnalyzeResult, ErrorEvent } from '../types'

type Phase = 'idle' | 'analyzing' | 'confirm' | 'error'

type ErrorInfo = Pick<ErrorEvent, 'code' | 'message'>

export function useAnalyze() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState<string[]>([])
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [error, setError] = useState<ErrorInfo | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function analyze(url: string) {
    abortRef.current?.abort() // drop any run still in flight
    const controller = new AbortController()
    abortRef.current = controller

    setPhase('analyzing')
    setProgress([])
    setResult(null)
    setError(null)

    let finished = false
    try {
      await streamAnalyze(
        url,
        (event) => {
          if (event.type === 'progress') {
            setProgress((p) => [...p, event.message])
          } else if (event.type === 'result') {
            finished = true
            setResult(event.data)
            setPhase('confirm')
          } else {
            finished = true
            setError({ code: event.code, message: event.message })
            setPhase('error')
          }
        },
        controller.signal,
      )
      if (!finished) throw new Error('The connection closed before the server finished.')
    } catch (e) {
      if (controller.signal.aborted) return // a newer run replaced this one
      setError({ code: 'INTERNAL_ERROR', message: networkMessage(e) })
      setPhase('error')
    }
  }

  function reset() {
    abortRef.current?.abort()
    setPhase('idle')
    setProgress([])
    setResult(null)
    setError(null)
  }

  return { phase, progress, result, error, analyze, reset }
}

function networkMessage(e: unknown): string {
  if (e instanceof TypeError) return 'Could not reach the backend. Is it running on port 8000?'
  return e instanceof Error ? e.message : 'Something went wrong.'
}
