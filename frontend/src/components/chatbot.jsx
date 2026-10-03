import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, LogIn, MessageCircle, Send, Sparkles, ThumbsDown, ThumbsUp, Minus, X } from 'lucide-react';
import { chatApi } from '../services/api';

// Rendered locally, never derived from a backend error body, so stack traces,
// exception text and debug data can never reach the user.
const GREETING = 'Hi! How can I help you today? You can ask about products, orders, or store policies.';
const CONNECTION_ERROR = "Sorry, I'm having trouble connecting right now. Please try again.";
const LOGIN_PROMPT = 'Please log in so I can look up your orders.';
const MAX_LENGTH = 500;

// crypto.randomUUID needs a secure context, so fall back for plain-http LAN
// hosts (e.g. opening the dev server from a phone) instead of crashing.
function newConversationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const RATINGS = [
  { value: 1, label: 'Bad', Icon: ThumbsDown, active: 'border-red-300 bg-red-50 text-red-700' },
  { value: 2, label: 'Neutral', Icon: Minus, active: 'border-amber-300 bg-amber-50 text-amber-700' },
  { value: 3, label: 'Excellent', Icon: ThumbsUp, active: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
];

const role = {
  ai: 'max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3.5 py-2.5 text-sm leading-relaxed text-slate-700 shadow-card',
  user: 'ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-brand-600 px-3.5 py-2.5 text-sm leading-relaxed text-white shadow-card',
};

function Sources({ sources }) {
  if (!sources.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-slate-400">
      <span>Sources:</span>
      {sources.map((s) => (
        <span key={s} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{s}</span>
      ))}
    </div>
  );
}

function Bubble({ m }) {
  if (m.role === 'user') return <div className={role.user}>{m.text}</div>;
  const tone = m.error
    ? 'max-w-[85%] rounded-2xl rounded-bl-sm border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm leading-relaxed text-red-700'
    : m.requiresAuth
      ? 'max-w-[85%] rounded-2xl rounded-bl-sm border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm leading-relaxed text-amber-800'
      : role.ai;
  return (
    <div>
      <div className={tone}>
        <span className="sr-only">Shoply AI Assistant: </span>
        {m.text}
        {m.requiresAuth && (
          <Link to="/login" className="btn-outline mt-2.5 py-1.5 text-xs">
            <LogIn size={14} />Log in
          </Link>
        )}
      </div>
      <Sources sources={m.sources} />
    </div>
  );
}

function Typing() {
  return (
    <div className="flex max-w-[85%] items-center gap-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3.5 py-3 shadow-card">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" style={{ animationDelay: `${delay}ms` }} />
        ))}
      </span>
      <span className="text-xs text-slate-400">AI is typing...</span>
    </div>
  );
}

