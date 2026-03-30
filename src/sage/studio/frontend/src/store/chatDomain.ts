import type { ChatSessionSummary } from '../services/api'
import type {
    ReasoningStep,
    ReasoningStepType,
    ReasoningStepStatus,
    ToolCallMetadata,
} from '../components/ReasoningAccordion'

export type { ChatSessionSummary, ReasoningStep, ReasoningStepType, ReasoningStepStatus, ToolCallMetadata }

export interface ChatMessage {
    id: string
    role: 'user' | 'assistant' | 'system'
    content: string
    timestamp: string
    isStreaming?: boolean
    isReasoning?: boolean
    reasoningSteps?: ReasoningStep[]
    metadata?: Record<string, unknown>
}
