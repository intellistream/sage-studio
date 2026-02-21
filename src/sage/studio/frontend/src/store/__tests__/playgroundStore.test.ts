import { beforeEach, describe, expect, it } from 'vitest'
import { usePlaygroundStore } from '../playgroundStore'

describe('playgroundStore', () => {
    beforeEach(() => {
        usePlaygroundStore.setState({
            isOpen: false,
            currentSessionId: 'default',
            sessions: {
                default: {
                    id: 'default',
                    name: 'Default Session',
                    createdAt: new Date(),
                    lastActive: new Date(),
                    messageCount: 0,
                },
            },
            messages: { default: [] },
            isExecuting: false,
            canStop: false,
            currentInput: '',
            showCode: false,
            codeLanguage: 'python',
            generatedCode: '',
        })
    })

    it('creates session and switches current id', () => {
        const id = usePlaygroundStore.getState().createSession('Test Session')
        expect(usePlaygroundStore.getState().currentSessionId).toBe(id)
    })
})
