/**
 * SAGE Studio API Client
 *
 * 与 Phase 1 后端 API 通信的服务层
 */

import axios from 'axios'
import type { Node } from 'reactflow'
import { parseSSEV2Chunk } from './sseProtocol'

// API 基础 URL
// 开发模式: 使用 Vite 代理 /api -> 后端端口（由 VITE_BACKEND_PORT 配置）
// 生产模式: 直接请求 Gateway（同域或通过环境变量配置）
const getApiBaseUrl = (): string => {
    // 如果有环境变量配置，优先使用
    if (import.meta.env.VITE_API_BASE_URL) {
        return import.meta.env.VITE_API_BASE_URL
    }
    // 生产模式下，假设 Gateway 与前端同域（通过反向代理）
    // 或者前端与 Gateway 在同一台机器上
    if (import.meta.env.PROD) {
        // 使用相对路径，依赖反向代理或同域部署
        // 如果前端和 Gateway 分离，需要配置 VITE_API_BASE_URL
        return '/api'
    }
    // 开发模式使用代理
    return '/api'
}

const API_BASE_URL = getApiBaseUrl()

// Helper function to get auth token for fetch requests
function getAuthToken(): string | null {
    try {
        const storage = localStorage.getItem('sage-auth-storage')
        if (storage) {
            const { state } = JSON.parse(storage)
            return state?.token || null
        }
    } catch (e) {
        // Ignore parsing errors
    }
    return null
}

// Helper function to get headers with auth token for fetch requests
function getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
    }
    const token = getAuthToken()
    if (token) {
        headers['Authorization'] = `Bearer ${token}`
    }
    return headers
}

// Axios 实例
const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 120000, // 120秒，适应 LLM 调用和 RAG 流程
    headers: {
        'Content-Type': 'application/json',
    },
})

// Auth Interceptor
apiClient.interceptors.request.use((config) => {
    const token = getAuthToken()
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            window.dispatchEvent(new CustomEvent('auth:unauthorized'))
        }
        return Promise.reject(error)
    }
)

// ==================== 类型定义 ====================

// Auth Types
export interface User {
    id: number
    username: string
    created_at: string
    is_guest?: boolean
}

export interface LoginCredentials {
    username: string
    password: string
}

export interface RegisterCredentials {
    username: string
    password: string
}

export interface TokenResponse {
    access_token: string
    token_type: string
}

// 参数配置接口
export interface ParameterConfig {
    name: string
    label: string
    type: 'text' | 'textarea' | 'number' | 'select' | 'password' | 'json'
    required?: boolean
    defaultValue?: any
    placeholder?: string
    description?: string
    options?: string[]
    min?: number
    max?: number
    step?: number
}

export interface NodeDefinition {
    id: number
    name: string
    description: string
    code: string
    isCustom: boolean
    parameters?: ParameterConfig[]  // 节点参数配置
}

export interface FlowConfig {
    name: string
    description?: string
    nodes: Array<{
        id: string
        type: string
        position: { x: number; y: number }
        data: any
    }>
    edges: Array<{
        id: string
        source: string
        target: string
        sourceHandle?: string
        targetHandle?: string
    }>
}

export interface Job {
    jobId: string
    name: string
    isRunning: boolean
    nthreads: string
    cpu: string
    ram: string
    startTime: string
    duration: string
    nevents: number
    minProcessTime: number
    maxProcessTime: number
    meanProcessTime: number
    latency: number
    throughput: number
    ncore: number
    periodicalThroughput: number[]
    periodicalLatency: number[]
    totalTimeBreakdown: {
        totalTime: number
        serializeTime: number
        persistTime: number
        streamProcessTime: number
        overheadTime: number
    }
    schedulerTimeBreakdown: {
        overheadTime: number
        streamTime: number
        totalTime: number
        txnTime: number
    }
    operators: Array<{
        id: number
        name: string
        numOfInstances: number
        downstream: number[]
        [key: string]: any
    }>
}

export interface JobStatus {
    job_id: string
    status: 'idle' | 'running' | 'stopped' | 'error'
    use_ray: boolean
    isRunning: boolean
}

