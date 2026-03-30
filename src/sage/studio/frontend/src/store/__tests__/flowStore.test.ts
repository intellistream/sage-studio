import { beforeEach, describe, expect, it } from 'vitest'
import { useFlowStore } from '../flowStore'

describe('flowStore', () => {
    beforeEach(() => {
        useFlowStore.setState({
            nodes: [],
            edges: [],
            selectedNode: null,
            reactFlowInstance: null,
            history: [{ nodes: [], edges: [] }],
            historyIndex: 0,
            maxHistorySize: 50,
            currentJobId: null,
            jobStatus: null,
            isPolling: false,
        })
    })

    it('adds node and records history', () => {
        useFlowStore.getState().addNode({ id: 'n1', position: { x: 0, y: 0 }, data: {}, type: 'default' })
        const state = useFlowStore.getState()
        expect(state.nodes).toHaveLength(1)
        expect(state.canUndo()).toBe(true)
    })
})
