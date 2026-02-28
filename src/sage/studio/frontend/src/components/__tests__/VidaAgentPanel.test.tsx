import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import VidaAgentPanel from '../VidaAgentPanel'

const apiMocks = vi.hoisted(() => ({
    getVidaStatus: vi.fn(),
    getVidaTriggers: vi.fn(),
    getVidaReflections: vi.fn(),
    listVidaMemory: vi.fn(),
    recallVidaMemory: vi.fn(),
    toggleVidaTrigger: vi.fn(),
    fireVidaTrigger: vi.fn(),
}))

vi.mock('../../services/api', () => ({
    ...apiMocks,
}))

describe('VidaAgentPanel', () => {
    beforeEach(() => {
        vi.clearAllMocks()

        apiMocks.getVidaStatus.mockResolvedValue({
            state: 'running',
            accepting: true,
            queue_depth: 2,
            processed_count: 10,
            failed_count: 1,
            uptime_seconds: 12,
            trigger_names: ['heartbeat'],
            disabled_trigger_names: [],
            last_reflect_timestamp: 1700000000,
            memory_usage: {
                working_count: 5,
                episodic_count: 3,
                semantic_count: 2,
            },
        })
        apiMocks.getVidaTriggers.mockResolvedValue([
            { name: 'heartbeat', type: 'interval', enabled: true },
        ])
        apiMocks.getVidaReflections.mockResolvedValue([
            { timestamp: 1700000000, summary: 's1', insights: ['i1'] },
        ])
        apiMocks.listVidaMemory.mockResolvedValue({
            layer: 'working',
            page: 1,
            page_size: 10,
            total: 1,
            items: [{ id: 'w1', text: 'working memory item', metadata: { role: 'user' } }],
        })
        apiMocks.recallVidaMemory.mockResolvedValue({
            query: 'hello',
            top_k: 10,
            layer: 'working',
            results: {
                working: [{ text: 'matched memory', metadata: {} }],
            },
        })
        apiMocks.toggleVidaTrigger.mockResolvedValue({ name: 'heartbeat', enabled: false })
        apiMocks.fireVidaTrigger.mockResolvedValue({
            trigger_name: 'heartbeat',
            result_ok: true,
            message_id: 'm1',
            answer: 'ok',
            error: '',
        })
    })

    it('loads panel data and renders trigger/reflection tabs', async () => {
        render(<VidaAgentPanel />)

        await waitFor(() => {
            expect(apiMocks.getVidaStatus).toHaveBeenCalled()
            expect(apiMocks.getVidaTriggers).toHaveBeenCalled()
            expect(apiMocks.listVidaMemory).toHaveBeenCalledWith('working', 1, 10)
        })

        expect(screen.getByText('Agent 状态')).toBeInTheDocument()

        fireEvent.click(screen.getByRole('tab', { name: '触发器控制' }))
        await waitFor(() => {
            expect(screen.getByText('heartbeat')).toBeInTheDocument()
        })

        fireEvent.click(screen.getByRole('tab', { name: '记忆浏览' }))

        fireEvent.click(screen.getByRole('tab', { name: '反思日志' }))
        await waitFor(() => {
            expect(screen.getByText('s1')).toBeInTheDocument()
        })
    })
})
