import fixture from '@/data/news.json'
import type { Story, TrendingStory } from '@/types/news'

/**
 * Phase 1 uses fixture data. Phase 5 replaces this implementation with the
 * HTTP repository while pages continue to call the same methods.
 */
export const newsRepository = {
  getSnapshot: () => fixture,
  getStoryById: (id: string | null): Story | undefined =>
    fixture.stories.find((story) => story.id === id) as Story | undefined,
  getTrending: (): TrendingStory[] => fixture.trending as TrendingStory[],
}
