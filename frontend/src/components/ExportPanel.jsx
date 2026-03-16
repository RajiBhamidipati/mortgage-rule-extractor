import { Download, Lock, FileSpreadsheet, FileText } from 'lucide-react'
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
    </div>
  )
}