export interface JobLogs {
    offset: number
    lines: string[]
}

// ==================== API 方法 ====================

// Auth API
export const login = async (credentials: LoginCredentials): Promise<TokenResponse> => {
    const params = new URLSearchParams()
    params.append('username', credentials.username)
    params.append('password', credentials.password)
    const response = await apiClient.post<TokenResponse>('/auth/login', params, {
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    })
    return response.data
}

export const loginGuest = async (): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/guest')
    return response.data
}

export const logout = async (): Promise<void> => {
    await apiClient.post('/auth/logout')
}

export const register = async (credentials: RegisterCredentials): Promise<User> => {
    const response = await apiClient.post<User>('/auth/register', credentials)
    return response.data
}

export const getCurrentUser = async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me')
    return response.data
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<{ status: string; service: string }> {
    const response = await apiClient.get('/health')
    return response.data
}

/**
 * 获取所有可用节点定义
 */
export async function getNodes(): Promise<NodeDefinition[]> {
    const response = await apiClient.get('/operators')
    return response.data
}

/**
 * 获取节点列表（分页）
 */
export async function getNodesList(
    page: number = 1,
    size: number = 10,
    search: string = ''
): Promise<{ items: NodeDefinition[]; total: number }> {
    const response = await apiClient.get('/operators/list', {
        params: { page, size, search },
    })
    return response.data
}

/**
 * 提交流程配置
 */
export async function submitFlow(flowConfig: FlowConfig): Promise<{
    status: string
    message: string
    pipeline_id: string
    file_path: string
}> {
    const response = await apiClient.post('/pipeline/submit', flowConfig)
    return response.data
}

/**
 * 获取所有作业
 */
export async function getAllJobs(): Promise<Job[]> {
    const response = await apiClient.get('/jobs/all')
    return response.data
}

/**
 * 获取作业详情
 */
export async function getJobDetail(jobId: string): Promise<Job> {
    const response = await apiClient.get(`/jobInfo/get/${jobId}`)
    return response.data
}

/**
 * 获取作业状态
 */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
    const response = await apiClient.get(`/signal/status/${jobId}`)
    return response.data
}

/**
 * 启动作业
 */
export async function startJob(jobId: string): Promise<{
    status: string
    message: string
}> {
    const response = await apiClient.post(`/signal/start/${jobId}`)
    return response.data
}

/**
 * 停止作业
 */
export async function stopJob(
    jobId: string,
    duration: string = '00:00:00'
): Promise<{
    status: string
    message: string
}> {
    const response = await apiClient.post(`/signal/stop/${jobId}/${duration}`)
    return response.data
}

/**
 * 获取作业日志（增量）
 */
export async function getJobLogs(
    jobId: string,
    offset: number = 0
): Promise<JobLogs> {
    const response = await apiClient.get(`/signal/sink/${jobId}`, {
        params: { offset },
    })
    return response.data
}

/**
 * 获取管道配置
 */
export async function getPipelineConfig(pipelineId: string): Promise<{
    config: string
}> {
    const response = await apiClient.get(`/jobInfo/config/${pipelineId}`)
    return response.data
}

/**
 * 更新管道配置
 */
export async function updatePipelineConfig(
    pipelineId: string,
    config: string
): Promise<{
    status: string
    message: string
    file_path: string
}> {
    const response = await apiClient.put(`/jobInfo/config/update/${pipelineId}`, {
        config,
    })
    return response.data
}

/**
 * Playground 执行接口
 */
export async function executePlayground(params: {
    flowId: string
    input: string
    sessionId: string
    stream?: boolean
}): Promise<{
    output: string
    status: string
    agentSteps?: Array<{
        step: number
        type: 'reasoning' | 'tool_call' | 'response'
        content: string
        timestamp: string
        duration?: number
        toolName?: string
        toolInput?: any
        toolOutput?: any
    }>
}> {
    const response = await apiClient.post('/playground/execute', params)
    return response.data
}

