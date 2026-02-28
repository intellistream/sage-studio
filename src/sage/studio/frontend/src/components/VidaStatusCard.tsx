import type { VidaStatus } from '../services/api'

interface VidaStatusCardProps {
    status: VidaStatus | null
    className?: string
}

export default function VidaStatusCard({ status, className = '' }: VidaStatusCardProps) {
    const running = status?.state === 'running'
    const accepting = Boolean(status?.accepting)
    const indicatorClass = running
        ? (accepting ? 'bg-emerald-500' : 'bg-amber-500')
        : 'bg-rose-500'

    const lastReflectText = (() => {
        if (!status?.last_reflect_timestamp || status.last_reflect_timestamp <= 0) {
            return '暂无'
        }
        return new Date(status.last_reflect_timestamp * 1000).toLocaleTimeString()
    })()

    return (
        <div className={`rounded-2xl border border-[--gemini-border] bg-[--gemini-main-bg] p-3 ${className}`}>
            <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-semibold text-[--gemini-text-secondary]">VIDA Agent</div>
                <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${indicatorClass}`} />
                    <span className="text-xs text-[--gemini-text-secondary]">
                        {running ? (accepting ? 'running' : 'idle') : 'stopped'}
                    </span>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-xl bg-[--gemini-sidebar-bg] px-2 py-1.5">
                    <div className="text-[--gemini-text-secondary]">队列</div>
                    <div className="text-[--gemini-text-primary] font-medium">{status?.queue_depth ?? 0}</div>
                </div>
                <div className="rounded-xl bg-[--gemini-sidebar-bg] px-2 py-1.5">
                    <div className="text-[--gemini-text-secondary]">上次反思</div>
                    <div className="text-[--gemini-text-primary] font-medium">{lastReflectText}</div>
                </div>
            </div>

            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                <span className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300">
                    W {status?.memory_usage?.working_count ?? 0}/20
                </span>
                <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
                    E {status?.memory_usage?.episodic_count ?? 0}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-300">
                    S {status?.memory_usage?.semantic_count ?? 0}
                </span>
            </div>
        </div>
    )
}
