import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import VidaStatusCard from '../VidaStatusCard'
import type { VidaStatus } from '../../services/api'

describe('VidaStatusCard', () => {
    it('renders running state and memory usage', () => {
        const status: VidaStatus = {
            state: 'running',
            accepting: true,
            queue_depth: 3,
            processed_count: 10,
            failed_count: 1,
            uptime_seconds: 12.5,
            trigger_names: ['heartbeat'],
            last_reflect_timestamp: 1700000000,
            memory_usage: {
                working_count: 7,
                episodic_count: 21,
                semantic_count: 8,
            },
        }

        render(<VidaStatusCard status={status} />)

        expect(screen.getByText('VIDA Agent')).toBeInTheDocument()
        expect(screen.getByText('running')).toBeInTheDocument()
        expect(screen.getByText('3')).toBeInTheDocument()
        expect(screen.getByText('W 7/20')).toBeInTheDocument()
        expect(screen.getByText('E 21')).toBeInTheDocument()
        expect(screen.getByText('S 8')).toBeInTheDocument()
    })

    it('renders idle state when running but not accepting', () => {
        const status: VidaStatus = {
            state: 'running',
            accepting: false,
            queue_depth: 0,
            processed_count: 0,
            failed_count: 0,
            uptime_seconds: 0,
            trigger_names: [],
            memory_usage: {
                working_count: 0,
                episodic_count: 0,
                semantic_count: 0,
            },
        }

        render(<VidaStatusCard status={status} />)

        expect(screen.getByText('idle')).toBeInTheDocument()
        expect(screen.getByText('W 0/20')).toBeInTheDocument()
        expect(screen.getByText('E 0')).toBeInTheDocument()
        expect(screen.getByText('S 0')).toBeInTheDocument()
    })

    it('renders stopped fallback values', () => {
        const status: VidaStatus = {
            state: 'stopped',
            accepting: false,
            queue_depth: 0,
            processed_count: 0,
            failed_count: 0,
            uptime_seconds: 0,
            trigger_names: [],
        }

        render(<VidaStatusCard status={status} />)

        expect(screen.getByText('stopped')).toBeInTheDocument()
        expect(screen.getByText('暂无')).toBeInTheDocument()
        expect(screen.getByText('W 0/20')).toBeInTheDocument()
        expect(screen.getByText('E 0')).toBeInTheDocument()
        expect(screen.getByText('S 0')).toBeInTheDocument()
    })
})
