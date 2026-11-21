import { External } from './icons'

type Props = {
  quote: string
  sourceUrl: string
  sourceLabel: string
}

/** A verbatim passage plus a link to where it came from. Used for founders and for facts. */
export function EvidenceQuote({ quote, sourceUrl, sourceLabel }: Props) {
  return (
    <figure className="quote-wrap">
      <blockquote className="quote">“{quote}”</blockquote>
      <a className="quote-source" href={sourceUrl} target="_blank" rel="noreferrer">
        {sourceLabel}
        <External width={12} height={12} />
      </a>
    </figure>
  )
}
