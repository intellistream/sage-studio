/**
 * Chat Mode Component - Gemini-style interface for SAGE
 *
 * Design inspired by Google Gemini's clean, modern aesthetic:
 * - Sidebar: #F0F4F9 background with rounded-full hover states
 * - Main area: Pure white (#FFFFFF) with centered content (max-w-[830px])
 * - Floating capsule input bar with focus transitions
 * - User messages: Right-aligned with light grey bubbles
 * - AI messages: Left-aligned, no bubble, clean typography
 *
 * Mobile support:
 * - Drawer-style sidebar
 * - Simplified header
 * - Touch-friendly input area
 */

import React, { useEffect, useRef, useState } from 'react'
import type { Edge, Node } from 'reactflow'
import {
    Tooltip,
    Dropdown,
    Spin,
    message as antMessage,
} from 'antd'
import {
    Send,
    Plus,
    Trash2,
    MessageSquare,
    MoreHorizontal,
    Loader,
    Sparkles,
    ArrowRight,
    PanelLeftClose,
    PanelLeft,
    Mic,
    ChevronDown,
    Square,
} from 'lucide-react'
import { SageIcon } from './SageIcon'
import { useChatStore, type ChatMessage, type ReasoningStep } from '../store/chatStore'
import MessageContent from './MessageContent'
import FileUpload from './FileUpload'
import MobileHeader from './MobileHeader'
import MobileSidebar from './MobileSidebar'
import {
    sendChatMessage,
    getChatSessions,
    deleteChatSession,
    createChatSession,
    getChatSessionDetail,
    clearChatSession as clearSessionApi,
    convertChatSessionToPipeline,
    getLLMStatus,
    selectLLMModel,
    type ChatSessionSummary,
    type LLMStatus,
} from '../services/api'
import { useFlowStore } from '../store/flowStore'
import type { AppMode } from '../App'

// ============================================================================
// Sub-Components
// ============================================================================

/** SAGE Logo Icon for AI messages */
function SageLogo({ className = '' }: { className?: string }) {
    return (
        <div className={`w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center ${className}`}>
            <SageIcon size={16} className="text-white" />
        </div>
    )
}

