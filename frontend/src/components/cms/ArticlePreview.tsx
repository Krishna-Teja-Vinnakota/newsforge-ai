import type { CmsArticle } from '@/types/cms'

type ArticlePreviewProps = { article: Pick<CmsArticle, 'title' | 'dek' | 'content_html' | 'topic' | 'hero_url'>; onClose: () => void }

export function ArticlePreview({ article, onClose }: ArticlePreviewProps) {
  return <div className="preview-overlay" role="dialog" aria-modal="true" aria-label="Article preview"><div className="preview-modal"><button className="preview-close" onClick={onClose}>Close preview</button><p className="eyebrow"><span /> {article.topic}</p><h1>{article.title || 'Untitled story'}</h1><p className="preview-dek">{article.dek}</p>{article.hero_url && <img className="preview-hero" src={article.hero_url} alt=""/>}<article className="preview-content" dangerouslySetInnerHTML={{ __html: article.content_html || '<p>Start writing to preview the story.</p>' }} /></div></div>
}
