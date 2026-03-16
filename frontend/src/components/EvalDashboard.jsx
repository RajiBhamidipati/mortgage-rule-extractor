import { useState } from 'react'
import clsx from 'clsx'
import { BarChart3, Target, Search, FileCheck, Info, ChevronDown, ChevronUp } from 'lucide-react'

const RAG_COLORS = {
  green: { bg: 'bg-green-100', text: 'text-green-800', ring: 'ring-green-500', dot: 'bg-green-500' },
  amber: { bg: 'bg-amber-100', text: 'text-amber-800', ring: 'ring-amber-500', dot: 'bg-amber-500' },
  red: { bg: 'bg-red-100', text: 'text-red-800', ring: 'ring-red-500', dot: 'bg-red-500' },
}

export default function EvalDashboard({ evalReport, onRunEval, loading }) {
  if (!evalReport) {
    return (
      <div className="space-y-3">
        <div className="border rounded-lg p-6 text-center space-y-3">
          <BarChart3 className="h-10 w-10 text-gray-300 mx-auto" />
          <p className="text-gray-500 text-sm">No evaluation run yet</p>
          <button
            onClick={onRunEval}
            disabled={loading}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Running...' : 'Run Evaluation'}
          </button>
        </div>
        <EvalInfoPanel />
      </div>
    )
  }

  const rag = RAG_COLORS[evalReport.rag_status] || RAG_COLORS.red

  return (
    <div className="border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Evaluation</h2>
        <button
          onClick={onRunEval}
          disabled={loading}
          className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Running...' : 'Re-run'}
        </button>
      </div>

      {/* EQS Score — the hero metric */}
      <div className={clsx('rounded-lg p-4 text-center ring-2', rag.bg, rag.ring)}>
        <div className="flex items-center justify-center gap-2 mb-1">
          <div className={clsx('h-3 w-3 rounded-full', rag.dot)} />
          <span className={clsx('text-sm font-medium uppercase', rag.text)}>
            {evalReport.rag_status}
          </span>
        </div>
        <div className={clsx('text-4xl font-bold', rag.text)}>
          {evalReport.eqs}
        </div>
        <div className="text-sm text-gray-500 mt-1">Extraction Quality Score</div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard
          icon={<Target className="h-4 w-4" />}
          label="Precision"
          value={`${(evalReport.precision * 100).toFixed(1)}%`}
          detail={`${evalReport.true_positives} correct of ${evalReport.total_extracted} extracted`}
        />
        <MetricCard
          icon={<Search className="h-4 w-4" />}
          label="Recall"
          value={`${(evalReport.recall * 100).toFixed(1)}%`}
          detail={`${evalReport.true_positives} found of ${evalReport.total_golden} expected`}
        />
        <MetricCard
          icon={<BarChart3 className="h-4 w-4" />}
          label="F1 Score"
          value={`${(evalReport.f1 * 100).toFixed(1)}%`}
          detail="Harmonic mean of P & R"
        />
        <MetricCard
          icon={<FileCheck className="h-4 w-4" />}
          label="Source Fidelity"
          value={`${(evalReport.source_fidelity * 100).toFixed(1)}%`}
          detail="Quotes verified in document"
        />
      </div>

      {/* Missed/Extra rules */}
      {evalReport.missed_rules?.length > 0 && (
        <div className="text-xs">
          <p className="font-medium text-red-600 mb-1">Missed Rules ({evalReport.false_negatives}):</p>
          <div className="flex flex-wrap gap-1">
            {evalReport.missed_rules.map((r, i) => (
              <span key={i} className="bg-red-50 text-red-700 px-2 py-0.5 rounded font-mono">{r}</span>
            ))}
          </div>
        </div>
      )}
      {evalReport.extra_rules?.length > 0 && (
        <div className="text-xs">
          <p className="font-medium text-amber-600 mb-1">Extra Rules ({evalReport.false_positives}):</p>
          <div className="flex flex-wrap gap-1">
            {evalReport.extra_rules.map((r, i) => (
              <span key={i} className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded font-mono">{r}</span>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-gray-400 text-center">
        POC Gate: F1 ≥ 80%, EQS ≥ 80, Source Fidelity ≥ 90%
      </p>
    </div>
  )
}

function MetricCard({ icon, label, value, detail }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="flex items-center gap-1 text-gray-500 mb-1">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="text-xl font-bold text-gray-800">{value}</div>
      <div className="text-xs text-gray-400">{detail}</div>
    </div>
  )
}

function EvalInfoPanel() {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-slate-800"
      >
        <Info className="h-3.5 w-3.5 shrink-0" />
        <span className="flex-1">What is evaluation?</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs text-slate-600 leading-relaxed space-y-1.5 border-t border-slate-200 pt-2">
          <p>Evaluation compares extracted rules against a <strong>golden dataset</strong> — a hand-verified set of rules that should be found in this document.</p>
          <p><strong>Precision</strong> — Of the rules extracted, how many are correct? Low precision means the AI is inventing rules.</p>
          <p><strong>Recall</strong> — Of the expected rules, how many were found? Low recall means the AI is missing rules.</p>
          <p><strong>F1 Score</strong> — The balance between precision and recall. The POC target is F1 ≥ 80%.</p>
          <p><strong>Source Fidelity</strong> — What percentage of source quotes were verified in the document. Target ≥ 90%.</p>
          <p><strong>EQS</strong> — The overall Extraction Quality Score combining all metrics. Green ≥ 80, Amber ≥ 60, Red &lt; 60.</p>
        </div>
      )}
    </div>
  )
}
