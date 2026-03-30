import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    Alert,
    Badge,
    Button,
    Card,
    Empty,
    Input,
    List,
    message,
    Select,
    Space,
    Spin,
    Statistic,
    Switch,
    Table,
    Tabs,
    Tag,
    Timeline,
    Typography,
} from 'antd'
import {
    fireVidaTrigger,
    getVidaReflections,
    getVidaStatus,
    getVidaTriggers,
    listVidaMemory,
    recallVidaMemory,
    toggleVidaTrigger,
    type VidaMemoryListResponse,
    type VidaReflectionItem,
    type VidaStatus,
    type VidaTrigger,
} from '../services/api'

const { Text, Paragraph } = Typography

type MemoryLayer = 'working' | 'episodic' | 'semantic'

function formatTimestamp(timestamp?: number): string {
    if (!timestamp || timestamp <= 0) {
        return '暂无'
    }
    return new Date(timestamp * 1000).toLocaleString()
}

function formatDuration(seconds?: number): string {
    if (!seconds || seconds <= 0) {
        return '0s'
    }
    if (seconds < 60) {
        return `${Math.floor(seconds)}s`
    }
    const min = Math.floor(seconds / 60)
    const sec = Math.floor(seconds % 60)
    return `${min}m ${sec}s`
}

export default function VidaAgentPanel() {
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState<VidaStatus | null>(null)
    const [triggers, setTriggers] = useState<VidaTrigger[]>([])
    const [reflections, setReflections] = useState<VidaReflectionItem[]>([])

    const [memoryLayer, setMemoryLayer] = useState<MemoryLayer>('working')
    const [memoryQuery, setMemoryQuery] = useState('')
    const [memoryPage, setMemoryPage] = useState(1)
    const [memoryPageSize, setMemoryPageSize] = useState(10)
    const [memoryList, setMemoryList] = useState<VidaMemoryListResponse | null>(null)
    const [memorySearching, setMemorySearching] = useState(false)
    const [memorySearchResults, setMemorySearchResults] = useState<Array<Record<string, any>>>([])

    const refreshStatus = useCallback(async () => {
        const [statusRes, triggerRes, reflectionRes] = await Promise.all([
            getVidaStatus(),
            getVidaTriggers(),
            getVidaReflections(20),
        ])
        setStatus(statusRes)
        setTriggers(triggerRes)
        setReflections(reflectionRes)
    }, [])

    const loadMemoryList = useCallback(async (layer: MemoryLayer, page: number, pageSize: number) => {
        const result = await listVidaMemory(layer, page, pageSize)
        setMemoryList(result)
    }, [])

    useEffect(() => {
        const bootstrap = async () => {
            try {
                await Promise.all([
                    refreshStatus(),
                    loadMemoryList(memoryLayer, memoryPage, memoryPageSize),
                ])
            } catch (error) {
                message.error(`加载 VIDA 面板失败: ${error instanceof Error ? error.message : '未知错误'}`)
            } finally {
                setLoading(false)
            }
        }
        bootstrap()
    }, [loadMemoryList, memoryLayer, memoryPage, memoryPageSize, refreshStatus])

    useEffect(() => {
        const timer = window.setInterval(() => {
            refreshStatus().catch(() => undefined)
        }, 5000)
        return () => window.clearInterval(timer)
    }, [refreshStatus])

    const handleToggleTrigger = async (trigger: VidaTrigger, enabled: boolean) => {
        try {
            await toggleVidaTrigger(trigger.name, enabled)
            setTriggers((prev) => prev.map((item) => (
                item.name === trigger.name ? { ...item, enabled } : item
            )))
            message.success(`${trigger.name} 已${enabled ? '启用' : '禁用'}`)
        } catch (error) {
            message.error(`触发器切换失败: ${error instanceof Error ? error.message : '未知错误'}`)
        }
    }

    const handleManualTrigger = async (trigger: VidaTrigger) => {
        try {
            const result = await fireVidaTrigger(trigger.name)
            if (result.result_ok) {
                message.success(`触发成功: ${trigger.name}`)
            } else {
                message.warning(`触发器返回失败: ${result.error || '无错误信息'}`)
            }
            await refreshStatus()
        } catch (error) {
            message.error(`手动触发失败: ${error instanceof Error ? error.message : '未知错误'}`)
        }
    }

    const handleSearchMemory = async () => {
        if (!memoryQuery.trim()) {
            message.warning('请输入检索关键词')
            return
        }
        setMemorySearching(true)
        try {
            const result = await recallVidaMemory(memoryQuery.trim(), 10, memoryLayer)
            const layerResults = result.results[memoryLayer] || []
            setMemorySearchResults(layerResults)
        } catch (error) {
            message.error(`记忆检索失败: ${error instanceof Error ? error.message : '未知错误'}`)
        } finally {
            setMemorySearching(false)
        }
    }

    const memoryColumns = useMemo(() => [
        {
            title: '内容',
            dataIndex: 'text',
            key: 'text',
            render: (_: unknown, record: Record<string, any>) => (
                <Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ marginBottom: 0 }}>
                    {String(record.text || record.content || JSON.stringify(record))}
                </Paragraph>
            ),
        },
        {
            title: '元数据',
            dataIndex: 'metadata',
            key: 'metadata',
            width: 280,
            render: (value: unknown) => (
                <Text type="secondary">
                    {JSON.stringify(value || {})}
                </Text>
            ),
        },
    ], [])

    const semanticNodeTags = useMemo(() => {
        if (!memoryList || memoryLayer !== 'semantic') {
            return []
        }
        return memoryList.items
            .map((item) => String(item.text || item.content || '').trim())
            .filter((item) => Boolean(item))
            .slice(0, 16)
    }, [memoryList, memoryLayer])

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <Spin size="large" />
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto p-4 bg-[--gemini-main-bg]">
            {!status && (
                <Alert
                    type="warning"
                    message="VIDA 运行时不可用"
                    description="请先在后端启用 VIDA 运行时后再查看 Agent 状态。"
                    showIcon
                    className="mb-4"
                />
            )}

            <Card title="Agent 状态" className="mb-4">
                <Space size={24} wrap>
                    <Statistic
                        title="运行状态"
                        value={status?.state === 'running' ? '运行中' : '已停止'}
                        prefix={(
                            <Badge
                                status={status?.state === 'running' ? (status.accepting ? 'success' : 'processing') : 'error'}
                            />
                        )}
                    />
                    <Statistic title="任务队列深度" value={status?.queue_depth ?? 0} />
                    <Statistic title="累计处理" value={status?.processed_count ?? 0} />
                    <Statistic title="累计失败" value={status?.failed_count ?? 0} />
                    <Statistic title="运行时长" value={formatDuration(status?.uptime_seconds)} />
                    <Statistic title="上次反思" value={formatTimestamp(status?.last_reflect_timestamp)} />
                </Space>

                <div className="mt-4 flex gap-3 flex-wrap">
                    <Tag color="blue">Working {status?.memory_usage?.working_count ?? 0}/20</Tag>
                    <Tag color="gold">Episodic {status?.memory_usage?.episodic_count ?? 0} 条</Tag>
                    <Tag color="purple">Semantic {status?.memory_usage?.semantic_count ?? 0} 节点</Tag>
                </div>
            </Card>

            <Tabs
                items={[
                    {
                        key: 'memory',
                        label: '记忆浏览',
                        children: (
                            <div>
                                <Space className="mb-3" wrap>
                                    <Select<MemoryLayer>
                                        value={memoryLayer}
                                        onChange={(value) => {
                                            setMemoryLayer(value)
                                            setMemoryPage(1)
                                            setMemorySearchResults([])
                                            loadMemoryList(value, 1, memoryPageSize).catch(() => undefined)
                                        }}
                                        options={[
                                            { value: 'working', label: 'Working' },
                                            { value: 'episodic', label: 'Episodic' },
                                            { value: 'semantic', label: 'Semantic' },
                                        ]}
                                        style={{ width: 140 }}
                                    />
                                    <Input
                                        placeholder="输入检索关键词"
                                        value={memoryQuery}
                                        onChange={(event) => setMemoryQuery(event.target.value)}
                                        style={{ width: 300 }}
                                        onPressEnter={handleSearchMemory}
                                    />
                                    <Button loading={memorySearching} onClick={handleSearchMemory}>
                                        recall()
                                    </Button>
                                </Space>

                                {memorySearchResults.length > 0 && (
                                    <Card size="small" title="检索结果" className="mb-3">
                                        <List
                                            dataSource={memorySearchResults}
                                            renderItem={(item) => (
                                                <List.Item>
                                                    <div>
                                                        <Paragraph style={{ marginBottom: 4 }}>
                                                            {String(item.text || item.content || JSON.stringify(item))}
                                                        </Paragraph>
                                                        <Text type="secondary">{JSON.stringify(item.metadata || {})}</Text>
                                                    </div>
                                                </List.Item>
                                            )}
                                        />
                                    </Card>
                                )}

                                <Table
                                    rowKey={(record, idx) => String(record.id || record.data_id || idx)}
                                    dataSource={memoryList?.items || []}
                                    columns={memoryColumns}
                                    pagination={{
                                        current: memoryPage,
                                        pageSize: memoryPageSize,
                                        total: memoryList?.total || 0,
                                        onChange: (page, pageSize) => {
                                            const finalSize = pageSize || memoryPageSize
                                            setMemoryPage(page)
                                            setMemoryPageSize(finalSize)
                                            loadMemoryList(memoryLayer, page, finalSize).catch(() => undefined)
                                        },
                                    }}
                                />

                                {memoryLayer === 'episodic' && (
                                    <Card size="small" title="情节记忆时间轴" className="mt-3">
                                        {(memoryList?.items || []).length === 0 ? (
                                            <Empty description="暂无情节记忆" />
                                        ) : (
                                            <Timeline
                                                items={(memoryList?.items || []).map((item) => ({
                                                    label: formatTimestamp(item?.metadata?.timestamp),
                                                    children: String(item.text || item.content || ''),
                                                }))}
                                            />
                                        )}
                                    </Card>
                                )}

                                {memoryLayer === 'semantic' && (
                                    <Card size="small" title="语义记忆图谱（简要）" className="mt-3">
                                        {semanticNodeTags.length === 0 ? (
                                            <Empty description="暂无语义节点" />
                                        ) : (
                                            <div className="flex gap-2 flex-wrap">
                                                {semanticNodeTags.map((node) => (
                                                    <Tag key={node}>{node}</Tag>
                                                ))}
                                            </div>
                                        )}
                                    </Card>
                                )}
                            </div>
                        ),
                    },
                    {
                        key: 'triggers',
                        label: '触发器控制',
                        children: (
                            <List
                                locale={{ emptyText: '暂无已注册触发器' }}
                                dataSource={triggers}
                                renderItem={(trigger) => (
                                    <List.Item
                                        actions={[
                                            <Switch
                                                key="switch"
                                                checked={trigger.enabled}
                                                onChange={(enabled) => handleToggleTrigger(trigger, enabled)}
                                            />,
                                            <Button
                                                key="manual"
                                                type="primary"
                                                onClick={() => handleManualTrigger(trigger)}
                                            >
                                                手动触发
                                            </Button>,
                                        ]}
                                    >
                                        <List.Item.Meta
                                            title={trigger.name}
                                            description={<Tag>{trigger.type}</Tag>}
                                        />
                                    </List.Item>
                                )}
                            />
                        ),
                    },
                    {
                        key: 'reflections',
                        label: '反思日志',
                        children: (
                            reflections.length === 0 ? (
                                <Empty description="暂无反思日志" />
                            ) : (
                                <Timeline
                                    items={reflections.map((item, index) => ({
                                        key: `${item.timestamp}-${index}`,
                                        label: formatTimestamp(item.timestamp),
                                        children: (
                                            <div>
                                                <Paragraph style={{ marginBottom: 8 }}>{item.summary}</Paragraph>
                                                <Space wrap>
                                                    {(item.insights || []).slice(0, 4).map((insight) => (
                                                        <Tag color="geekblue" key={insight}>{insight}</Tag>
                                                    ))}
                                                </Space>
                                            </div>
                                        ),
                                    }))}
                                />
                            )
                        ),
                    },
                ]}
            />
        </div>
    )
}
