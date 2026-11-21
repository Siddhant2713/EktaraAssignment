import { useRef, useState } from 'react'
import type { ErrorEvent, StreamEvent } from '../types'

export type Phase = 'idle' | 'running' | 'done' | 'error'
export type ErrorInfo = Pick<ErrorEvent, 'code' | 'message'>

type Starter<TArgs, TResult> = (
  args: TArgs,
  onEvent: (event: StreamEvent<TResult>) => void,
  signal: AbortSignal,
) => Promise<void>

/**
 * Runs one streaming backend call and tracks it: progress lines while it runs, then a result or an error.
 * Shared by the analyze and draft steps.
 */
export function useStreamTask<TArgs, TResult>(start: Starter<TArgs, TResult>) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState<string[]>([])
  const [result, setResult] = useState<TResult | null>(null)
  const [error, setError] = useState<ErrorInfo | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function run(args: TArgs) {
    abortRef.current?.abort() // drop any run still in flight
    const controller = new AbortController()
    abortRef.current = controller

    setPhase('running')
    setProgress([])
    setResult(null)
    setError(null)

    let finished = false
    try {
      await start(
        args,
        (event) => {
          if (event.type === 'progress') {
            setProgress((p) => [...p, event.message])
          } else if (event.type === 'result') {
            finished = true
            setResult(event.data)
            setPhase('done')
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

  return { phase, progress, result, error, run, reset }
}

function networkMessage(e: unknown): string {
  if (e instanceof TypeError) return 'Could not reach the backend. Is it running on port 8000?'
  return e instanceof Error ? e.message : 'Something went wrong.'
}
