import type { DraftRequestBody, DraftResult, StreamEvent } from '../types'
import { postStream } from './stream'

export function streamDraft(
  body: DraftRequestBody,
  onEvent: (event: StreamEvent<DraftResult>) => void,
  signal?: AbortSignal,
) {
  return postStream<DraftResult>('/api/draft', body, onEvent, signal)
}