// ==================== 节点输出 ====================

/**
 * 获取节点的输出数据
 */
export async function getNodeOutput(flowId: string, nodeId: string): Promise<{
    data: any
    type: 'json' | 'text' | 'error'
    timestamp: string
}> {
    const response = await apiClient.get(`/node/${flowId}/${nodeId}/output`)
    return response.data
}

// ==================== Flow 导入/导出 ====================

/**
 * 导出 Flow 为 JSON
 */
export async function exportFlow(flowId: string): Promise<Blob> {
    const response = await apiClient.get(`/flows/${flowId}/export`, {
        responseType: 'blob',
    })
    return response.data
}

/**
 * 导入 Flow
 */
export async function importFlow(file: File): Promise<{ flowId: string; name: string }> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await apiClient.post('/flows/import', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    })
    return response.data
}

// ==================== 环境变量 ====================

/**
 * 获取所有环境变量
 */
export async function getEnvVars(): Promise<Record<string, string>> {
    const response = await apiClient.get('/env')
    return response.data
}

/**
 * 更新环境变量
 */
export async function updateEnvVars(vars: Record<string, string>): Promise<void> {
    await apiClient.put('/env', vars)
}

// ==================== 日志 ====================

/**
 * 获取流程执行日志（增量获取）
 */
export async function getLogs(flowId: string, lastId: number = 0): Promise<{
    logs: Array<{
        id: number
        timestamp: string
        level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG'
        message: string
        nodeId?: string
    }>
    last_id: number
}> {
    const response = await apiClient.get(`/logs/${flowId}`, {
        params: { last_id: lastId }
    })
    return response.data
}

// ==================== Chat API (OpenAI-compatible) ====================

export interface ChatMessageDTO {
    role: 'user' | 'assistant' | 'system'
    content: string
    timestamp: string
    metadata?: Record<string, any>
}

export interface ChatSessionSummary {
    id: string
    title: string
    created_at: string
    last_active: string
    message_count: number
}

export interface ChatSessionDetail extends ChatSessionSummary {
    messages: ChatMessageDTO[]
    metadata?: Record<string, any>
}

export interface PipelineRecommendation {
    success: boolean
    visual_pipeline: {
        name: string
        description: string
        nodes: Node[]
        connections: Array<{
            id: string
            source: string
            target: string
            type?: string
            animated?: boolean
        }>
    }
    raw_plan?: any
    message: string
    error?: string
}

// ==================== Multi-Agent SSE 类型定义 ====================

/**
 * Agent 步骤类型 (与 Task 5 文档对齐)
 */
export type AgentStepType =
    | 'reasoning'
    | 'routing'
    | 'retrieval'
    | 'tool_call'
    | 'tool_result'
    | 'response'

/**
 * Agent 步骤状态
 */
export type AgentStepStatus = 'pending' | 'running' | 'completed' | 'failed'

/**
 * Agent 步骤数据结构 (Multi-Agent 架构核心类型)
 *
 * 用于表示 AgentOrchestrator 返回的每个推理/工具调用步骤
 */
export interface AgentStep {
    id: string
    type: AgentStepType
    content: string
    status: AgentStepStatus
    timestamp: number  // Unix timestamp (ms)
    metadata?: {
        tool_name?: string      // 工具名称 (type='tool_call' 时)
        tool_input?: unknown    // 工具输入参数
        tool_output?: unknown   // 工具输出结果 (type='tool_result' 时)
        confidence?: number     // 置信度 (0-1)
        duration_ms?: number    // 执行耗时 (ms)
        agent_name?: string     // 执行该步骤的 Agent 名称
        error_message?: string  // 错误信息
        [key: string]: unknown
    }
}

/**
 * SSE 事件类型枚举 (与后端 AgentOrchestrator 协议对齐)
 */
export type SSEEventType =
    | 'step'              // Agent 步骤事件
    | 'step_update'       // 步骤状态更新
    | 'step_content'      // 步骤内容追加（流式）
    | 'message'           // 最终消息内容块
    | 'reasoning_end'     // 推理阶段结束
    | 'error'             // 错误事件
    | 'done'              // 完成

