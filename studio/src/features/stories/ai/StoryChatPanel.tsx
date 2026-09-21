import { type KeyboardEvent, useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../../../shared/api/client'
import type { AiProposal } from './AiReviewModal'
import './StoryChatPanel.css'

export type StoryChatMessage = ChatMessage & {
  proposal?: Pick<AiProposal, 'title' | 'dek' | 'content_html'>
  baseHtml?: string
}

export function StoryChatPanel({
  messages,
  sending,
  error,
  currentHtml,
  onSend,
  onApply,
  onClose,
}: {
  messages: StoryChatMessage[]
  sending: boolean
  error: string
  currentHtml: string
  onSend: (text: string) => Promise<boolean>
  onApply: (proposal: Pick<AiProposal, 'title' | 'dek' | 'content_html'>) => void
  onClose: () => void
}) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])
  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const send = async () => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setText('')
    const sent = await onSend(trimmed)
    if (!sent) setText((current) => current || trimmed)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      void send()
    }
  }

  return (
    <aside
      className="story-chat-panel"
      role="complementary"
      aria-label="Story chat"
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <header className="story-chat-header">
        <div>
          <p className="eyebrow">AI STORY TOOLS</p>
          <h2>Refine this story</h2>
        </div>
        <button type="button" className="story-chat-close" aria-label="Close story refinement chat" onClick={onClose}>×</button>
      </header>
      <div className="story-chat-messages" ref={messagesRef} aria-live="polite">
        {!messages.length && (
          <div className="story-chat-bubble story-chat-bubble--assistant">
            I can help revise this draft, discuss clarity and style, or flag attribution and verification gaps. I can only use the material in this story.
          </div>
        )}
        {messages.map((message, index) => {
          const stale =
            message.proposal?.content_html !== undefined && message.baseHtml !== undefined && message.baseHtml !== currentHtml
          return (
            <div className={`story-chat-message story-chat-message--${message.role}`} key={`${message.role}-${index}`}>
              <div className="story-chat-bubble">{message.content}</div>
              {message.proposal && (
                <div className="story-chat-proposal">
                  {stale && <small>Draft changed since this suggestion.</small>}
                  <button type="button" className="primary" onClick={() => onApply(message.proposal!)}>Apply to draft</button>
                </div>
              )}
            </div>
          )
        })}
        {sending && <div className="story-chat-bubble story-chat-bubble--assistant">Thinking…</div>}
        {error && <div className="story-chat-error" role="alert">{error}</div>}
      </div>
      <footer className="story-chat-composer">
        <input
          ref={inputRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about this draft…"
          aria-label="Message story refinement chat"
          disabled={sending}
        />
        <button type="button" className="primary" onClick={send} disabled={sending || !text.trim()}>Send</button>
      </footer>
    </aside>
  )
}
