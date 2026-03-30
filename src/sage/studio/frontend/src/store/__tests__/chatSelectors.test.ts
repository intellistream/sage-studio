import { describe, expect, it } from 'vitest'
import { selectMessagesBySession } from '../chatStore'

describe('chat selectors', () => {
    it('returns empty array for missing session', () => {
        const selector = selectMessagesBySession('missing')
        const selected = selector({
            currentSessionId: null,
            sessions: [],
            messages: {},
            currentInput: '',
            isStreaming: false,
            streamingMessageId: null,
            isLoading: false,
        } as any)

        expect(selected).toEqual([])
    })
})
