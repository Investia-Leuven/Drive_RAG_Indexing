import { useState, useRef, useEffect } from 'react'

const MODES = [
  { value: 'strict', label: 'Context only' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'general', label: 'General' },
]

// In dev, call the backend directly to avoid proxy 403; override with VITE_API_URL if needed
const API_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:5000/api/chat' : '/api/chat')

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSubmit(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', text }])
    setLoading(true)

    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, mode }),
      })
      const data = await res.json().catch(() => ({}))

      if (!res.ok) {
        const friendly = data?.error ?? data?.message ?? 'Something went wrong.'
        let detail = data?.detail ?? data?.body ?? res.statusText
        const isQuotaError = typeof detail === 'string' && (
          detail.includes('429') || detail.includes('quota') || detail.includes('RESOURCE_EXHAUSTED')
        )
        let hint = ''
        if (res.status === 403) {
          hint = ' Make sure the backend is running (python -m api.server from the project root).'
        } else if (isQuotaError) {
          hint = ' Wait a minute and try again, or add a second Gemini key as GEMINI_API_KEY_2 in your .env for automatic fallback.'
          if (detail.length > 200) detail = detail.slice(0, 200) + '…'
        } else if (res.status === 500 && detail) {
          hint = ' Check your .env (Supabase and Gemini keys) and the terminal where the backend runs for more detail.'
        }
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: null,
            error: true,
            errorSummary: friendly,
            errorDetail: detail,
            errorHint: hint,
          },
        ])
        setError(friendly)
        return
      }

      const answer = data.answer ?? 'No answer returned.'
      const sources = data.sources ?? []

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: answer, sources },
      ])
    } catch (err) {
      const msg = err.message || 'Something went wrong.'
      setError(msg)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: null,
          error: true,
          errorSummary: 'The request could not be completed.',
          errorDetail: msg,
          errorHint: ' Check that the backend is running and the app can reach it.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-white text-slate-800">
      {/* Header */}
      <header className="relative flex items-center justify-between shrink-0 px-12 py-3 border-b border-slate-200 bg-white">
        <img
          src="/lupus-logo.png"
          alt=""
          className="h-16 w-auto object-contain"
          onError={(e) => {
            e.target.onerror = null
            e.target.src = '/logo.png'
          }}
        />
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-0.5">
          <h1
            className="text-3xl font-semibold tracking-tight bg-clip-text text-transparent"
            style={{
              backgroundImage: 'linear-gradient(135deg, #8b5cf6 0%, #3b82f6 50%, #10b981 100%)',
            }}
          >
            Lupus
          </h1>
          <span
            className="text-lg font-medium tracking-tight bg-clip-text text-transparent"
            style={{
              backgroundImage: 'linear-gradient(135deg, #8b5cf6 0%, #3b82f6 50%, #10b981 100%)',
            }}
          >
            Investia RAG
          </span>
        </div>
        <img
          src="/logo.png"
          alt="Club logo"
          className="h-16 w-auto object-contain"
          onError={(e) => {
            e.target.style.display = 'none'
          }}
        />
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-12 py-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-slate-500 text-center text-sm py-8">
            Ask a question about your Drive documents. Choose Context only, Hybrid, or General below.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-violet-600 text-white'
                  : msg.error
                    ? 'bg-red-50 text-red-800 border border-red-200'
                    : 'bg-slate-100 text-slate-800 border border-slate-200'
              }`}
            >
              {msg.error ? (
                <div className="text-sm space-y-2">
                  <p className="font-medium">What happened</p>
                  <p>{msg.errorSummary ?? msg.error ?? 'Something went wrong.'}</p>
                  {msg.errorDetail && (
                    <p className="text-red-600 text-xs mt-1.5">
                      Technical detail: {msg.errorDetail}
                    </p>
                  )}
                  {msg.errorHint && (
                    <p className="text-amber-800 text-xs mt-1">
                      What you can do:{msg.errorHint}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
              )}
              {msg.sources?.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-200">
                  <p className="text-xs text-slate-500 mb-1">Sources:</p>
                  <ul className="text-xs text-slate-600 space-y-0.5">
                    {msg.sources.slice(0, 3).map((s, j) => (
                      <li key={j}>
                        {s.title || s.doc_id}
                        {s.drive_url && (
                          <a
                            href={s.drive_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-1 text-violet-600 hover:underline"
                          >
                            Link
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-2.5 bg-slate-100 border border-slate-200">
              <span className="text-slate-500 text-sm">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {/* Error banner */}
      {error && (
        <div className="shrink-0 px-12 py-2 bg-red-50 border-t border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Input area */}
      <footer className="shrink-0 border-t border-slate-200 bg-slate-50 px-12 pt-4 pb-8">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                mode === m.value
                  ? 'bg-violet-600 text-white'
                  : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask something..."
            className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="shrink-0 rounded-xl bg-violet-600 px-5 py-3 font-medium text-white hover:bg-violet-500 disabled:opacity-50 disabled:pointer-events-none transition-colors"
          >
            Send
          </button>
        </form>
      </footer>
    </div>
  )
}
