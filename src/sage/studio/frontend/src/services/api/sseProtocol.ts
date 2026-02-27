export type ChatSSEEventKind = 'meta' | 'step' | 'step_update' | 'delta' | 'done' | 'error'

export interface ChatSSEEnvelope {
    type: ChatSSEEventKind
    session_id?: string
    message_id?: string
    content?: string
    step_id?: string
    step_type?: string
    status?: string
    error?: string
    metrics?: Record<string, unknown>
}

export interface ParsedSSEEvent {
    event: string
    payload: ChatSSEEnvelope
}

export function parseSSEV2Chunk(chunk: string): ParsedSSEEvent[] {
    const normalized = chunk.replace(/\r\n/g, '\n')
    const blocks = normalized.split('\n\n').filter(Boolean)
    const events: ParsedSSEEvent[] = []

    for (const block of blocks) {
        const lines = block.split('\n')
        let event = ''
        const dataLines: string[] = []

        for (const line of lines) {
            if (line.startsWith('event:')) {
                event = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trim())
            }
        }

        if (dataLines.length === 0) {
            continue
        }

        const raw = dataLines.join('\n')
        const normalizedEvent = event || 'chat.v2'
        if (normalizedEvent !== 'chat.v2') {
            continue
        }

        if (raw === '[DONE]') {
            events.push({ event: normalizedEvent, payload: { type: 'done' } })
            continue
        }

        try {
            const parsed = JSON.parse(raw) as ChatSSEEnvelope
            if (parsed.type) {
                events.push({ event: normalizedEvent, payload: parsed })
            }
        } catch {
            events.push({ event: normalizedEvent, payload: { type: 'error', error: 'invalid_json' } })
        }
    }

    return events
}

export function validateSSEEventOrder(events: ParsedSSEEvent[]): boolean {
    let seenDone = false
    for (const item of events) {
        if (seenDone) {
            return false
        }
        if (item.payload.type === 'done' || item.payload.type === 'error') {
            seenDone = true
        }
    }
    return true
}
