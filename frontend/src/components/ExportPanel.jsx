import { useState } from 'react'
import { Download, Lock, FileSpreadsheet, FileText, Info, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'

export default function ExportPanel({ docId, canExport, blockers, approvedCount }) {
  const handleExport = async (format) => {
    const endpoint = format === 'excel'
      ? `/api/export/excel/${docId}`
      : `/api/export/text/${docId}`

    try {
      const res = await fetch(endpoint)
      if (!res.ok) {
        const data = await res.json()
        alert(data.detail || 'Export failed')
        return
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = format === 'excel'
        ? `rules_export_${docId}.xlsx`
        : `rules_export_${docId}.txt`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Export failed: ' + err.message)
    }
  }

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <h2 className="text-lg font-semibold text-gray-800">Export</h2>

      {!canExport && blockers?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded p-3">
          <div className="flex items-center gap-2 text-red-700 font-medium text-sm mb-2">
            <Lock className="h-4 w-4" />
            Export Blocked
          </div>
          <ul className="text-xs text-red-600 space-y-1">
            {blockers.slice(0, 5).map((b, i) => (
              <li key={i}>• {b}</li>
            ))}
            {blockers.length > 5 && (
              <li>...and {blockers.length - 5} more</li>
            )}
          </ul>
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => handleExport('excel')}
          disabled={!canExport || approvedCount === 0}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded text-sm font-medium',
            canExport && approvedCount > 0
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          )}
        >
          <FileSpreadsheet className="h-4 w-4" />
          Excel Decision Table
        </button>

        <button
          onClick={() => handleExport('text')}
          disabled={!canExport || approvedCount === 0}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded text-sm font-medium',
            canExport && approvedCount > 0
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          )}
        >
          <FileText className="h-4 w-4" />
          NL Statements
        </button>
      </div>

      {approvedCount > 0 && (
        <p className="text-xs text-gray-500">
          {approvedCount} approved rule{approvedCount !== 1 ? 's' : ''} ready for export
        </p>
      )}

      <ExportInfoPanel />
    </div>
  )
}

function ExportInfoPanel() {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-slate-800"
      >
        <Info className="h-3.5 w-3.5 shrink-0" />
        <span className="flex-1">About export formats</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs text-slate-600 leading-relaxed space-y-1.5 border-t border-slate-200 pt-2">
          <p><strong>Excel Decision Table</strong> — A structured spreadsheet with one row per rule. Includes all fields: category, operator, value, conditions, outcomes, and source references. Suitable for importing into lending decision engines.</p>
          <p><strong>NL Statements</strong> — Plain-English rule statements in a text file. Useful for compliance review, documentation, and sharing with non-technical stakeholders.</p>
          <p className="text-slate-500 italic">Export is blocked until guardrails have been run and all flagged rules have been reviewed. Only rules with "approved" status are included in the export.</p>
        </div>
      )}
    </div>
  )
}