/** Session list item in sidebar */
function SessionItem({
    session,
    isActive,
    onClick,
    onDelete,
}: {
    session: ChatSessionSummary
    isActive: boolean
    onClick: () => void
    onDelete: () => void
}) {
    return (
        <div
            className={`
                group flex items-center gap-3 px-3 py-2.5 mx-2 rounded-full cursor-pointer
                transition-all duration-200 ease-out
                ${isActive
                    ? 'bg-[#D3E3FD] dark:bg-[#394457] text-[--gemini-text-primary]'
                    : 'hover:bg-[--gemini-hover-bg] text-[--gemini-text-secondary]'
                }
            `}
            onClick={onClick}
        >
            <MessageSquare size={18} className="flex-shrink-0" />
            <span className="flex-1 text-sm truncate font-medium">
                {session.title}
            </span>
            <Dropdown
                menu={{
                    items: [
                        {
                            key: 'delete',
                            label: 'Delete',
                            danger: true,
                            onClick: (e) => {
                                e.domEvent.stopPropagation()
                                onDelete()
                            },
                        },
                    ],
                }}
                trigger={['click']}
            >
                <button
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-[#D3E3FD] dark:hover:bg-[#4a5568] transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                >
                    <MoreHorizontal size={16} />
                </button>
            </Dropdown>
        </div>
    )
}

/** Model selector dropdown in header */
function ModelSelector({
    llmStatus,
    onSelectModel
}: {
    llmStatus: LLMStatus | null
    onSelectModel: (modelName: string, baseUrl: string) => void
}) {
    const allModels = llmStatus?.available_models || []
    const embeddingModels = llmStatus?.embedding_models || []
    const chatModels = allModels.filter(model => model.engine_type !== 'embedding')
    const selectableModels = chatModels.length > 0 ? chatModels : allModels

    const currentModelName = llmStatus?.model_name
    const currentModel = allModels.find(m => m.name === currentModelName)

    const isGatewayService = llmStatus?.service_type === 'gateway'
    const modelName = isGatewayService
        ? 'sageLLM'
        : (currentModel?.name
            ? (currentModel.name.split('/').pop() || currentModel.name.split('__').pop() || 'Unknown')
            : 'sageLLM')

    const isLocal = llmStatus?.is_local
    const isHealthy = Boolean(llmStatus?.healthy || selectableModels.some(model => model.healthy))
    const connectionLabel = llmStatus ? (isHealthy ? 'Connected' : 'Disconnected') : 'Connecting'

    const handleMenuClick = (e: any) => {
        const selectedModel = selectableModels.find(m => m.name === e.key)
        if (selectedModel) {
            onSelectModel(selectedModel.name, selectedModel.base_url)
        }
    }

    const chatModelItems = selectableModels.map(model => {
        const isSelected = model.name === currentModelName

        return {
            key: model.name,
            label: (
                <div className="py-1 flex items-center justify-between min-w-[280px]">
                    <div className="flex-1">
                        <div className={`font-medium flex items-center gap-2 ${
                            isSelected ? 'text-blue-600 dark:text-blue-400' : ''
                        }`}>
                            {model.name}
                            {isSelected && (
                                <span className="text-xs px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 rounded">当前</span>
                            )}
                        </div>
                        <div className="text-xs text-[--gemini-text-secondary] space-y-0.5">
                            <div>{model.description || (model.is_local ? 'Local Model' : 'Cloud Model')}</div>
                            {(model.engine_type || model.device) && (
                                <div className="flex items-center gap-2 text-[11px] mt-0.5">
                                    {model.engine_type && (
                                        <span className="px-1.5 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded">
                                            {model.engine_type}
                                        </span>
                                    )}
                                    {model.device && (
                                        <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">
                                            {model.device}
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                    <div className={`w-2 h-2 rounded-full ml-3 flex-shrink-0 ${model.healthy ? 'bg-green-500' : 'bg-red-400'}`} title={model.healthy ? 'Running' : 'Stopped/Unreachable'} />
                </div>
            ),
        }
    })

    const embeddingItems = embeddingModels.map(model => ({
        key: `embed__${model.name}`,
        disabled: true,
        label: (
            <div className="py-1 flex items-center justify-between min-w-[280px] opacity-80">
                <div className="flex-1">
                    <div className="font-medium text-[--gemini-text-secondary] flex items-center gap-2">
                        {model.name}
                        <span className="text-[10px] px-1.5 py-0.5 bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-300 rounded">embedding</span>
                    </div>
                    <div className="text-xs text-[--gemini-text-secondary]">
                        {model.is_local ? 'Local Embedding Model' : 'Cloud Embedding Model'}
                    </div>
                </div>
                <div className={`w-2 h-2 rounded-full ml-3 flex-shrink-0 ${model.healthy ? 'bg-green-500' : 'bg-red-400'}`} title={model.healthy ? 'Running' : 'Stopped/Unreachable'} />
            </div>
        ),
    }))

    const fallbackItem = [
        {
            key: 'current',
            label: (
                <div className="py-1">
                    <div className="font-medium">{modelName}</div>
                    <div className="text-xs text-[--gemini-text-secondary]">
                        {(isGatewayService ? 'sageLLM Gateway' : (isLocal ? 'Local Model' : 'Cloud Model'))} · {connectionLabel}
                    </div>
                </div>
            ),
            disabled: true,
        },
    ]

    const items = [
        ...(chatModelItems.length > 0 ? chatModelItems : fallbackItem),
        ...(embeddingModels.length > 0 ? [
            { type: 'divider' as const },
            {
                key: '__embed_header__',
                disabled: true,
                label: (
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-[--gemini-text-secondary] px-1 py-0.5">
                        Embedding Models
                    </div>
                ),
            },
            ...embeddingItems,
        ] : []),
    ]

    return (
        <Dropdown
            menu={{
                items,
                onClick: handleMenuClick,
            }}
            trigger={['click']}
        >
            <button className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[--gemini-hover-bg] transition-colors">
                <div className="flex flex-col items-start">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[--gemini-text-primary]">
                            {modelName}
                        </span>
                        {isHealthy && (
                            <span className="w-2 h-2 bg-green-500 rounded-full" />
                        )}
                    </div>
                    {currentModel && (currentModel.engine_type || currentModel.device) && (
                        <div className="flex items-center gap-1.5 text-[10px] mt-0.5">
                            {currentModel.engine_type && (
                                <span className="text-blue-600 dark:text-blue-400">
                                    {currentModel.engine_type}
                                </span>
                            )}
                            {currentModel.engine_type && currentModel.device && (
                                <span className="text-[--gemini-text-secondary]">·</span>
                            )}
                            {currentModel.device && (
                                <span className="text-[--gemini-text-secondary]">
                                    {currentModel.device}
                                </span>
                            )}
                        </div>
                    )}
                </div>
                <ChevronDown size={16} className="text-[--gemini-text-secondary]" />
            </button>
        </Dropdown>
    )
}

/** Floating input bar - Gemini style */
function ChatInput({
    value,
    onChange,
    onSend,
    onStop,
    onUpload,
    disabled,
    isSending,
    isStreaming,
    isMobile = false,
}: {
    value: string
    onChange: (value: string) => void
    onSend: () => void
    onStop?: () => void
    onUpload: () => void
    disabled: boolean
    isSending: boolean
    isStreaming?: boolean
    isMobile?: boolean
}) {
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const [isFocused, setIsFocused] = useState(false)

    // Auto-resize textarea
    useEffect(() => {
        const textarea = textareaRef.current
        if (textarea) {
            textarea.style.height = 'auto'
            textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
        }
    }, [value])

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            if (isStreaming && onStop) {
                onStop()
            } else if (!isSending && !disabled) {
                onSend()
            }
        }
    }

    // Determine if we should show stop button
    const showStop = isStreaming && !!onStop

    return (
        <div className={`w-full mx-auto ${isMobile ? 'px-3 pb-3' : 'max-w-[830px] px-4 pb-6'}`}>
            <div
                className={`
                    relative flex flex-col transition-all duration-200
                    ${isMobile ? 'rounded-[24px]' : 'rounded-[28px]'}
                    ${isFocused
                        ? 'bg-[--gemini-main-bg] shadow-lg ring-1 ring-[--gemini-border]'
                        : 'bg-[--gemini-input-bg]'
                    }
                `}
            >
                {/* Textarea */}
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onFocus={() => setIsFocused(true)}
                    onBlur={() => setIsFocused(false)}
                    placeholder={isStreaming ? "Generating answer..." : "Ask SAGE anything..."}
                    disabled={disabled && !showStop}
                    rows={1}
                    className={`
                        w-full bg-transparent resize-none outline-none
                        text-[--gemini-text-primary] placeholder:text-[--gemini-text-secondary]/60
                        min-h-[24px] max-h-[200px]
                        ${isMobile ? 'px-4 pt-3 pb-2 text-base' : 'px-6 pt-4 pb-2 text-base'}
                    `}
                    style={{ fontSize: '16px' }} // Prevent iOS zoom on focus
                />

                {/* Bottom toolbar */}
                <div className={`flex items-center justify-between ${isMobile ? 'px-2 pb-2' : 'px-3 pb-3'}`}>
                    {/* Left: Upload button */}
                    <div className="flex items-center gap-1">
                        <Tooltip title="Upload files">
                            <button
                                onClick={onUpload}
                                disabled={showStop}
                                className={`rounded-full hover:bg-[--gemini-hover-bg] transition-colors text-[--gemini-text-secondary] ${isMobile ? 'p-2' : 'p-2.5'} ${showStop ? 'opacity-50 cursor-not-allowed' : ''}`}
                            >
                                <Plus size={isMobile ? 18 : 20} />
                            </button>
                        </Tooltip>
                        {!isMobile && (
                            <Tooltip title="Voice input (coming soon)">
                                <button
                                    className="p-2.5 rounded-full hover:bg-[--gemini-hover-bg] transition-colors text-[--gemini-text-secondary] opacity-50 cursor-not-allowed"
                                    disabled
                                >
                                    <Mic size={20} />
                                </button>
                            </Tooltip>
                        )}
                    </div>

                    {/* Right: Send/Stop button */}
                    <button
                        onClick={showStop ? onStop : onSend}
                        disabled={(!value.trim() && !showStop) || (disabled && !showStop)}
                        className={`
                            rounded-full transition-all duration-200
                            ${isMobile ? 'p-2' : 'p-2.5'}
                            ${(value.trim() || showStop) && !(disabled && !showStop)
                                ? 'bg-[--gemini-text-primary] text-[--gemini-main-bg] hover:opacity-80 active:scale-95'
                                : 'bg-[--gemini-border] text-[--gemini-text-secondary]/40 cursor-not-allowed'
                            }
                        `}
                    >
                        {showStop ? (
                            <Square size={isMobile ? 16 : 18} fill="currentColor" />
                        ) : isSending ? (
                            <Loader size={isMobile ? 18 : 20} className="animate-spin" />
                        ) : (
                            <Send size={isMobile ? 18 : 20} />
                        )}
                    </button>
                </div>
            </div>

            {/* Disclaimer - Hide on mobile */}
            {!isMobile && (
                <p className="text-center text-xs text-[--gemini-text-secondary]/70 mt-3">
                    SAGE may display inaccurate info, including about people, so double-check its responses.
                </p>
            )}
        </div>
    )
}

/** Single message bubble */
function MessageBubble({
    message,
    isStreaming,
    streamingMessageId,
}: {
    message: ChatMessage
    isStreaming: boolean
    streamingMessageId: string | null
}) {
    const isUser = message.role === 'user'
    const tokensPerSecond = extractTokensPerSecond(message.metadata)

    if (isUser) {
        // User message: Right-aligned, light grey bubble
        return (
            <div className="flex justify-end mb-6">
                <div className="flex items-start gap-3 max-w-[80%]">
                    <div
                        className={`
                            px-5 py-3 rounded-[20px] rounded-tr-sm
                            bg-[--gemini-user-bubble] text-[--gemini-text-primary]
                        `}
                    >
                        <p className="whitespace-pre-wrap break-words text-base leading-relaxed">
                            {message.content}
                        </p>
                    </div>
                </div>
            </div>
        )
    }

    // AI message: Left-aligned, no bubble, with SAGE logo
    return (
        <div className="flex justify-start mb-8">
            <div className="flex items-start gap-4 max-w-full">
                {/* SAGE Avatar */}
                <SageLogo className="flex-shrink-0 mt-1" />

                {/* Message content */}
                <div className="flex-1 min-w-0">
                    <MessageContent
                        content={message.content}
                        isUser={false}
                        isStreaming={isStreaming && streamingMessageId === message.id}
                        streamingMessageId={streamingMessageId}
                        messageId={message.id}
                        reasoningSteps={message.reasoningSteps}
                        isReasoning={message.isReasoning}
                    />
                    {tokensPerSecond !== null && (
                        <div className="mt-2 text-xs text-[--gemini-text-secondary]">
                            Speed {tokensPerSecond.toFixed(2)} token/s
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

function extractTokensPerSecond(metadata?: Record<string, unknown>): number | null {
    const metricsValue = metadata?.metrics
    if (!metricsValue || typeof metricsValue !== 'object') {
        return null
    }

    return findTokensPerSecond(metricsValue as Record<string, unknown>)
}

function findTokensPerSecond(metrics: Record<string, unknown>): number | null {
    const candidateKeys = ['tokens_per_second', 'token_per_second', 'throughput_tps', 'tps']

    for (const key of candidateKeys) {
        const value = metrics[key]
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value
        }
        if (typeof value === 'string') {
            const parsed = Number.parseFloat(value)
            if (Number.isFinite(parsed)) {
                return parsed
            }
        }
    }

    for (const nested of Object.values(metrics)) {
        if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
            const found = findTokensPerSecond(nested as Record<string, unknown>)
            if (found !== null) {
                return found
            }
        }
    }

    return null
}

/** Empty state when no messages */
function EmptyState() {
    return (
        <div className="flex-1 flex flex-col items-center justify-center min-h-[400px]">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-6">
                <SageIcon size={32} className="text-white" />
            </div>
            <h2 className="text-2xl font-normal text-[--gemini-text-primary] mb-2">
                Hello, how can I help you today?
            </h2>
            <p className="text-[--gemini-text-secondary] text-base">
                Start a conversation with SAGE
            </p>
        </div>
    )
}

// ============================================================================
// Main Component
// ============================================================================

interface ChatModeProps {
    onModeChange?: (mode: AppMode) => void
    isMobile?: boolean
}

export default function ChatMode({ onModeChange, isMobile = false }: ChatModeProps) {
    const {
        currentSessionId,
        sessions,
        messages,
        currentInput,
        isStreaming,
        streamingMessageId,
        isLoading,
        setCurrentSessionId,
        setSessions,
        addSession,
        removeSession,
        addMessage,
        appendToMessage,
        updateMessageMetadata,
        setCurrentInput,
        setIsStreaming,
        setStreamingMessageId,
        setIsLoading,
        clearCurrentSession,
        setMessages,
        updateSessionStats,
        addReasoningStep,
        updateReasoningStep,
        appendToReasoningStep,
        setMessageReasoning,
    } = useChatStore()
    const { setNodes, setEdges } = useFlowStore()

    const messagesEndRef = useRef<HTMLDivElement>(null)
    const abortControllerRef = useRef<AbortController | null>(null)
    const [isSending, setIsSending] = useState(false)
    const [isConverting, setIsConverting] = useState(false)
    const [recommendationSummary, setRecommendationSummary] = useState<string | null>(null)
    const [recommendationInsights, setRecommendationInsights] = useState<string[]>([])
    const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null)
    const [isUploadVisible, setIsUploadVisible] = useState(false)
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
    const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages[currentSessionId || '']])

    useEffect(() => {
        loadSessions()
        loadLLMStatus()
        const interval = setInterval(loadLLMStatus, 10000)
        return () => clearInterval(interval)
    }, [])

    const loadLLMStatus = async () => {
        try {
            const status = await getLLMStatus()
            setLlmStatus(status)
        } catch (error) {
            console.error('Failed to load LLM status:', error)
        }
    }

    const handleModelSelect = async (modelName: string, baseUrl: string) => {
        try {
            // Show loading message
            const hideLoading = antMessage.loading(`切换到模型: ${modelName}...`, 0)

            try {
                await selectLLMModel(modelName, baseUrl)

                // Wait for backend config to update (retry up to 5 times with 1s interval)
                let retries = 5
                let modelNameMatched = false

                while (retries > 0) {
                    await new Promise(resolve => setTimeout(resolve, 1000))
                    const status = await getLLMStatus()

                    // Success: model_name matches (don't require healthy yet)
                    if (status.model_name === modelName) {
                        modelNameMatched = true
                        setLlmStatus(status)
                        hideLoading()

                        const currentModel = status.available_models?.find(m => m.name === modelName)
                        if (currentModel?.healthy) {
                            antMessage.success(`已切换到: ${modelName}`)
                        } else {
                            antMessage.success(`已切换到: ${modelName}（模型启动中...）`)
                        }
                        break
                    }

                    retries--
                }

                // Even if model_name doesn't match yet, force update UI to show the selection
                if (!modelNameMatched) {
                    const finalStatus = await getLLMStatus()
                    // Force update the status to show the selected model
                    finalStatus.model_name = modelName
                    finalStatus.base_url = baseUrl
                    setLlmStatus(finalStatus)

                    hideLoading()
                    antMessage.warning(`模型已配置: ${modelName}（后台加载中...）`)
                }
            } catch (error) {
                hideLoading()
                throw error
            }
        } catch (error) {
            console.error('Failed to switch model:', error)
            antMessage.error('切换模型失败')
        }
    }

    useEffect(() => {
        setRecommendationSummary(null)
        setRecommendationInsights([])
    }, [currentSessionId])

    const loadSessions = async () => {
        try {
            setIsLoading(true)
            const sessionList = await getChatSessions()
            setSessions(sessionList)

            if (!currentSessionId && sessionList.length > 0) {
                setCurrentSessionId(sessionList[0].id)
                await loadSessionMessages(sessionList[0].id)
            }
        } catch (error) {
            console.error('Failed to load sessions:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const loadSessionMessages = async (sessionId: string) => {
        if (!sessionId || sessionId === 'undefined' || sessionId === 'null') {
            console.warn('[ChatMode] loadSessionMessages called with invalid sessionId:', sessionId)
            return
        }
        try {
            const detail = await getChatSessionDetail(sessionId)

            const mappedMessages: ChatMessage[] = detail.messages.map((msg, index) => {
                const reasoningSteps = msg.metadata?.reasoningSteps as ReasoningStep[] | undefined

                return {
                    id: `server_${index}_${msg.timestamp}`,
                    role: msg.role,
                    content: msg.content,
                    timestamp: msg.timestamp,
                    metadata: msg.metadata,
                    reasoningSteps: reasoningSteps,
                    isReasoning: false,
                }
            })
            setMessages(sessionId, mappedMessages)
            updateSessionStats(sessionId, {
                message_count: mappedMessages.length,
                last_active: detail.last_active,
            })
        } catch (error: any) {
            console.error('Failed to load session messages:', error)
            if (error?.response?.status === 404) {
                antMessage.error('Session not found or expired')
                removeSession(sessionId)
            } else {
                antMessage.error('Failed to load messages')
            }
            if (currentSessionId === sessionId) {
                setCurrentSessionId(null)
            }
        }
    }

    const handleSendMessage = async () => {
        if (!currentInput.trim() || isStreaming || isSending) return

        const userMessageContent = currentInput.trim()
        setCurrentInput('')
        setIsSending(true)

        try {
            let sessionId = currentSessionId
            if (!sessionId) {
                const newSession = await createChatSession()
                sessionId = newSession.id
                addSession({
                    id: newSession.id,
                    title: newSession.title,
                    created_at: newSession.created_at,
                    last_active: newSession.last_active,
                    message_count: 0,
                })
                setMessages(sessionId, [])
                setCurrentSessionId(sessionId)
            }

            const userMessage: ChatMessage = {
                id: `msg_${Date.now()}_user`,
                role: 'user',
                content: userMessageContent,
                timestamp: new Date().toISOString(),
            }
            addMessage(sessionId, userMessage)

            const assistantMessageId = `msg_${Date.now()}_assistant`
            const assistantMessage: ChatMessage = {
                id: assistantMessageId,
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                isStreaming: true,
                isReasoning: true,
                reasoningSteps: [],
            }
            addMessage(sessionId, assistantMessage)

            setIsStreaming(true)
            setStreamingMessageId(assistantMessageId)

            // Model resolution: use the polled llmStatus model_name.
            // The backend can also auto-detect from gateway, so model is best-effort here.
            let selectedModel = llmStatus?.model_name || ''

            // If we don't have a model yet (initial load race), do one fresh fetch
            if (!selectedModel) {
                const freshStatus = await getLLMStatus().catch(() => null)
                if (freshStatus) {
                    setLlmStatus(freshStatus)
                    selectedModel = freshStatus.model_name || ''
                }
            }

            const controller = await sendChatMessage(
                userMessageContent,
                sessionId,
                (chunk: string) => {
                    appendToMessage(sessionId, assistantMessageId, chunk)
                },
                (error: Error) => {
                    console.error('Streaming error:', error)
                    antMessage.error(`Failed: ${error.message}`)
                    setIsStreaming(false)
                    setStreamingMessageId(null)
                    setMessageReasoning(sessionId, assistantMessageId, false)
                },
                () => {
                    setIsStreaming(false)
                    setStreamingMessageId(null)
                    setMessageReasoning(sessionId, assistantMessageId, false)

                    // If response completed but message content is still empty, show fallback
                    const currentMessages = useChatStore.getState().messages[sessionId!] || []
                    const assistantMsg = currentMessages.find((m: ChatMessage) => m.id === assistantMessageId)
                    if (assistantMsg && !assistantMsg.content.trim()) {
                        appendToMessage(sessionId!, assistantMessageId, '(No response from model. Please try again.)')
                    }

                    updateSessionStats(sessionId!, {
                        message_count: (messages[sessionId!] || []).length,
                        last_active: new Date().toISOString(),
                    })
                },
                {
                    onReasoningStep: (step) => {
                        addReasoningStep(sessionId, assistantMessageId, step as ReasoningStep)
                    },
                    onReasoningStepUpdate: (stepId, updates) => {
                        updateReasoningStep(sessionId, assistantMessageId, stepId, updates)
                    },
                    onReasoningContent: (stepId, content) => {
                        appendToReasoningStep(sessionId, assistantMessageId, stepId, content)
                    },
                    onReasoningEnd: () => {
                        setMessageReasoning(sessionId, assistantMessageId, false)
                    },
                    onMetrics: (metrics) => {
                        updateMessageMetadata(sessionId, assistantMessageId, { metrics })
                    },
                },
                selectedModel // Pass the selected model with fallback
            )
            abortControllerRef.current = controller
        } catch (error) {
            console.error('Send message error:', error)
            antMessage.error('Failed to send message')
        } finally {
            setIsSending(false)
            abortControllerRef.current = null
        }
    }

    const handleStopGeneration = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort()
            abortControllerRef.current = null
            setIsStreaming(false)
            setStreamingMessageId(null)
            antMessage.info('Generation stopped')
        }
    }

    const handleNewChat = async () => {
        try {
            setIsLoading(true)
            const newSession = await createChatSession()
            addSession({
                id: newSession.id,
                title: newSession.title,
                created_at: newSession.created_at,
                last_active: newSession.last_active,
                message_count: 0,
            })
            setMessages(newSession.id, [])
            setCurrentSessionId(newSession.id)
            setCurrentInput('')
        } catch (error) {
            antMessage.error('Failed to create chat')
        } finally {
            setIsLoading(false)
        }
    }

    const handleDeleteSession = async (sessionId: string) => {
        try {
            await deleteChatSession(sessionId)
            removeSession(sessionId)
            antMessage.success('Chat deleted')
        } catch (error) {
            console.error('Delete session error:', error)
            antMessage.error('Failed to delete chat')
        }
    }

    const handleClearCurrentSession = async () => {
        if (!currentSessionId) return
        try {
            await clearSessionApi(currentSessionId)
            clearCurrentSession()
            antMessage.success('Chat cleared')
        } catch (_error) {
            antMessage.error('Failed to clear chat')
        }
    }

    const handleConvertToPipeline = async () => {
        if (!currentSessionId) return
        setIsConverting(true)
        setRecommendationSummary(null)
        setRecommendationInsights([])
        try {
            const recommendation = await convertChatSessionToPipeline(currentSessionId)

            if (!recommendation.success) {
                throw new Error(recommendation.error || 'Failed to generate workflow')
            }

            const { visual_pipeline } = recommendation

            const edges = visual_pipeline.connections.map((conn) => ({
                id: conn.id,
                source: conn.source,
                target: conn.target,
                type: conn.type || 'smoothstep',
                animated: conn.animated !== false,
            }))

            setNodes(visual_pipeline.nodes as Node[])
            setEdges(edges as Edge[])
            setRecommendationSummary(recommendation.message || visual_pipeline.description)
            setRecommendationInsights([`Workflow: ${visual_pipeline.name}`])
            antMessage.success(`Generated: ${visual_pipeline.name}`)
        } catch (error) {
            console.error('Convert error', error)
            antMessage.error(error instanceof Error ? error.message : 'Cannot generate pipeline')
        } finally {
            setIsConverting(false)
        }
    }

    const currentMessages = messages[currentSessionId || ''] || []

    // Get current session title for mobile header
    const currentSessionTitle = sessions.find(s => s.id === currentSessionId)?.title

    return (
        <div className={`flex bg-[--gemini-main-bg] ${isMobile ? 'flex-col h-full' : 'h-full'}`}>
            {/* ================================================================
                Mobile Header & Sidebar Drawer
            ================================================================ */}
            {isMobile && (
                <>
                    <MobileHeader
                        onMenuClick={() => setMobileSidebarOpen(true)}
                        onNewChat={handleNewChat}
                        title={currentSessionTitle}
                        llmStatus={llmStatus}
                        onSelectModel={handleModelSelect}
                    />
                    <MobileSidebar
                        isOpen={mobileSidebarOpen}
                        onClose={() => setMobileSidebarOpen(false)}
                        sessions={sessions}
                        currentSessionId={currentSessionId}
                        isLoading={isLoading}
                        onSessionClick={(sessionId) => {
                            setCurrentSessionId(sessionId)
                            loadSessionMessages(sessionId)
                        }}
                        onDeleteSession={handleDeleteSession}
                        onNewChat={handleNewChat}
                    />
                </>
            )}

            {/* ================================================================
                Desktop Sidebar - Gemini Style (Hidden on mobile)
            ================================================================ */}
            {!isMobile && (
                <div
                    className={`
                        flex flex-col bg-[--gemini-sidebar-bg] transition-all duration-300 ease-out
                        ${sidebarCollapsed ? 'w-0 overflow-hidden' : 'w-[280px]'}
                    `}
                >
                    {/* New Chat Button */}
                    <div className="p-3">
                        <button
                            onClick={handleNewChat}
                            disabled={isStreaming}
                            className={`
                                flex items-center gap-3 w-full px-4 py-3 rounded-full
                                bg-[--gemini-hover-bg] text-[--gemini-text-secondary] font-medium text-sm
                                hover:bg-[--gemini-main-bg] hover:shadow-md transition-all duration-200
                                disabled:opacity-50 disabled:cursor-not-allowed
                            `}
                        >
                            <Plus size={20} />
                            <span>New chat</span>
                        </button>
                    </div>

                    {/* Session List */}
                    <div className="flex-1 overflow-y-auto gemini-scrollbar py-2">
                        {isLoading ? (
                            <div className="flex justify-center items-center h-32">
                                <Spin />
                            </div>
                        ) : sessions.length === 0 ? (
                            <div className="text-center text-[--gemini-text-secondary]/60 text-sm py-8 px-4">
                                No conversations yet
                            </div>
                        ) : (
                            <div className="space-y-1">
                                {sessions.map((session: ChatSessionSummary) => (
                                    <SessionItem
                                        key={session.id}
                                        session={session}
                                        isActive={currentSessionId === session.id}
                                        onClick={() => {
                                            setCurrentSessionId(session.id)
                                            loadSessionMessages(session.id)
                                        }}
                                        onDelete={() => handleDeleteSession(session.id)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ================================================================
                Main Chat Area
            ================================================================ */}
            <div className={`flex-1 flex flex-col min-w-0 min-h-0 bg-[--gemini-main-bg] ${isMobile ? 'pt-14' : ''}`}>
                {/* Header - Hidden on mobile (MobileHeader is used instead) */}
                {!isMobile && (
                    <header className="sticky top-0 z-10 flex items-center justify-between px-4 py-2 bg-[--gemini-main-bg]/80 backdrop-blur-md border-b border-transparent">
                        <div className="flex items-center gap-2">
                            {/* Sidebar Toggle */}
                            <Tooltip title={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}>
                                <button
                                    onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                                    className="p-2 rounded-full hover:bg-[--gemini-hover-bg] transition-colors text-[--gemini-text-secondary]"
                                >
                                    {sidebarCollapsed ? <PanelLeft size={20} /> : <PanelLeftClose size={20} />}
                                </button>
                            </Tooltip>

                            {/* Model Selector */}
                            <ModelSelector llmStatus={llmStatus} onSelectModel={handleModelSelect} />
                        </div>

                        {/* Right Actions */}
                        <div className="flex items-center gap-1">
                            {currentMessages.length > 0 && (
                                <>
                                    <Tooltip title="Convert to pipeline">
                                        <button
                                            onClick={handleConvertToPipeline}
                                            disabled={isStreaming || isConverting}
                                            className={`
                                            flex items-center gap-2 px-3 py-2 rounded-full text-sm
                                            transition-colors duration-200
                                            ${isConverting
                                                    ? 'bg-[--gemini-border] text-[--gemini-text-secondary]/50'
                                                    : 'hover:bg-[--gemini-hover-bg] text-[--gemini-text-secondary]'
                                                }
                                        `}
                                        >
                                            {isConverting ? (
                                                <Loader size={16} className="animate-spin" />
                                            ) : (
                                                <Sparkles size={16} />
                                            )}
                                            <span className="hidden sm:inline">Convert</span>
                                        </button>
                                    </Tooltip>

                                    <Tooltip title="Clear chat">
                                        <button
                                            onClick={handleClearCurrentSession}
                                            disabled={isStreaming}
                                            className="p-2 rounded-full hover:bg-[--gemini-hover-bg] transition-colors text-[--gemini-text-secondary]"
                                        >
                                            <Trash2 size={18} />
                                        </button>
                                    </Tooltip>
                                </>
                            )}
                        </div>
                    </header>
                )}

                {/* Messages Area */}
                <div
                    className={`flex-1 overflow-y-auto gemini-scrollbar ${isMobile ? 'min-h-0' : ''}`}
                    style={isMobile ? { WebkitOverflowScrolling: 'touch' } : undefined}
                >
                    <div className={`mx-auto px-4 py-6 ${isMobile ? 'max-w-full' : 'max-w-[830px]'}`}>
                        {/* Recommendation Banner */}
                        {recommendationSummary && (
                            <div className="mb-6 p-4 bg-[#E8F0FE] dark:bg-[#394457] rounded-2xl border border-[#D2E3FC] dark:border-[#4a5568]">
                                <p className="text-[--gemini-text-primary] text-sm mb-2">{recommendationSummary}</p>
                                {recommendationInsights.length > 0 && (
                                    <ul className="text-xs text-[--gemini-text-secondary] mb-3">
                                        {recommendationInsights.map((tip) => (
                                            <li key={tip}>• {tip}</li>
                                        ))}
                                    </ul>
                                )}
                                <button
                                    onClick={() => onModeChange?.('canvas')}
                                    className="flex items-center gap-2 text-sm font-medium text-[--gemini-accent] hover:underline"
                                >
                                    Go to Canvas
                                    <ArrowRight size={16} />
                                </button>
                            </div>
                        )}

                        {/* Empty State or Messages */}
                        {currentMessages.length === 0 ? (
                            <EmptyState />
                        ) : (
                            <>
                                {currentMessages.map((msg) => (
                                    <MessageBubble
                                        key={msg.id}
                                        message={msg}
                                        isStreaming={isStreaming}
                                        streamingMessageId={streamingMessageId}
                                    />
                                ))}
                                <div ref={messagesEndRef} />
                            </>
                        )}
                    </div>
                </div>

                {/* Input Area */}
                <div
                    className={`flex-shrink-0 bg-gradient-to-t from-[--gemini-main-bg] via-[--gemini-main-bg] to-transparent ${isMobile ? 'pt-2 px-2' : 'pt-4'}`}
                    style={isMobile ? { paddingBottom: 'max(16px, env(safe-area-inset-bottom))' } : undefined}
                >
                    <ChatInput
                        value={currentInput}
                        onChange={setCurrentInput}
                        onSend={handleSendMessage}
                        onStop={handleStopGeneration}
                        onUpload={() => setIsUploadVisible(true)}
                        disabled={isSending}
                        isSending={isSending}
                        isStreaming={isStreaming}
                        isMobile={isMobile}
                    />
                </div>
            </div>

            {/* File Upload Modal */}
            <FileUpload visible={isUploadVisible} onClose={() => setIsUploadVisible(false)} />
        </div>
    )
}
