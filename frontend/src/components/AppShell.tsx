import type { ReactNode } from 'react'
import { Logo } from './Logo'
import { Stepper } from './Stepper'

type Props = {
  step: 0 | 1 | 2 | null // which step is current; null on the landing page
  onHome: () => void
  children: ReactNode
}

export function AppShell({ step, onHome, children }: Props) {
  return (
    <div className="shell">
      <header className="topbar">
        <button type="button" className="brand" onClick={onHome} aria-label="Ektara, start over">
          <Logo />
          <span>Ektara</span>
        </button>
        {step !== null && <Stepper current={step} />}
      </header>

      <main className="stage">{children}</main>

      <footer className="footnote">Every line is built from a quote you can check.</footer>
    </div>
  )
}
