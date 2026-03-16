import { useState, useCallback } from 'react'
import RegulatoryBanner from './components/RegulatoryBanner'
import FileUpload from './components/FileUpload'
import RuleTable from './components/RuleTable'
import EvalDashboard from './components/EvalDashboard'
import ExportPanel from './components/ExportPanel'
import { Loader2, Play, Shield, FileText, Info, ChevronDown, ChevronUp } from 'lucide-react'

function ProgressPanel({ message }) {
  return (
    <div className="mt-3 bg-blue-50 border border-blue-200 rounded-lg p-4 text-left">
      <div className="flex items-start gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-blue-500 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-800">{message}</p>
      </div>
    </div>
  )
}

function InfoPanel({ title, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left text-sm font-medium text-slate-600 hover:text-slate-800"
      >
        <Info className="h-4 w-4 shrink-0" />
        <span className="flex-1">{title}</span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="px-4 pb-3 text-xs text-slate-600 leading-relaxed space-y-2 border-t border-slate-200 pt-3">
          {children}
        </div>
      )}
    </div>
  )
}

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
  const [progressMsg, setProgressMsg] = useState('')

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
    setProgressMsg('Sending document to Claude for analysis...')
    const timer1 = setTimeout(() => setProgressMsg('Claude is reading the document and identifying lending rules...'), 3000)
    const timer2 = setTimeout(() => setProgressMsg('Extracting structured rules — this can take 1–2 minutes for large documents...'), 12000)
    const timer3 = setTimeout(() => setProgressMsg('Still working — building rule definitions, source quotes, and classifications...'), 30000)
    const timer4 = setTimeout(() => setProgressMsg('Nearly there — finalising extraction results...'), 60000)
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
      ;[timer1, timer2, timer3, timer4].forEach(clearTimeout)
      setExtracting(false)
      setProgressMsg('')
    }
  }

  // Step 3: Run guardrails
  const handleGuardrails = async () => {
    setRunningGuardrails(true)
    setProgressMsg('Running hallucination check — verifying source quotes against document...')
    const timer1 = setTimeout(() => setProgressMsg('Running completeness check — scanning for sections with missing rules...'), 5000)
    const timer2 = setTimeout(() => setProgressMsg('Running classification validator — second AI pass to verify categories...'), 12000)
    const timer3 = setTimeout(() => setProgressMsg('Running regulatory bias check — scanning for protected characteristics...'), 25000)
    const timer4 = setTimeout(() => setProgressMsg('Running footnote check and finalising guardrail results...'), 35000)
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
      ;[timer1, timer2, timer3, timer4].forEach(clearTimeout)
      setRunningGuardrails(false)
      setProgressMsg('')
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
              <div className="space-y-3">
                <div className="bg-white border rounded-lg p-6 text-center space-y-3">
                  {!extracting && (
                    <p className="text-gray-600">
                      Document parsed successfully. Ready to extract rules.
                    </p>
                  )}
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
                  {extracting && progressMsg && (
                    <ProgressPanel message={progressMsg} />
                  )}
                </div>
                <InfoPanel title="What does extraction do?">
                  <p>The AI (Claude) reads your mortgage policy document and identifies every lending rule — thresholds, limits, conditions, eligibility criteria, and requirements.</p>
                  <p>Each rule is structured with: the data field being tested (e.g. max LTV), the operator and value, the outcome (Pass/Refer/Decline), and a <strong>verbatim source quote</strong> from the document for traceability.</p>
                  <p>This typically takes 1–2 minutes depending on document size. Longer documents with many tables may take longer.</p>
                </InfoPanel>
              </div>
            )}

            {step === 'extracted' && (
              <div className="space-y-3">
                <div className="bg-white border rounded-lg p-6 text-center space-y-3">
                  {!runningGuardrails && (
                    <p className="text-gray-600">
                      {rules.length} rules extracted. Run guardrails to validate.
                    </p>
                  )}
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
                  {runningGuardrails && progressMsg && (
                    <ProgressPanel message={progressMsg} />
                  )}
                </div>
                <InfoPanel title="What are guardrails and why do they matter?">
                  <p>Guardrails are automated validation checks that catch errors before a human reviewer sees the rules. Five checks run in sequence:</p>
                  <p><strong>1. Hallucination Check</strong> — Verifies every source quote actually exists in the original document. Flags rules where the AI may have invented or paraphrased text.</p>
                  <p><strong>2. Completeness Check</strong> — Scans for document sections that have substantial content but zero extracted rules, which may indicate the AI missed something.</p>
                  <p><strong>3. Classification Validator</strong> — A second AI pass reviews each rule's category (LTV, income, credit, etc.) to catch misclassifications.</p>
                  <p><strong>4. Regulatory Bias Check</strong> — Scans for references to protected characteristics (age, gender, race, etc.) and FCA MCOB keywords. Flags rules that need compliance review.</p>
                  <p><strong>5. Footnote Check</strong> — Links footnote references to their source text and flags any that can't be verified.</p>
                  <p className="text-slate-500 italic">Under the EU AI Act, this system is classified as HIGH RISK. Guardrails are a critical safety layer — no rules can be exported until guardrails have run and flagged rules have been reviewed.</p>
                </InfoPanel>
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
