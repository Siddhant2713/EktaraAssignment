import type { FormEvent } from 'react'
import { ArrowRight } from '../components/icons'

type Props = {
  url: string
  onUrlChange: (url: string) => void
  onSubmit: () => void
}

const EXAMPLES = ['linear.app', 'posthog.com', 'cal.com']

const HOW = [
  { title: 'Read the site', body: 'We read the company’s pages, and the open web if needed, to find out who runs it.' },
  {
    title: 'Research the founders',
    body: 'We collect things they have actually said or done, each with the exact quote and a link.',
  },
  {
    title: 'Write the opener',
    body: 'Tell us what you offer, pick a tone, and get a first line built on those verified facts.',
  },
]

export function Landing({ url, onUrlChange, onSubmit }: Props) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit()
  }

  return (
    <div className="landing">
      <p className="eyebrow">Cold outreach, minus the cold</p>
      <h1 className="hero-title">
        One string.
        <br />
        <em>One first line</em> worth replying to.
      </h1>

      <svg className="hero-string" viewBox="0 0 600 24" preserveAspectRatio="none" aria-hidden>
        <path d="M0 12 H600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <animate
            attributeName="d"
            dur="5s"
            repeatCount="indefinite"
            values="M0 12 Q300 12 600 12; M0 12 Q300 2 600 12; M0 12 Q300 20 600 12; M0 12 Q300 9 600 12; M0 12 Q300 14 600 12; M0 12 Q300 12 600 12; M0 12 Q300 12 600 12"
            keyTimes="0;0.06;0.12;0.2;0.3;0.45;1"
            calcMode="spline"
            keySplines=".4 0 .6 1;.4 0 .6 1;.4 0 .6 1;.4 0 .6 1;.4 0 .6 1;.4 0 .6 1"
          />
        </path>
      </svg>

      <p className="hero-sub">
        Paste a company’s website. Ektara finds the founders, digs up what they have really said in public, and drafts
        openers that point to it.
      </p>

      <form className="url-form" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="site-url">
          Company website
        </label>
        <input
          id="site-url"
          className="input url-input"
          type="url"
          inputMode="url"
          placeholder="https://company.com"
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
          required
          autoFocus
        />
        <button type="submit" className="btn btn-primary btn-lg">
          Find founders <ArrowRight />
        </button>
      </form>

      <p className="examples">
        Try
        {EXAMPLES.map((host) => (
          <button key={host} type="button" className="chip example" onClick={() => onUrlChange(`https://${host}`)}>
            {host}
          </button>
        ))}
      </p>

      <ol className="how">
        {HOW.map((item, i) => (
          <li key={item.title}>
            <span className="how-num">0{i + 1}</span>
            <h2>{item.title}</h2>
            <p>{item.body}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
