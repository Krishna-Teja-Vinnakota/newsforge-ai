import { useCallback, useEffect } from 'react'
import { EditorContent, useEditor, type JSONContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { Bold, ImagePlus, Italic, Link as LinkIcon, List, ListOrdered, Quote, Undo2 } from 'lucide-react'

import { cmsService } from '@/services/cms'

type TiptapEditorProps = {
  content?: JSONContent
  onChange: (json: JSONContent, html: string) => void
}

export function TiptapEditor({ content, onChange }: TiptapEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Image,
      Link.configure({ openOnClick: false }),
      Placeholder.configure({ placeholder: 'Start writing the story…' }),
    ],
    content,
    editorProps: { attributes: { class: 'tiptap-content' } },
    onUpdate: ({ editor: instance }) => onChange(instance.getJSON(), instance.getHTML()),
  })

  useEffect(() => {
    if (editor && content && JSON.stringify(editor.getJSON()) !== JSON.stringify(content))
      editor.commands.setContent(content, { emitUpdate: false })
  }, [content, editor])

  const uploadImage = useCallback(
    async (file?: File) => {
      if (!file || !editor) return
      const media = await cmsService.uploadMedia(file, 'inline')
      editor.chain().focus().setImage({ src: media.url, alt: file.name }).run()
    },
    [editor]
  )

  if (!editor) return null
  const promptForLink = () => {
    const href = window.prompt('Paste a link')
    if (href) editor.chain().focus().extendMarkRange('link').setLink({ href }).run()
  }
  return (
    <div className="tiptap-shell">
      <div className="tiptap-toolbar" aria-label="Text formatting">
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleBold().run()}
          className={editor.isActive('bold') ? 'active' : ''}
          aria-label="Bold"
        >
          <Bold size={16} />
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleItalic().run()}
          className={editor.isActive('italic') ? 'active' : ''}
          aria-label="Italic"
        >
          <Italic size={16} />
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          className={editor.isActive('bulletList') ? 'active' : ''}
          aria-label="Bullet list"
        >
          <List size={16} />
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          className={editor.isActive('orderedList') ? 'active' : ''}
          aria-label="Numbered list"
        >
          <ListOrdered size={16} />
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          className={editor.isActive('blockquote') ? 'active' : ''}
          aria-label="Quote"
        >
          <Quote size={16} />
        </button>
        <button
          type="button"
          onClick={promptForLink}
          className={editor.isActive('link') ? 'active' : ''}
          aria-label="Link"
        >
          <LinkIcon size={16} />
        </button>
        <label aria-label="Upload image">
          <ImagePlus size={16} />
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={(event) => void uploadImage(event.target.files?.[0])}
          />
        </label>
        <button type="button" onClick={() => editor.chain().focus().undo().run()} aria-label="Undo">
          <Undo2 size={16} />
        </button>
      </div>
      <EditorContent editor={editor} />
    </div>
  )
}
