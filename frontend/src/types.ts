// Mirrors backend/app/schemas/*

export type Company = {
  name: string
  one_liner: string
}

export type Founder = {
  name: string
  role: string | null
  confidence: number
  source_url: string
  evidence: string
}

export type AnalyzeResult = {
  company: Company
  founders: Founder[]
  pages_scraped: string[]
}

// What the user confirms: names may have been edited or added by hand
export type Person = {
  name: string
  role: string
}

export type ErrorCode =
  | 'CONFIG_MISSING'
  | 'INVALID_URL'
  | 'SITE_UNREACHABLE'
  | 'SITE_BLOCKED'
  | 'NO_CONTENT'
  | 'LLM_FAILED'
  | 'INTERNAL_ERROR'

export type ProgressEvent = { type: 'progress'; step: string; message: string }
export type ResultEvent<T> = { type: 'result'; data: T }
export type ErrorEvent = { type: 'error'; step: string; code: ErrorCode; message: string }

export type StreamEvent<T> = ProgressEvent | ResultEvent<T> | ErrorEvent
