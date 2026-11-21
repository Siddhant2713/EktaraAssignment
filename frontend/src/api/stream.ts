import type { StreamEvent } from '../types'

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/**
 * POST a JSON body and read the server's event stream.
 * EventSource can't send a POST body, so we read the response with fetch + a stream reader.
 * Calls onEvent for every `data: {...}` message the server sends.
 */
export async function postStream<T>(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent<T>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(res.status === 422 ? 'That does not look like a valid URL.' : `Server returned HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // messages are separated by a blank line; the last piece may be incomplete, so keep it
    const messages = buffer.split('\n\n')
    buffer = messages.pop() ?? ''
    for (const message of messages) {
      const line = message.split('\n').find((l) => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice('data: '.length)) as StreamEvent<T>)
    }
  }
}