/**
 * SSE 步骤事件 (新增 Agent 步骤)
 */
export interface SSEStepEvent {
    type: 'step'
    data: AgentStep
}

/**
 * SSE 步骤更新事件
 */
export interface SSEStepUpdateEvent {
    type: 'step_update'
    step_id: string
    updates: Partial<Pick<AgentStep, 'content' | 'status'> & {
        duration_ms?: number
    }>
}

/**
 * SSE 步骤内容追加事件 (流式内容)
 */
export interface SSEStepContentEvent {
    type: 'step_content'
    step_id: string
    content: string
}

/**
 * SSE 消息内容事件 (最终回复)
 */
export interface SSEMessageEvent {
    type: 'message'
    content: string
}

/**
 * SSE 错误事件
 */
export interface SSEErrorEvent {
    type: 'error'
    error: {
        code: string
        message: string
        details?: unknown
    }
}

/**
 * 所有 SSE 事件联合类型
 */
export type SSEEvent =
    | SSEStepEvent
    | SSEStepUpdateEvent
    | SSEStepContentEvent
    | SSEMessageEvent
    | SSEErrorEvent
    | { type: 'reasoning_end' }
    | { type: 'done' }

// ==================== 旧版推理步骤类型 (兼容) ====================

/**
 * 推理步骤事件类型 (旧版，保持向后兼容)
 */
export interface ReasoningStepEvent {
    type: 'reasoning_step'
    step: {
        id: string
        type: 'thinking' | 'retrieval' | 'workflow' | 'analysis' | 'conclusion' | 'tool_call'
        title: string
        content: string
        status: 'pending' | 'running' | 'completed' | 'error'
        timestamp: string
        duration?: number
        metadata?: Record<string, unknown>
    }
}

/**
 * 推理步骤更新事件 (旧版)
 */
export interface ReasoningStepUpdateEvent {
    type: 'reasoning_step_update'
    step_id: string
    updates: {
        content?: string
        status?: 'pending' | 'running' | 'completed' | 'error'
        duration?: number
    }
}

/**
 * 推理内容追加事件 (旧版)
 */
export interface ReasoningContentEvent {
    type: 'reasoning_content'
    step_id: string
    content: string
}

/**
 * 推理阶段结束事件 (旧版)
 */
export interface ReasoningEndEvent {
    type: 'reasoning_end'
}

// ==================== 回调接口定义 ====================

/**
 * 聊天消息回调集合 (旧版，保持兼容)
 */
export interface ChatMessageCallbacks {
    onChunk: (chunk: string) => void
    onError: (error: Error) => void
    onComplete: () => void
    onMetrics?: (metrics: Record<string, unknown>) => void
    onReasoningStep?: (step: ReasoningStepEvent['step']) => void
    onReasoningStepUpdate?: (stepId: string, updates: ReasoningStepUpdateEvent['updates']) => void
    onReasoningContent?: (stepId: string, content: string) => void
    onReasoningEnd?: () => void
}

/**
 * Multi-Agent 聊天回调集合 (新版，Task 5 规范)
 *
 * 用于处理 AgentOrchestrator 返回的流式事件
 */
export interface MultiAgentChatCallbacks {
    /** 收到新的 Agent 步骤 */
    onStep: (step: AgentStep) => void
    /** 步骤状态更新 */
    onStepUpdate?: (stepId: string, updates: SSEStepUpdateEvent['updates']) => void
    /** 步骤内容追加（流式） */
    onStepContent?: (stepId: string, content: string) => void
    /** 收到最终回复内容块 */
    onContent: (chunk: string) => void
    /** 推理阶段结束 */
    onReasoningEnd?: () => void
    /** 发生错误 */
    onError: (error: Error) => void
    /** 全部完成 */
    onComplete: () => void
}

/**
 * Human-readable label for a pipeline step_type string.
 * Used when constructing a ReasoningStep from a backend SSE 'step' event.
 */
