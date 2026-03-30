import { beforeEach, describe, expect, it } from 'vitest'
import { useChatStore } from '../chatStore'

describe('chatStore', () => {
    beforeEach(() => {
        useChatStore.setState({
            currentSessionId: null,
            sessions: [],
            messages: {},
            currentInput: '',
            isStreaming: false,
            streamingMessageId: null,
            isLoading: false,
        })
    })

    it('adds and appends message content', () => {
        const state = useChatStore.getState()
        state.addMessage('s1', {
            id: 'm1',
            role: 'assistant',
            content: 'hi',
            timestamp: new Date().toISOString(),
        })
        state.appendToMessage('s1', 'm1', ' there')

        const messages = useChatStore.getState().messages.s1
        expect(messages).toHaveLength(1)
        expect(messages[0].content).toBe('hi there')
    })
})
