import { DragEvent, MouseEvent, ReactNode, useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { Fragment } from '@tiptap/pm/model'
import { Bold, Code2, GripVertical, Heading2, ImagePlus, Italic, Link2, List, ListOrdered, Plus, Quote, Redo2, Undo2 } from 'lucide-react'
import { DialogForm, StudioDialog } from '../../../StudioDialog'
import '../../../NotionTiptapEditor.css'
import './SlashMenu.css'

type AssetKind = 'link' | 'image' | null
type BlockCommand = { category: string; label: string; description: string; execute: () => void }

export function NotionTiptapEditor({ value, onChange, editable = true }: { value: string; onChange: (html: string) => void; editable?: boolean }) {
  const [hovered, setHovered] = useState<{ index: number; top: number } | null>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const [asset, setAsset] = useState<AssetKind>(null)
  const [assetUrl, setAssetUrl] = useState('')
  const [slashOpen, setSlashOpen] = useState(false)
  const [slashQuery, setSlashQuery] = useState('')
  const [slashIndex, setSlashIndex] = useState(0)
  const [selectionActive, setSelectionActive] = useState(false)
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ codeBlock: { HTMLAttributes: { class: 'nf-code-block' } } }),
      Link.configure({ openOnClick: false, autolink: true }),
      Image.configure({ HTMLAttributes: { class: 'nf-inline-image' } }),
      Placeholder.configure({ placeholder: 'Write your story, or type / for blocks…' }),
    ],
    content: value,
    editable,
    editorProps: {
      handleKeyDown: (_view, event) => {
        if (event.key === '/') { setSlashOpen(true); setSlashQuery(''); setSlashIndex(0); return false }
        if (slashOpen && event.key === 'ArrowDown') { event.preventDefault(); setSlashIndex(index => Math.min(index + 1, commands.length - 1)); return true }
        if (slashOpen && event.key === 'ArrowUp') { event.preventDefault(); setSlashIndex(index => Math.max(index - 1, 0)); return true }
        if (slashOpen && event.key === 'Enter') { event.preventDefault(); commands[slashIndex]?.execute(); return true }
        if (event.key === 'Escape') { setSlashOpen(false); return true }
        return false
      },
    },
    onSelectionUpdate: ({ editor: activeEditor }) => setSelectionActive(!activeEditor.state.selection.empty),
    onUpdate: ({ editor: activeEditor }) => {
      const { from } = activeEditor.state.selection
      const before = activeEditor.state.doc.textBetween(Math.max(0, from - 30), from, ' ')
      const match = before.match(/\/([^\s/]*)$/)
      setSlashQuery(match?.[1] ?? '')
      if (!match) setSlashOpen(false)
      onChange(activeEditor.getHTML())
    },
  })

  useEffect(() => { if (editor && value !== editor.getHTML()) editor.commands.setContent(value) }, [editor, value])
  useEffect(() => { editor?.setEditable(editable) }, [editor, editable])
  if (!editor) return null

  const topLevelBlocks = () => Array.from(editor.view.dom.children) as HTMLElement[]
  const blockFromTarget = (target: EventTarget | null) => {
    const element = target instanceof HTMLElement ? target : null
    const block = element?.closest('.ProseMirror > *') as HTMLElement | null
    if (!block || block.parentElement !== editor.view.dom) return null
    const index = topLevelBlocks().indexOf(block)
    return index < 0 ? null : { index, element: block }
  }
  const removeSlash = () => {
    const from = editor.state.selection.from
    const before = editor.state.doc.textBetween(Math.max(0, from - 40), from, ' ')
    const match = before.match(/\/([^\s/]*)$/)
    if (match) editor.commands.deleteRange({ from: from - match[0].length, to: from })
  }
  const insertAfter = (index: number) => {
    let position = 0
    editor.state.doc.forEach((node, offset, childIndex) => { if (childIndex === index) position = offset + node.nodeSize })
    editor.chain().focus().insertContentAt(position, { type: 'paragraph' }).run()
  }
  const move = (from: number, target: number) => {
    if (target === from || target === from + 1) return
    const nodes: Array<(typeof editor.state.doc.content.content)[number]> = []
    editor.state.doc.forEach(node => nodes.push(node))
    const [block] = nodes.splice(from, 1)
    nodes.splice(target > from ? target - 1 : target, 0, block)
    editor.view.dispatch(editor.state.tr.replaceWith(0, editor.state.doc.content.size, Fragment.fromArray(nodes)))
    editor.commands.focus()
  }
  const dropAt = (event: DragEvent<HTMLDivElement>) => {
    const blocks = topLevelBlocks()
    for (let index = 0; index < blocks.length; index += 1) {
      const rect = blocks[index].getBoundingClientRect()
      if (event.clientY < rect.top + rect.height / 2) return index
    }
    return blocks.length
  }
  const markerTop = (index: number) => {
    const blocks = topLevelBlocks()
    if (!blocks.length) return 0
    return index >= blocks.length ? blocks[blocks.length - 1].offsetTop + blocks[blocks.length - 1].offsetHeight : blocks[index].offsetTop
  }
  const openAsset = (kind: Exclude<AssetKind, null>) => { setAsset(kind); setAssetUrl(kind === 'link' ? editor.getAttributes('link').href ?? '' : '') }
  const saveAsset = () => {
    const url = assetUrl.trim()
    if (!url) return
    if (asset === 'link') editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    if (asset === 'image') editor.chain().focus().setImage({ src: url }).run()
    setAsset(null); setAssetUrl('')
  }
  const command = (category: string, label: string, description: string, execute: () => void): BlockCommand => ({ category, label, description, execute: () => { removeSlash(); execute(); setSlashOpen(false); setSlashIndex(0); editor.commands.focus() } })
  const commands = [
    command('Basic blocks', 'Text', 'Plain paragraph', () => editor.chain().focus().setParagraph().run()),
    command('Basic blocks', 'Heading 1', 'Large section heading', () => editor.chain().focus().toggleHeading({ level: 1 }).run()),
    command('Basic blocks', 'Heading 2', 'Medium section heading', () => editor.chain().focus().toggleHeading({ level: 2 }).run()),
    command('Basic blocks', 'Heading 3', 'Small section heading', () => editor.chain().focus().toggleHeading({ level: 3 }).run()),
    command('Lists & structure', 'Bullet list', 'A simple list', () => editor.chain().focus().toggleBulletList().run()),
    command('Lists & structure', 'Numbered list', 'An ordered list', () => editor.chain().focus().toggleOrderedList().run()),
    command('Lists & structure', 'Quote', 'Editorial pull quote', () => editor.chain().focus().toggleBlockquote().run()),
    command('Lists & structure', 'Divider', 'Horizontal section break', () => editor.chain().focus().setHorizontalRule().run()),
    command('Media & code', 'Code block', 'Code or structured text', () => editor.chain().focus().toggleCodeBlock().run()),
    command('Media & code', 'Image', 'Insert image from a URL', () => openAsset('image')),
  ].filter(item => `${item.label} ${item.description}`.toLowerCase().includes(slashQuery.toLowerCase()))
  const button = (label: string, icon: ReactNode, action: () => void, active = false) => <button type="button" title={label} aria-label={label} className={active ? 'active' : ''} onMouseDown={event => event.preventDefault()} onClick={action}>{icon}</button>
  const dragAllowed = dragging !== null && dropIndex !== null && dropIndex !== dragging && dropIndex !== dragging + 1
  const onCanvasMove = (event: MouseEvent<HTMLDivElement>) => {
    const block = blockFromTarget(event.target)
    if (!block) return
    const canvas = event.currentTarget.getBoundingClientRect()
    setHovered({ index: block.index, top: block.element.getBoundingClientRect().top - canvas.top + 2 })
  }

  return <section className="nf-editor">{editable && <><header className="nf-editor-toolbar"><div className="nf-history">{button('Undo', <Undo2/>, () => editor.chain().focus().undo().run())}{button('Redo', <Redo2/>, () => editor.chain().focus().redo().run())}</div><div className="nf-toolbar-group">{button('Bold', <Bold/>, () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}{button('Italic', <Italic/>, () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}{button('Heading', <Heading2/>, () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading', { level: 2 }))}{button('Bullet list', <List/>, () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}{button('Numbered list', <ListOrdered/>, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}{button('Quote', <Quote/>, () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}{button('Code block', <Code2/>, () => editor.chain().focus().toggleCodeBlock().run(), editor.isActive('codeBlock'))}</div><div className="nf-toolbar-group">{button('Add link', <Link2/>, () => openAsset('link'), editor.isActive('link'))}{button('Insert image', <ImagePlus/>, () => openAsset('image'))}</div></header>{selectionActive && <div className="nf-selection-menu">{button('Bold', <Bold/>, () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}{button('Italic', <Italic/>, () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}{button('Add link', <Link2/>, () => openAsset('link'))}</div>}{slashOpen && <aside className="nf-slash-menu"><b>Insert a block</b>{commands.length ? ['Basic blocks','Lists & structure','Media & code'].map(category => <section key={category}><strong>{category}</strong>{commands.map((item,index) => item.category===category && <button key={item.label} className={index===slashIndex?'selected':''} type="button" onMouseEnter={()=>setSlashIndex(index)} onClick={item.execute}><span>{item.label}</span><small>{item.description}</small></button>)}</section>) : <p>No matching block</p>}<footer>↑ ↓ to select · Enter to insert</footer></aside>}</>}<div className={`nf-editor-canvas${dragging !== null ? ' dragging' : ''}${dragging !== null && !dragAllowed ? ' invalid-drop' : ''}`} onMouseMove={onCanvasMove} onMouseLeave={() => dragging === null && setHovered(null)} onDragOver={editable ? event => { event.preventDefault(); const target = dropAt(event); const allowed = dragging !== null && target !== dragging && target !== dragging + 1; event.dataTransfer.dropEffect = allowed ? 'move' : 'none'; setDropIndex(target) } : undefined} onDrop={editable ? event => { event.preventDefault(); const target = dropAt(event); if (dragging !== null && target !== dragging && target !== dragging + 1) move(dragging, target); setDragging(null); setDropIndex(null) } : undefined}><EditorContent editor={editor}/>{editable && hovered && <div className="nf-block-controls" style={{ top: hovered.top }}><button type="button" title="Insert block below" aria-label="Insert block below" onMouseDown={event => event.preventDefault()} onClick={() => insertAfter(hovered.index)}><Plus/></button><button type="button" className="nf-drag-handle" title="Drag to move block" aria-label="Drag to move block" draggable onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(hovered.index)); setDragging(hovered.index); setDropIndex(null) }} onDragEnd={() => { setDragging(null); setDropIndex(null) }}><GripVertical/></button></div>}{editable && dragAllowed && <div className="nf-drop-marker" style={{ top: markerTop(dropIndex!) }}/>}</div>{editable && <footer className="nf-editor-hint">Hover a block to insert or reorder it. Type <kbd>/</kbd> to open the block menu.</footer>}{asset && <StudioDialog title={asset === 'link' ? 'Add link' : 'Insert image'} onClose={() => setAsset(null)}><DialogForm onSubmit={event => { event.preventDefault(); saveAsset() }}><label>{asset === 'link' ? 'Destination URL' : 'Image URL'}<input autoFocus type="url" value={assetUrl} onChange={event => setAssetUrl(event.target.value)} placeholder="https://…" required/></label><div className="dialog-actions"><button type="button" onClick={() => setAsset(null)}>Cancel</button><button className="dialog-primary" type="submit">{asset === 'link' ? 'Add link' : 'Insert image'}</button></div></DialogForm></StudioDialog>}</section>
}
