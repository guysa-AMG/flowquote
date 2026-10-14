import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { formatCents } from '../lib/utils'

gsap.registerPlugin(ScrollTrigger)

const sampleQuoteLines = [
  { sku: 'COP-15-ELB', description: '15mm Copper Elbow', quantityMilli: 2000, unit: 'each', unitPriceCents: 1850 },
  { sku: 'LBR-PLM-STD', description: 'Plumbing Labour Standard', quantityMilli: 2000, unit: 'hours', unitPriceCents: 65000 },
  { sku: 'FEE-CALLOUT', description: 'Standard Call-out and Diagnostic Fee', quantityMilli: 1000, unit: 'each', unitPriceCents: 55000 },
]

function roundHalfUpRatio(numerator: number, denominator: number): number {
  return Math.floor((numerator + Math.floor(denominator / 2)) / denominator)
}

export default function Showcase() {
  const heroRef = useRef<HTMLDivElement>(null)
  const pipeRef = useRef<SVGPathElement>(null)
  const itemsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!heroRef.current || !pipeRef.current) return

    const media = gsap.matchMedia()
    media.add('(prefers-reduced-motion: reduce)', () => {
      const path = pipeRef.current
      if (!path) return
      gsap.set(path, { strokeDashoffset: 0 })
      dropItem(0, false)
      dropItem(1, false)
    })
    media.add('(prefers-reduced-motion: no-preference)', () => {
      const ctx = gsap.context(() => {
      const path = pipeRef.current!
      const pathLength = path.getTotalLength()

      gsap.set(path, {
        strokeDasharray: pathLength,
        strokeDashoffset: pathLength,
      })

      gsap.to(path, {
        strokeDashoffset: 0,
        duration: 3,
        ease: 'power2.inOut',
        onUpdate: () => {
          const progress = 1 - Number(path.getAttribute('stroke-dashoffset')!) / pathLength
          if (progress > 0.3 && !itemsRef.current?.dataset.item1) {
            dropItem(0)
          }
          if (progress > 0.7 && !itemsRef.current?.dataset.item2) {
            dropItem(1)
          }
        },
      })
      }, heroRef)
      return () => ctx.revert()
    })

    return () => {
      media.revert()
      if (itemsRef.current) {
        itemsRef.current.replaceChildren()
        delete itemsRef.current.dataset.item1
        delete itemsRef.current.dataset.item2
      }
    }
  }, [])

  const dropItem = (index: number, withMotion = true) => {
    if (!itemsRef.current) return
    const item = document.createElement('div')
    item.className = [
      'absolute px-4 py-2 bg-white border border-galvanised rounded-lg shadow-lg font-medium text-sm',
      withMotion ? 'animate-bounce-in' : '',
    ].filter(Boolean).join(' ')
    item.textContent = index === 0 ? 'Geyser element 3kW' : '2 hours labour'
    item.style.left = `${200 + index * 150}px`
    item.style.top = `${100 + index * 80}px`
    itemsRef.current.appendChild(item)
    itemsRef.current.dataset[`item${index + 1}`] = 'true'
  }

  useEffect(() => {
    const media = gsap.matchMedia()
    media.add('(prefers-reduced-motion: no-preference)', () => {
      const ctx = gsap.context(() => {
        gsap.to('.explainer-content', {
          y: -300,
          scrollTrigger: {
            trigger: '.explainer-section',
            start: 'top center',
            end: 'bottom center',
            scrub: 1,
            pin: '.explainer-pin',
          },
        })
      })
      return () => ctx.revert()
    })

    return () => media.revert()
  }, [])

  const subtotal = sampleQuoteLines.reduce(
    (sum, line) => sum + roundHalfUpRatio(line.quantityMilli * line.unitPriceCents, 1000),
    0,
  )
  const vat = roundHalfUpRatio(subtotal * 1500, 10000)

  return (
    <div className="min-h-screen bg-teflon font-body">
      <section ref={heroRef} className="relative min-h-screen flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-teflon to-white" />

        <svg className="absolute w-full h-full max-w-4xl" viewBox="0 0 800 400" preserveAspectRatio="xMidYMid slice">
          <defs>
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>

          <path
            ref={pipeRef}
            d="M 100 200
               Q 200 200, 200 100
               Q 200 0, 300 0
               Q 400 0, 400 100
               Q 400 200, 500 200
               Q 600 200, 600 300
               Q 600 400, 700 400"
            stroke="#1C57F2"
            strokeWidth="4"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#glow)"
          />

          <circle cx="200" cy="100" r="12" fill="#1C57F2" className="elbow" />
          <circle cx="400" cy="100" r="12" fill="#1C57F2" className="elbow" />
          <circle cx="600" cy="300" r="12" fill="#1C57F2" className="elbow" />
        </svg>

        <div ref={itemsRef} className="absolute inset-0 pointer-events-none" />

        <div className="relative z-10 text-center px-4 max-w-3xl">
          <h1 className="font-display text-5xl md:text-7xl font-bold text-slate-ink leading-tight mb-6 animate-fade-up">
            Voice becomes plumbing becomes paperwork.
          </h1>
          <p className="text-xl md:text-2xl text-slate-ink/60 mb-10 animate-fade-up animate-delay-100">
            Record a voice memo on site. TalkQuote transcribes, matches your price list,
            and generates a quote PDF. No internet required.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center animate-fade-up animate-delay-200">
            <Link to="/app/record" className="btn-primary text-lg px-8">
              Try TalkQuote
            </Link>
            <Link to="/app/record" className="btn-secondary text-lg px-8">
              Watch Demo
            </Link>
          </div>
        </div>

        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 animate-bounce">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#14222E" strokeWidth="2">
            <path d="M12 5v14M19 12l-7 7-7-7" />
          </svg>
        </div>
      </section>

      <section className="py-20 px-4 bg-white" aria-labelledby="sample-quote-title">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-cold-blue">
              Read-only example
            </p>
            <h2 id="sample-quote-title" className="font-display text-3xl md:text-4xl font-bold text-slate-ink mt-2">
              A quote built from the sample price list
            </h2>
            <p className="text-sm text-slate-ink/60 mt-2">
              Synthetic example data; not a customer quote. Prices and 15% VAT use the repository's sample configuration.
            </p>
          </div>
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-galvanised flex flex-wrap justify-between gap-2">
              <span className="font-semibold">Example quote · Q-SAMPLE-01</span>
              <span className="text-sm text-slate-ink/60">Preview only</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-teflon text-slate-ink/70">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Item</th>
                    <th className="px-4 py-3 text-right font-medium">Qty</th>
                    <th className="px-4 py-3 text-right font-medium">Unit price</th>
                    <th className="px-4 py-3 text-right font-medium">Line total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-galvanised/50">
                  {sampleQuoteLines.map(line => {
                    const lineTotal = roundHalfUpRatio(
                      line.quantityMilli * line.unitPriceCents,
                      1000,
                    )
                    return (
                      <tr key={line.sku}>
                        <td className="px-4 py-3">
                          <span className="font-medium">{line.description}</span>
                          <span className="block text-xs text-slate-ink/50">{line.sku}</span>
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {line.quantityMilli / 1000} {line.unit}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {formatCents(line.unitPriceCents)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums font-medium">
                          {formatCents(lineTotal)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="border-t border-galvanised bg-teflon p-4">
              <dl className="ml-auto max-w-xs space-y-2">
                <div className="flex justify-between gap-4">
                  <dt>Subtotal</dt><dd className="tabular-nums">{formatCents(subtotal)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>VAT (15%)</dt><dd className="tabular-nums">{formatCents(vat)}</dd>
                </div>
                <div className="flex justify-between gap-4 border-t border-galvanised pt-2 font-semibold">
                  <dt>Total</dt><dd className="tabular-nums">{formatCents(subtotal + vat)}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </section>

      <section className="explainer-section relative min-h-screen">
        <div className="explainer-pin fixed inset-0 z-0">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-4xl h-[60vh] bg-white/90 backdrop-blur-sm rounded-2xl border border-galvanised shadow-2xl p-8 md:p-16 flex items-center justify-center">
            <div className="explainer-content text-center max-w-2xl">
              <h2 className="font-display text-4xl md:text-5xl font-bold text-slate-ink mb-6">
                How it works
              </h2>
              <div className="space-y-6 text-left">
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-cold-blue/10 flex items-center justify-center flex-shrink-0 text-2xl">🎙️</div>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-slate-ink">Record</h3>
                    <p className="text-slate-ink/60">Speak naturally: "Replaced the geyser element, two hours labour, new thermostat"</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-cold-blue/10 flex items-center justify-center flex-shrink-0 text-2xl">🔍</div>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-slate-ink">Extract</h3>
                    <p className="text-slate-ink/60">Local LLM extracts items, quantities, units — never prices</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-cold-blue/10 flex items-center justify-center flex-shrink-0 text-2xl">🔗</div>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-slate-ink">Match</h3>
                    <p className="text-slate-ink/60">Code matches to your price list: confident, ambiguous (you pick), or no-match</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-cold-blue/10 flex items-center justify-center flex-shrink-0 text-2xl">💰</div>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-slate-ink">Price</h3>
                    <p className="text-slate-ink/60">Integer-cent math, VAT calculated, prices snapshotted — 100% correct by construction</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-cold-blue/10 flex items-center justify-center flex-shrink-0 text-2xl">✅</div>
                  <div>
                    <h3 className="font-display text-lg font-semibold text-slate-ink">Approve</h3>
                    <p className="text-slate-ink/60">Review flags, approve, share PDF via WhatsApp or email</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="relative z-10 h-[200vh]" />
      </section>

      <section className="py-20 px-4 bg-white">
        <div className="max-w-6xl mx-auto">
          <h2 className="font-display text-4xl font-bold text-slate-ink text-center mb-16">
            Built for the trade
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: '📴', title: 'Offline First', desc: 'Works on a hotspot with no upstream. Audio queued in IndexedDB, syncs when online.' },
              { icon: '🔒', title: 'Your Data Stays Yours', desc: 'No cloud transcription. No cloud LLM. Everything runs on your machine.' },
              { icon: '⚡', title: 'No Guessing', desc: 'Ambiguous items flagged for your review. Confident-wrong rate targeted at zero.' },
              { icon: '📋', title: 'Your Price List', desc: 'Import CSV, edit inline, manage aliases for trade slang (geezer → geyser).' },
              { icon: '🔄', title: 'Variation Orders', desc: 'Mid-job extras become priced variations linked to the original quote.' },
              { icon: '📊', title: 'Full Audit Trail', desc: 'Every decision logged: transcript, extraction, match, manual override, approval.' },
            ].map((feature, i) => (
              <div key={i} className="card p-6 hover:shadow-lg transition-shadow">
                <div className="text-4xl mb-4">{feature.icon}</div>
                <h3 className="font-display text-xl font-semibold text-slate-ink mb-2">{feature.title}</h3>
                <p className="text-slate-ink/60">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 bg-teflon">
        <div className="max-w-6xl mx-auto">
          <h2 className="font-display text-4xl font-bold text-slate-ink text-center mb-16">
            Open Stack
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { name: 'faster-whisper', desc: 'Local ASR, no cloud', license: 'MIT' },
              { name: 'Ollama + Gemma/Qwen', desc: 'Local LLM, structured output', license: 'MIT / Custom' },
              { name: 'RapidFuzz', desc: 'Fast fuzzy matching', license: 'MIT' },
              { name: 'SQLite WAL', desc: 'Embedded database', license: 'Public Domain' },
              { name: 'FastAPI', desc: 'Python API framework', license: 'MIT' },
              { name: 'React + Vite PWA', desc: 'Offline-capable frontend', license: 'MIT' },
              { name: 'WeasyPrint', desc: 'PDF generation', license: 'BSD-3' },
              { name: 'GSAP', desc: 'Animation (showcase only)', license: 'Standard/Business' },
            ].map((tech, i) => (
              <div key={i} className="card p-6">
                <h3 className="font-display text-lg font-semibold text-slate-ink mb-1">{tech.name}</h3>
                <p className="text-slate-ink/60 text-sm mb-2">{tech.desc}</p>
                <span className="text-xs bg-galvanised text-slate-ink px-2 py-1 rounded">{tech.license}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 bg-slate-ink text-white">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="font-display text-4xl font-bold mb-6">Ready to stop doing paperwork at 9 PM?</h2>
          <p className="text-slate-ink/30 mb-8 text-lg">Deploy with <code className="bg-white/10 px-2 py-1 rounded">docker compose up</code> — runs on a laptop, a mini-PC in the van, or a hosted GPU box.</p>
          <Link to="/app/record" className="inline-flex items-center gap-2 bg-white text-slate-ink px-8 py-4 rounded-lg font-semibold hover:bg-white/90 transition-colors">
            Get Started →
          </Link>
        </div>
      </section>
    </div>
  )
}
