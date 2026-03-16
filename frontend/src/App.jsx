import { useState, useCallback } from 'react'
import RegulatoryBanner from './components/RegulatoryBanner'
import FileUpload from './components/FileUpload'
import RuleTable from './components/RuleTable'
import EvalDashboard from './components/EvalDashboard'
import ExportPanel from './components/ExportPanel'
import { Loader2, Play, Shield, FileText } from 'lucide-react'

export default function App() {
  const [docId, setDocId] = useState(null)
  const [docInfo, setDocInfo] = useState(null)
  const [rules, setRules] = useState([])
  const [evalReport, setEvalReport] = useState(null)
  const [exportStatus, setExportStatus] = useState(null)

  const [extracting, setExtracting] = useState(false)
  const [runningGuardrails, setRunningGuardrails] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [step, setStep] = useState('upload') // upload | extracted | guardrails | review

  // Fetch latest rules and export status
  const refreshRules = useCallback(async () => {
    if (!docId) return
    const [rulesRes, statusRes] = await Promise.all([
      fetch(`/api/rules/${docId}`),
      fetch(`/api/status/${docId}`),
    ])
    if (rulesRes.ok) {
      const data = await rulesRes.json()
      setRules(data.rules)
    }
    if (statusRes.ok) {
      const data = await statusRes.json()
      setExportStatus(data)
    }
  }, [docId])

  // Step 1: Upload complete
  const handleUploadComplete = (data) => {
    setDocId(data.doc_id)
    setDocInfo(data)
    setStep('uploaded')
    setRules([])
    setEvalReport(null)
    setExportStatus(null)
  }

  // Step 2: Extract rules
  const handleExtract = async () => {
    setExtracting(true)
    try {
      const res = await fetch(`/api/extract/${docId}`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setRules(data.rules)
        setStep('extracted')
      } else {
        const err = await res.json()
        alert('Extraction failed: ' + (err.detail || 'Unknown error'))
      }
    } catch (err) {
      alert('Extraction failed: ' + err.message)
    } finally {
      setExtracting(false)
    }
  }

  // Step 3: Run guardrails
  const handleGuardrails = async () => {
    setRunningGuardrails(true)
    try {
      const res = await fetch(`/api/guardrails/${docId}`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setRules(data.rules)
        setStep('review')
        // Fetch export status
        const statusRes = await fetch(`/api/status/${docId}`)
        if (statusRes.ok) setExportStatus(await statusRes.json())
      }
    } catch (err) {
      alert('Guardrails failed: ' + err.message)
    } finally {
      setRunningGuardrails(false)
    }
  }

  // Run evaluation
  const handleEvaluate = async () => {
    setEvaluating(true)
    try {
      const res = await fetch(`/api/evaluate/${docId}`, { method: 'POST' })
      if (res.ok) {
        setEvalReport(await res.json())
      }
    } catch (err) {
      alert('Evaluation failed: ' + err.message)
    } finally {
      setEvaluating(false)
    }
  }

  const flagCount = rules.filter(
    r => r.status === 'flagged_regulatory' || r.status === 'flagged_uncertain'
  ).length

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Regulatory Banner (F-19) */}
      <RegulatoryBanner flagCount={flagCount} />

      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">
              Mortgage Policy Rule Extractor
            </h1>
            <p className="text-sm text-gray-500">
              AI-powered extraction of structured lending rules from policy documents
            </p>
          </div>
          {docInfo && (
            <div className="text-right text-sm">
              <div className="flex items-center gap-2 text-gray-700">
                <FileText className="h-4 w-4" />
                <span className="font-medium">{docInfo.doc_name}</span>
              </div>
              <span className="text-gray-400">
                {docInfo.section_count} sections | {docInfo.char_count.toLocaleString()} chars
              </span>
            </div>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6">
        <div className="grid grid-cols-[1fr_320px] gap-6">
          {/* Left: Main workflow */}
          <div className="space-y-6">
            {/* Upload */}
            {step === 'upload' && (
              <FileUpload onUploadComplete={handleUploadComplete} />
            )}

            {/* Action buttons */}
            {step === 'uploaded' && (
              <div className="bg-white border rounded-lg p-6 text-center space-y-3">
                <p className="text-gray-600">
                  Document parsed successfully. Ready to extract rules.
                </p>
                <button
                  onClick={handleExtract}
                  disabled={extracting}
                  className="bg-blue-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {extracting ? (
                    <><Loader2 className="h-5 w-5 animate-spin" /> Extracting Rules...</>
                  ) : (
                    <><Play className="h-5 w-5" /> Extract Rules</>
                  )}
                </button>
              </div>
            )}

            {step === 'extracted' && (
              <div className="bg-white border rounded-lg p-6 text-center space-y-3">
                <p className="text-gray-600">
                  {rules.length} rules extracted. Run guardrails to validate.
                </p>
                <button
                  onClick={handleGuardrails}
                  disabled={runningGuardrails}
                  className="bg-amber-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {runningGuardrails ? (
                    <><Loader2 className="h-5 w-5 animate-spin" /> Running Guardrails...</>
                  ) : (
                    <><Shield className="h-5 w-5" /> Run Guardrails</>
                  )}
                </button>
              </div>
            )}

            {/* Rule table */}
            {rules.length > 0 && (
              <RuleTable rules={rules} docId={docId} onRulesUpdate={refreshRules} />
            )}

            {/* Upload another */}
            {step !== 'upload' && (
              <div className="text-center">
                <button
                  onClick={() => {
                    setStep('upload')
                    setDocId(null)
                    setDocInfo(null)
                    setRules([])
                    setEvalReport(null)
                    setExportStatus(null)
                  }}
                  className="text-sm text-gray-500 hover:text-gray-700 underline"
                >
                  Upload a different document
                </button>
              </div>
            )}
          </div>

          {/* Right sidebar: Eval + Export */}
          <div className="space-y-4">
            {docId && (
              <>
                <EvalDashboard
                  evalReport={evalReport}
                  onRunEval={handleEvaluate}
                  loading={evaluating}
                />
                <ExportPanel
                  docId={docId}
                  canExport={exportStatus?.can_export || false}
                  blockers={exportStatus?.blocking_reasons || []}
                  approvedCount={exportStatus?.approved_rules || 0}
                />
              </>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t bg-white px-6 py-3 text-center text-xs text-gray-400">
        Mortgage Policy Rule Extractor — POC v0.1 | EU AI Act: HIGH RISK |
        All outputs require human review and compliance sign-off
      </footer>
    </div>
  )
}