function _stepTitle(stepType: string): string {
    const labels: Record<string, string> = {
        thinking: 'Thinking',
        routing: 'Routing',
        retrieval: 'Retrieval',
        tool_call: 'Tool',
        response: 'Response',
        analysis: 'Analysis',
        reasoning: 'Reasoning',
    }
    return labels[stepType] ?? stepType
}

/**
 * 发送聊天消息（SSE 流式响应）
 * 支持推理步骤事件 (兼容旧版回调)
 *
 * @param message - 用户消息内容
 * @param sessionId - 会话 ID
 * @param onChunk - 收到内容块的回调
 * @param onError - 错误回调
 * @param onComplete - 完成回调
 * @param callbacks - 可选的扩展回调（旧版推理步骤）
 */
export async function sendChatMessage(
    message: string,
    sessionId: string,
    onChunk: (chunk: string) => void,
    onError: (error: Error) => void,
    onComplete: () => void,
    callbacks?: Partial<ChatMessageCallbacks>,
    model?: string
): Promise<AbortController> {
    const controller = new AbortController()
    // Safety timeout: if no data arrives for 120s, abort the stream
    const STALL_TIMEOUT_MS = 120_000
    let stallTimer: ReturnType<typeof setTimeout> | null = null

    const drainSSEFrames = (input: string): { frames: string[]; rest: string } => {
        const frames: string[] = []
        let remaining = input

        while (true) {
            const match = remaining.match(/\r\n\r\n|\n\n/)
            if (!match || match.index === undefined) {
                break
            }

            const boundaryIndex = match.index
            const delimiterLength = match[0].length
            frames.push(remaining.slice(0, boundaryIndex + delimiterLength))
            remaining = remaining.slice(boundaryIndex + delimiterLength)
        }

        return { frames, rest: remaining }
    }

    try {
        // model may be empty — the backend can auto-resolve from gateway
        const modelName = model || ''

        const response = await fetch(`${API_BASE_URL}/chat/v1/chat/completions`, {
            method: 'POST',
            headers: getAuthHeaders(),
            signal: controller.signal,
            body: JSON.stringify({
                model: modelName,
                messages: [{ role: 'user', content: message }],
                session_id: sessionId,
                stream: true,
            }),
        })

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
            throw new Error('ReadableStream not supported')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        const resetStallTimer = () => {
            if (stallTimer) clearTimeout(stallTimer)
            stallTimer = setTimeout(() => {
                console.warn('[SSE] Stream stalled for', STALL_TIMEOUT_MS / 1000, 's — aborting')
                controller.abort()
            }, STALL_TIMEOUT_MS)
        }

        resetStallTimer()

        try {
            while (true) {
                const { done, value } = await reader.read()

                if (done) {
                    onComplete()
                    break
                }

                resetStallTimer()

                buffer += decoder.decode(value, { stream: true })

                const { frames, rest } = drainSSEFrames(buffer)
                buffer = rest
                if (frames.length === 0) {
                    continue
                }

                const events = parseSSEV2Chunk(frames.join(''))

                for (const { payload } of events) {
                    if (payload.type === 'done') {
                        onComplete()
                        if (stallTimer) clearTimeout(stallTimer)
                        return controller
                    }

                    if (payload.type === 'error') {
                        onError(new Error(payload.error || 'chat_stream_error'))
                        if (stallTimer) clearTimeout(stallTimer)
                        return controller
                    }

                    if (payload.type === 'delta') {
                        if (payload.content) {
                            onChunk(payload.content)
                        }
                        if (payload.metrics && callbacks?.onMetrics) {
                            callbacks.onMetrics(payload.metrics)
                        }
                    }

                    // 'step' → NEW reasoning step: create it via onReasoningStep
                    if (payload.type === 'step' && payload.step_id) {
                        if (callbacks?.onReasoningStep) {
                            callbacks.onReasoningStep({
                                id: payload.step_id,
                                type: (payload.step_type || payload.step_id) as any,
                                title: _stepTitle(payload.step_type || payload.step_id || ''),
                                content: payload.content || '',
                                status: 'running',
                                timestamp: new Date().toISOString(),
                            })
                        }
                    }

                    // 'step_update' → UPDATE an existing step (status change or partial content)
                    if (payload.type === 'step_update' && payload.step_id && callbacks?.onReasoningStepUpdate) {
                        callbacks.onReasoningStepUpdate(payload.step_id, {
                            content: payload.content,
                            status: payload.status === 'failed' ? 'error' : payload.status as any,
                        })
                    }

                    if (payload.type === 'meta' && payload.status === 'stream_end' && callbacks?.onReasoningEnd) {
                        callbacks.onReasoningEnd()
                    }
                }
            }
        } finally {
            if (stallTimer) clearTimeout(stallTimer)
        }
    } catch (error) {
        if (stallTimer) clearTimeout(stallTimer)
        if (controller.signal.aborted) {
            onComplete()
        } else {
            onError(error instanceof Error ? error : new Error(String(error)))
        }
    }

    return controller
}

