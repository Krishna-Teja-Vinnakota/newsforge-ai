import './StoryChatPanel.css'

export function StoryChatLauncher({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="story-chat-launcher"
      aria-label={open ? 'Close story refinement chat' : 'Open story refinement chat'}
      aria-expanded={open}
      onClick={onToggle}
    >
      <span aria-hidden="true">{open ? '×' : '✦'}</span>
      <span className="story-chat-launcher-label">{open ? 'Close chat' : 'Refine story'}</span>
    </button>
  )
}
