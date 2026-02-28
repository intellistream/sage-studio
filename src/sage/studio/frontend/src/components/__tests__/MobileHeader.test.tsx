import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import MobileHeader from '../MobileHeader'

// Mock the stores
vi.mock('../store/authStore', () => ({
    useAuthStore: () => ({
        user: { name: 'Test User' },
        logout: vi.fn(),
        isAuthenticated: true,
    }),
}))

// Mock theme store if it exists, otherwise we might need to adjust
vi.mock('../store/themeStore', () => ({
    useThemeStore: () => ({
        resolvedTheme: 'light',
        toggleTheme: vi.fn(),
    }),
}))

describe('MobileHeader', () => {
    const defaultBaseUrl =
        import.meta.env.VITE_LLM_BASE_URL || import.meta.env.VITE_API_BASE_URL || '/api'
    const defaultProps = {
        onMenuClick: vi.fn(),
        onNewChat: vi.fn(),
        llmStatus: {
            model_name: 'test-model',
            running: true,
            healthy: true,
            service_type: 'local_sagellm' as const,
            base_url: defaultBaseUrl,
            is_local: true,
        },
        onSelectModel: vi.fn(),
    }

    it('renders correctly', () => {
        render(<MobileHeader {...defaultProps} />)
        expect(screen.getByRole('button', { name: /select model/i })).toBeInTheDocument()
        expect(screen.getByText('SAGE')).toBeInTheDocument()
    })

    it('calls onMenuClick when menu button is clicked', () => {
        render(<MobileHeader {...defaultProps} />)
        const menuButton = screen.getByRole('button', { name: /menu/i })
        fireEvent.click(menuButton)
        expect(defaultProps.onMenuClick).toHaveBeenCalled()
    })

    it('calls onNewChat when new chat button is clicked', () => {
        render(<MobileHeader {...defaultProps} />)
        const newChatButton = screen.getByRole('button', { name: /new chat/i })
        fireEvent.click(newChatButton)
        expect(defaultProps.onNewChat).toHaveBeenCalled()
    })

    it('opens model menu and selects a model', () => {
        const onSelectModel = vi.fn()
        render(
            <MobileHeader
                {...defaultProps}
                onSelectModel={onSelectModel}
                llmStatus={{
                    ...defaultProps.llmStatus,
                    available_models: [
                        {
                            name: 'test-model',
                            healthy: true,
                            engine_type: 'llm',
                            base_url: '/api',
                            is_local: true,
                            description: 'Local test model',
                        },
                        {
                            name: 'backup-model',
                            healthy: true,
                            engine_type: 'llm',
                            base_url: '/api',
                            is_local: true,
                            description: 'Backup model',
                        },
                    ],
                }}
            />
        )

        fireEvent.click(screen.getByRole('button', { name: /select model/i }))
        expect(screen.getByText('Select Model')).toBeInTheDocument()

        fireEvent.click(screen.getByText('backup-model'))
        expect(onSelectModel).toHaveBeenCalledWith('backup-model', '/api')
    })
})