/**
 * 发送聊天消息到 Multi-Agent 后端（SSE 流式响应）
 *
 * 支持 Task 5 规范的新 SSE 事件格式：
 * - event: step + data: AgentStep JSON
 * - event: step_update + data: {step_id, updates}
 * - event: step_content + data: {step_id, content}
 * - event: message + data: 内容块
 * - event: reasoning_end
 * - event: error + data: 错误信息
 * - data: [DONE]
 *
 * 同时兼容旧版纯 data: 格式
 *
 * @param message - 用户消息内容
 * @param sessionId - 会话 ID
 * @param callbacks - Multi-Agent 回调集合
 * @param options - 可选配置
 */
export async function sendChatMessageWithAgent(
    message: string,
    sessionId: string,
    callbacks: MultiAgentChatCallbacks,
    options?: {
        model?: string
        enableReasoning?: boolean
        systemPrompt?: string
    }
): Promise<void> {
    const { onStep, onStepUpdate, onStepContent, onContent, onReasoningEnd, onError, onComplete } = callbacks

    const drainSSEFrames = (input: string): { frames: string[]; rest: string } => {
        const frames: string[] = []
        let remaining = input

        while (true) {
            const match = remaining.match(/\r\n\r\n|\n\n/)
            if (!match || match.index === undefined) {
                break
            }

            const boundaryIndex = match.index
            const delimiterLength = match[0].length
            frames.push(remaining.slice(0, boundaryIndex + delimiterLength))
            remaining = remaining.slice(boundaryIndex + delimiterLength)
        }

        return { frames, rest: remaining }
    }

    try {
        const response = await fetch(`${API_BASE_URL}/chat/v1/chat/completions`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                model: options?.model,
                messages: [
                    ...(options?.systemPrompt ? [{ role: 'system', content: options.systemPrompt }] : []),
                    { role: 'user', content: message }
                ],
                session_id: sessionId,
                stream: true,
                // Multi-Agent 特定选项
                enable_reasoning: options?.enableReasoning ?? true,
            }),
        })

        if (!response.ok) {
            const errorText = await response.text()
            throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
            throw new Error('ReadableStream not supported')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()

            if (done) {
                onComplete()
                break
            }

            buffer += decoder.decode(value, { stream: true })

            const { frames, rest } = drainSSEFrames(buffer)
            buffer = rest
            if (frames.length === 0) {
                continue
            }

            const events = parseSSEV2Chunk(frames.join(''))

            for (const { payload } of events) {
                if (payload.type === 'done') {
                    onComplete()
                    return
                }

                if (payload.type === 'error') {
                    throw new Error(payload.error || 'chat_stream_error')
                }

                if (payload.type === 'step') {
                    onStep({
                        id: payload.step_id || crypto.randomUUID(),
                        type: (payload.step_type as AgentStepType) || 'reasoning',
                        content: payload.content || '',
                        status: (payload.status as AgentStepStatus) || 'running',
                        timestamp: Date.now(),
                    })
                    continue
                }

                if (payload.type === 'step_update' && payload.step_id && onStepUpdate) {
                    onStepUpdate(payload.step_id, {
                        content: payload.content,
                        status: payload.status as any,
                    })
                    continue
                }

                if (payload.type === 'delta' && payload.content) {
                    onContent(payload.content)
                    if (payload.step_id && onStepContent) {
                        onStepContent(payload.step_id, payload.content)
                    }
                    continue
                }

                if (payload.type === 'meta' && payload.status === 'stream_end') {
                    if (onReasoningEnd) {
                        onReasoningEnd()
                    }
                }
            }
        }
    } catch (error) {
        onError(error instanceof Error ? error : new Error(String(error)))
    }
}

