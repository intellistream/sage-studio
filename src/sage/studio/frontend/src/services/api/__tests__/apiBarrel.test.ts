import { describe, expect, it } from 'vitest'
import * as api from '../../api'

describe('api barrel exports', () => {
    it('exports transport and domain methods', () => {
        expect(typeof api.login).toBe('function')
        expect(typeof api.getNodes).toBe('function')
        expect(typeof api.sendChatMessage).toBe('function')
        expect(typeof api.uploadFile).toBe('function')
        expect(typeof api.getLLMStatus).toBe('function')
        expect(typeof api.apiClient).toBe('function')
    })
})
