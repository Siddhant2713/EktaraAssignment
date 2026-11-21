// Mirrors backend/app/schemas/*

export type Company = {
  name: string
  one_liner: string
}

export type Founder = {
  name: string
  role: string | null
  confidence: number
  source: 'site' | 'web' // the company's own pages, or a web search result
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
  | 'SEARCH_FAILED'
  | 'TIMEOUT'
  | 'INTERNAL_ERROR'

export type ProgressEvent = { type: 'progress'; step: string; message: string }
export type ResultEvent<T> = { type: 'result'; data: T }
export type ErrorEvent = { type: 'error'; step: string; code: ErrorCode; message: string }

export type StreamEvent<T> = ProgressEvent | ResultEvent<T> | ErrorEvent

// ---- draft step (mirrors backend/app/schemas/draft.py) ----

export type Tone = 'casual' | 'formal' | 'short'

export type FactKind = 'own_words' | 'decision' | 'launch' | 'career' | 'milestone' | 'other'

export type Fact = {
  id: number
  person: string
  text: string
  quote: string
  source_url: string
  source_title: string
  kind: FactKind
  specificity: number
  date: string | null
}

export type Opener = {
  to: string
  text: string
  fact_ids: number[]
  angle: string
}

export type DraftResult = {
  openers: Opener[]
  facts: Fact[]
  used_fallback: boolean
}

export type DraftRequestBody = {
  url: string
  company: Company
  founders: Person[]
  pitch: string
  tone: Tone
  facts?: Fact[] // sent back on regenerate so the server skips the research
}
