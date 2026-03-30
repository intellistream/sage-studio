import { describe, expect, it } from 'vitest'
import { parseSSEV2Chunk, validateSSEEventOrder } from '../sseProtocol'

describe('sseProtocol', () => {
    it('parses chat.v2 payload and done signal', () => {
        const chunk = [
            'event: chat.v2',
            'data: {"type":"delta","content":"hello"}',
            '',
            'event: chat.v2',
            'data: [DONE]',
            '',
        ].join('\n')

        const parsed = parseSSEV2Chunk(chunk)
        expect(parsed).toHaveLength(2)
        expect(parsed[0].payload.type).toBe('delta')
        expect(parsed[1].payload.type).toBe('done')
    })

    it('fails order validation when events appear after done', () => {
        const valid = [{ event: 'chat.v2', payload: { type: 'delta' as const } }, { event: 'chat.v2', payload: { type: 'done' as const } }]
        const invalid = [...valid, { event: 'chat.v2', payload: { type: 'delta' as const } }]

        expect(validateSSEEventOrder(valid)).toBe(true)
        expect(validateSSEEventOrder(invalid)).toBe(false)
    })

    it('ignores non chat.v2 events', () => {
        const chunk = [
            'event: message',
            'data: {"type":"delta","content":"legacy"}',
            '',
            'event: chat.v2',
            'data: {"type":"delta","content":"v2"}',
            '',
        ].join('\n')

        const parsed = parseSSEV2Chunk(chunk)
        expect(parsed).toHaveLength(1)
        expect(parsed[0].payload.content).toBe('v2')
    })

    it('accepts legacy data-only sse blocks', () => {
        const chunk = [
            'data: {"type":"delta","content":"legacy"}',
            '',
            'data: [DONE]',
            '',
        ].join('\n')

        const parsed = parseSSEV2Chunk(chunk)
        expect(parsed).toHaveLength(2)
        expect(parsed[0].payload.type).toBe('delta')
        expect(parsed[0].payload.content).toBe('legacy')
        expect(parsed[1].payload.type).toBe('done')
    })
})
