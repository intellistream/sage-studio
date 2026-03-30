import { describe, expect, it } from 'vitest'
import {
    parseSSEV2Chunk,
    validateSSEEventOrder,
    sendChatMessage,
    sendChatMessageWithAgent,
} from '../chat'

describe('chat api exports', () => {
    it('exposes sse parser and chat functions', () => {
        expect(typeof parseSSEV2Chunk).toBe('function')
        expect(typeof validateSSEEventOrder).toBe('function')
        expect(typeof sendChatMessage).toBe('function')
        expect(typeof sendChatMessageWithAgent).toBe('function')
    })
})