function FeedbackCard({ state, onRate, onDismiss }) {
  if (state === 'hidden') return null;

  return (
    <motion.section
      id="shoply-ai-feedback"
      role="dialog"
      aria-label="Rate your chat experience"
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.97 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="fixed inset-x-3 bottom-24 z-50 rounded-2xl border border-slate-200 bg-white p-4 shadow-lift sm:inset-x-auto sm:bottom-24 sm:right-6 sm:w-[400px]"
    >
      {state === 'done' ? (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <Check size={18} />
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-900">Thanks for your feedback!</p>
            <p className="text-xs text-slate-500">Closing in a moment...</p>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">How was your experience?</h2>
              <p className="mt-0.5 text-xs text-slate-500">Your rating helps us improve the assistant.</p>
            </div>
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss feedback"
              className="shrink-0 rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <X size={16} />
            </button>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {RATINGS.map(({ value, label, Icon, active }) => (
              <button
                key={value}
                type="button"
                data-rating={value}
                onClick={() => onRate(value)}
                className={`flex flex-col items-center gap-1 rounded-xl border border-slate-200 px-2 py-2.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${active}`}
              >
                <Icon size={18} />
                {label}
              </button>
            ))}
          </div>
        </>
      )}
    </motion.section>
  );
}

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  // Lives above the open/closed flag, so closing and reopening in the same page
  // session keeps the conversation.
  const [messages, setMessages] = useState(() => [{ id: 1, role: 'ai', text: GREETING, sources: [] }]);
  // One id per page session: every message of this conversation shares it, and a
  // reload starts a fresh conversation. It is the only thing sent to the API -
  // no user id ever leaves the browser.
  const [conversationId] = useState(newConversationId);
  // 'hidden' -> 'open' -> 'sent'. One rating per conversation, enforced by both
  // this state and the unique constraint on the backend.
  const [feedback, setFeedback] = useState('hidden');
  const ratedRef = useRef(false);
  const askedRef = useRef(false);
  const seq = useRef(1);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const launcherRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const push = (m) => setMessages((prev) => [...prev, { id: ++seq.current, ...m }]);

  // Rating is asked for only when the customer actually said something - the
  // greeting alone is not a conversation worth rating. Read from a ref so the
  // Escape listener, which is registered once per open/close, never sees a
  // stale message list.
  const close = () => {
    setOpen(false);
    launcherRef.current?.focus();
    if (askedRef.current && !ratedRef.current) setFeedback('open');
  };

  const rate = async (rating) => {
    if (ratedRef.current) return; // one submission per conversation
    ratedRef.current = true;
    setFeedback('sent');
    try {
      await chatApi.feedback(conversationId, rating);
    } catch {
      ratedRef.current = false; // let them retry a failed request
      setFeedback('open');
      return;
    }
    setFeedback('done');
    setTimeout(() => setFeedback('hidden'), 2000);
  };

  const send = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return; // guard against duplicate submissions
    setDraft('');
    push({ role: 'user', text });
    askedRef.current = true;
    setBusy(true);
    try {
      const res = await chatApi.send(text);
      const answer = typeof res?.answer === 'string' ? res.answer.trim() : '';
      push({
        role: 'ai',
        text: answer || CONNECTION_ERROR,
        sources: Array.isArray(res?.sources) ? res.sources.filter((s) => typeof s === 'string') : [],
        requiresAuth: res?.requires_auth === true,
        error: !answer,
      });
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) push({ role: 'ai', text: LOGIN_PROMPT, sources: [], requiresAuth: true });
      else push({ role: 'ai', text: CONNECTION_ERROR, sources: [], error: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.section
            id="shoply-ai-panel"
            role="dialog"
            aria-label="Shoply AI Assistant"
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.97 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="fixed inset-x-3 bottom-24 top-20 z-50 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lift sm:inset-x-auto sm:bottom-24 sm:left-auto sm:right-6 sm:top-auto sm:h-[600px] sm:w-[400px]"
          >
            <header className="flex items-center justify-between gap-3 bg-brand-600 px-4 py-3 text-white">
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/15">
                  <Sparkles size={16} />
                </span>
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold">Shoply AI Assistant</h2>
                  <p className="truncate text-[11px] text-brand-100">Products, orders and store policies</p>
                </div>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close chat"
                className="shrink-0 rounded-lg p-1.5 text-white/90 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                <X size={18} />
              </button>
            </header>

            <div
              ref={scrollRef}
              role="log"
              aria-live="polite"
              aria-relevant="additions text"
              className="flex-1 space-y-3 overflow-y-auto overscroll-contain bg-slate-50 px-4 py-4"
            >
              {messages.map((m) => <Bubble key={m.id} m={m} />)}
              {busy && <Typing />}
            </div>

            <form onSubmit={send} className="border-t border-slate-100 bg-white p-3">
              <label htmlFor="shoply-ai-input" className="sr-only">Message Shoply AI Assistant</label>
              <div className="flex items-end gap-2">
                <input
                  id="shoply-ai-input"
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value.slice(0, MAX_LENGTH))}
                  placeholder="Ask about products, orders or policies..."
                  autoComplete="off"
                  aria-label="Message Shoply AI Assistant"
                  className="input flex-1"
                />
                <button
                  type="submit"
                  disabled={busy || !draft.trim()}
                  aria-label="Send message"
                  className="btn-primary shrink-0 px-3 py-2.5"
                >
                  <Send size={18} />
                </button>
              </div>
            </form>
          </motion.section>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {feedback !== 'hidden' && (
          <FeedbackCard state={feedback} onRate={rate} onDismiss={() => setFeedback('hidden')} />
        )}
      </AnimatePresence>

      <button
        ref={launcherRef}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-controls="shoply-ai-panel"
        aria-label={open ? 'Close Shoply AI Assistant' : 'Open Shoply AI Assistant'}
        className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-lift transition duration-200 hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 active:scale-95 sm:bottom-6 sm:right-6"
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={open ? 'close' : 'open'}
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex items-center justify-center"
          >
            {open ? <X size={24} /> : <MessageCircle size={24} />}
          </motion.span>
        </AnimatePresence>
      </button>
    </>
  );
}