/**
 * 获取所有聊天会话
 */
export async function getChatSessions(): Promise<ChatSessionSummary[]> {
    const response = await apiClient.get('/chat/sessions')
    // Backend returns plain array []; Gateway returns {sessions: [...], stats: {...}}
    const data = response.data
    if (Array.isArray(data)) return data
    if (Array.isArray(data?.sessions)) return data.sessions
    return []
}

export async function createChatSession(title?: string): Promise<ChatSessionDetail> {
    const response = await apiClient.post('/chat/sessions', { title })
    return response.data
}

export async function getChatSessionDetail(sessionId: string): Promise<ChatSessionDetail> {
    const response = await apiClient.get(`/chat/sessions/${sessionId}`)
    return response.data
}

export async function clearChatSession(sessionId: string): Promise<void> {
    await apiClient.post(`/chat/sessions/${sessionId}/clear`)
}

export async function updateChatSessionTitle(sessionId: string, title: string): Promise<ChatSessionSummary> {
    const response = await apiClient.patch(`/chat/sessions/${sessionId}/title`, { title })
    return response.data
}

/**
 * 删除聊天会话
 */
export async function deleteChatSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/chat/sessions/${sessionId}`)
}

export async function convertChatSessionToPipeline(sessionId: string): Promise<PipelineRecommendation> {
    const response = await apiClient.post('/chat/generate-workflow', {
        user_input: '根据我们的对话历史生成工作流',
        session_id: sessionId,
        enable_optimization: false,
    })
    return response.data
}

// ==================== 文件上传 API ====================

export interface FileMetadata {
    file_id: string
    filename: string
    original_name: string
    file_type: string
    size_bytes: number
    upload_time: string  // ISO format
    path: string
    indexed: boolean
}

export const uploadFile = async (file: File): Promise<FileMetadata> => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await apiClient.post<FileMetadata>('/uploads', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    })
    return response.data
}

export const listFiles = async (): Promise<FileMetadata[]> => {
    const response = await apiClient.get<FileMetadata[]>('/uploads')
    return response.data
}

export const deleteFile = async (fileId: string): Promise<void> => {
    await apiClient.delete(`/uploads/${fileId}`)
}

// ==================== 记忆 API ====================

export interface MemoryConfig {
    enabled: boolean
    backends: string[]
    short_term: { max_items: number }
    long_term: { enabled: boolean }
}

export interface MemoryStats {
    short_term_count: number
    long_term_count: number
    available: boolean
}

export interface VidaMemoryUsage {
    working_count: number
    episodic_count: number
    semantic_count: number
}

export interface VidaStatus {
    state: 'running' | 'stopped'
    accepting: boolean
    queue_depth: number
    processed_count: number
    failed_count: number
    uptime_seconds: number
    trigger_names: string[]
    disabled_trigger_names?: string[]
    last_reflect_timestamp?: number
    memory_usage?: VidaMemoryUsage
}

export interface VidaTrigger {
    name: string
    type: string
    enabled: boolean
}

export interface VidaReflectionItem {
    timestamp: number
    summary: string
    insights: string[]
}

export interface VidaMemoryRecallResponse {
    query: string
    top_k: number
    layer: string
    results: Record<string, Array<Record<string, any>>>
}

export interface VidaMemoryListResponse {
    layer: 'working' | 'episodic' | 'semantic'
    page: number
    page_size: number
    total: number
    items: Array<Record<string, any>>
}

export const getMemoryConfig = async (): Promise<MemoryConfig> => {
    const response = await apiClient.get<MemoryConfig>('/studio/memory/config')
    return response.data
}

export const getMemoryStats = async (sessionId: string): Promise<MemoryStats> => {
    const response = await apiClient.get<MemoryStats>('/chat/memory/stats', {
        params: { session_id: sessionId },
    })
    return response.data
}

export const getVidaStatus = async (): Promise<VidaStatus> => {
    const response = await apiClient.get<VidaStatus>('/vida/admin/status')
    return response.data
}

export const getVidaTriggers = async (): Promise<VidaTrigger[]> => {
    const response = await apiClient.get<{ triggers: VidaTrigger[] }>('/vida/admin/triggers')
    return response.data.triggers || []
}

export const toggleVidaTrigger = async (name: string, enabled: boolean): Promise<VidaTrigger> => {
    const response = await apiClient.post<VidaTrigger>(`/vida/admin/triggers/${name}/toggle`, { enabled })
    return response.data
}

export const fireVidaTrigger = async (
    name: string,
    payload: Record<string, any> = {}
): Promise<{ trigger_name: string; result_ok: boolean; message_id: string; answer: string; error: string }> => {
    const response = await apiClient.post(`/vida/admin/trigger/${name}`, { payload })
    return response.data
}

export const getVidaReflections = async (limit = 20): Promise<VidaReflectionItem[]> => {
    const response = await apiClient.get<{ items: VidaReflectionItem[] }>('/vida/admin/reflections', {
        params: { limit },
    })
    return response.data.items || []
}

export const recallVidaMemory = async (
    query: string,
    topK = 10,
    layer: 'all' | 'working' | 'episodic' | 'semantic' = 'all'
): Promise<VidaMemoryRecallResponse> => {
    const response = await apiClient.get<VidaMemoryRecallResponse>('/vida/memory/recall', {
        params: {
            query,
            top_k: topK,
            layer,
        },
    })
    return response.data
}

export const listVidaMemory = async (
    layer: 'working' | 'episodic' | 'semantic',
    page = 1,
    pageSize = 20
): Promise<VidaMemoryListResponse> => {
    const response = await apiClient.get<VidaMemoryListResponse>('/vida/memory/list', {
        params: {
            layer,
            page,
            page_size: pageSize,
        },
    })
    return response.data
}

// ==================== 错误处理 ====================

// 添加响应拦截器处理错误
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response) {
            // 服务器返回错误状态码
            console.error('API Error:', error.response.data)
            throw new Error(error.response.data.detail || '请求失败')
        } else if (error.request) {
            // 请求已发送但没有收到响应
            console.error('Network Error:', error.request)
            throw new Error('网络错误：无法连接到服务器')
        } else {
            // 其他错误
            console.error('Error:', error.message)
            throw error
        }
    }
)

// ==================== LLM 状态 API ====================

export interface LLMStatus {
    running: boolean
    healthy: boolean
    service_type: 'gateway' | 'local_sagellm' | 'remote_api' | 'not_configured' | 'unknown' | 'error'
    model_name: string
    base_url: string
    is_local: boolean
    details?: {
        model_id: string
        max_model_len: number
        owned_by: string
    }
    available_models?: Array<{
        name: string
        base_url: string
        is_local: boolean
        description?: string
        healthy?: boolean
        engine_type?: string  // 推理引擎类型（sageLLM）
        device?: string  // 设备类型（CPU/CUDA/Ascend）
    }>
    embedding_models?: Array<{
        name: string
        base_url: string
        is_local: boolean
        description?: string
        healthy?: boolean
        engine_type?: string
        device?: string
    }>
    error?: string
}

export async function getLLMStatus(): Promise<LLMStatus> {
    const response = await apiClient.get('/llm/status')
    return response.data
}

export async function selectLLMModel(modelName: string, baseUrl: string): Promise<void> {
    await apiClient.post('/llm/select', { model_name: modelName, base_url: baseUrl })
}

export default apiClient
