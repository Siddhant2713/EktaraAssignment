import type { Fact, FactKind } from '../types'

const KIND_LABEL: Record<FactKind, string> = {
  own_words: 'In their words',
  decision: 'Decision',
  launch: 'Launch',
  career: 'Career',
  milestone: 'Milestone',
  other: 'Detail',
}

function Specificity({ value }: { value: number }) {
  return (
    <span className="specificity" title={`Specificity ${value} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <i key={n} className={n <= value ? 'on' : ''} />
      ))}
    </span>
  )
}

/** The kind chip and specificity dots shown above a fact. `showPerson` adds the founder's name (for the full list). */
export function FactMeta({ fact, showPerson = false }: { fact: Fact; showPerson?: boolean }) {
  return (
    <div className="fact-meta">
      {showPerson && <strong>{fact.person}</strong>}
      <span className="chip">{KIND_LABEL[fact.kind]}</span>
      <Specificity value={fact.specificity} />
    </div>
  )
}
