import type { AnalyzeResult, StreamEvent } from '../types'
import { postStream } from './stream'

export function streamAnalyze(
  url: string,
  onEvent: (event: StreamEvent<AnalyzeResult>) => void,
  signal?: AbortSignal,
) {
  return postStream<AnalyzeResult>('/api/analyze', { url }, onEvent, signal)
}
