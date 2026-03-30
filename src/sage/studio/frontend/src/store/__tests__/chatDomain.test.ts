import { describe, expect, it } from 'vitest'
import type { ChatMessage } from '../chatDomain'

describe('chatDomain types', () => {
    it('accepts structured chat message shape', () => {
        const msg: ChatMessage = {
            id: '1',
            role: 'assistant',
            content: 'ok',
            timestamp: new Date().toISOString(),
        }
        expect(msg.role).toBe('assistant')
    })
})
