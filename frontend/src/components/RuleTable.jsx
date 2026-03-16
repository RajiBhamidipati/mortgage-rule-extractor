import { useState } from 'react'
import { Check, X, Edit3, Flag, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'

const STATUS_STYLES = {
  pending_review: 'bg-blue-50 border-blue-200',
  approved: 'bg-green-50 border-green-200',
  rejected: 'bg-red-50 border-red-200',
  flagged_regulatory: 'bg-amber-50 border-amber-200',
  flagged_uncertain: 'bg-yellow-50 border-yellow-200',
}

const STATUS_BADGES = {
  pending_review: { label: 'Pending', color: 'bg-blue-100 text-blue-800' },
  approved: { label: 'Approved', color: 'bg-green-100 text-green-800' },
  rejected: { label: 'Rejected', color: 'bg-red-100 text-red-800' },
  flagged_regulatory: { label: 'Regulatory', color: 'bg-amber-100 text-amber-800' },
  flagged_uncertain: { label: 'Uncertain', color: 'bg-yellow-100 text-yellow-800' },
}

export default function RuleTable({ rules, docId, onRulesUpdate }) {
  const [expandedRule, setExpandedRule] = useState(null)
  const [editingRule, setEditingRule] = useState(null)
  const [editValues, setEditValues] = useState({})
  const [filter, setFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [updating, setUpdating] = useState(null)

  const filteredRules = rules.filter(r => {
    if (filter !== 'all' && r.status !== filter) return false
    if (categoryFilter !== 'all' && r.category !== categoryFilter) return false
    return true
  })

  const categories = [...new Set(rules.map(r => r.category))].sort()

  const updateRule = async (ruleId, status, edits = null) => {
    setUpdating(ruleId)
    try {
      const res = await fetch(`/api/rules/${docId}/${ruleId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          reviewed_by: 'reviewer',
          edits,
        }),
      })
      if (res.ok) {
        onRulesUpdate()
      }
    } catch (err) {
      console.error('Failed to update rule:', err)
    } finally {
      setUpdating(null)
      setEditingRule(null)
    }
  }

  const handleBulkAccept = async () => {
    const unflagged = rules.filter(
      r => r.status === 'pending_review' && (!r.guardrail_flags || r.guardrail_flags.length === 0)
    )
    for (const rule of unflagged) {
      await updateRule(rule.rule_id, 'approved')
    }
  }

  return (
    <div className="space-y-4">
      {/* Header with filters */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-gray-800">
          Extracted Rules ({filteredRules.length} of {rules.length})
        </h2>
        <div className="flex gap-2 flex-wrap">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="text-sm border rounded px-3 py-1.5"
          >
            <option value="all">All Status</option>
            <option value="pending_review">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="flagged_regulatory">Regulatory</option>
            <option value="flagged_uncertain">Uncertain</option>
          </select>
          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="text-sm border rounded px-3 py-1.5"
          >
            <option value="all">All Categories</option>
            {categories.map(c => (
              <option key={c} value={c}>{c.toUpperCase()}</option>
            ))}
          </select>
          <button
            onClick={handleBulkAccept}
            className="text-sm bg-green-600 text-white px-4 py-1.5 rounded hover:bg-green-700"
          >
            Accept All Unflagged
          </button>
        </div>
      </div>

      {/* Rule cards */}
      <div className="space-y-2">
        {filteredRules.map(rule => (
          <RuleCard
            key={rule.rule_id}
            rule={rule}
            expanded={expandedRule === rule.rule_id}
            editing={editingRule === rule.rule_id}
            editValues={editValues}
            updating={updating === rule.rule_id}
            onToggle={() => setExpandedRule(expandedRule === rule.rule_id ? null : rule.rule_id)}
            onAccept={() => updateRule(rule.rule_id, 'approved')}
            onReject={() => updateRule(rule.rule_id, 'rejected')}
            onFlagRegulatory={() => updateRule(rule.rule_id, 'flagged_regulatory')}
            onFlagUncertain={() => updateRule(rule.rule_id, 'flagged_uncertain')}
            onStartEdit={() => {
              setEditingRule(rule.rule_id)
              setEditValues({
                nl_statement: rule.nl_statement,
                value: rule.value,
                operator: rule.operator,
                field: rule.field,
              })
            }}
            onSaveEdit={() => updateRule(rule.rule_id, 'approved', editValues)}
            onCancelEdit={() => setEditingRule(null)}
            onEditChange={(field, value) => setEditValues(prev => ({ ...prev, [field]: value }))}
          />
        ))}
      </div>

      {filteredRules.length === 0 && (
        <div className="p-8 text-center text-gray-500 border rounded-lg">
          No rules match the current filters.
        </div>
      )}
    </div>
  )
}

function RuleCard({
  rule, expanded, editing, editValues, updating,
  onToggle, onAccept, onReject, onFlagRegulatory, onFlagUncertain,
  onStartEdit, onSaveEdit, onCancelEdit, onEditChange,
}) {
  const badge = STATUS_BADGES[rule.status] || STATUS_BADGES.pending_review
  const flagCount = rule.guardrail_flags?.length || 0

  return (
    <div className={clsx('border rounded-lg overflow-hidden', STATUS_STYLES[rule.status])}>
      {/* Main row */}
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          {/* Left: rule info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="font-mono text-sm font-semibold text-gray-700">{rule.rule_id}</span>
              <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-xs font-medium uppercase">
                {rule.category}
              </span>
              <span className={clsx('px-2 py-0.5 rounded text-xs font-medium', badge.color)}>
                {badge.label}
              </span>
              {flagCount > 0 && (
                <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full text-xs font-medium">
                  {flagCount} flag{flagCount !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            <button onClick={onToggle} className="text-left w-full group">
              <p className="text-sm text-gray-800 leading-relaxed">
                {rule.nl_statement}
              </p>
              <p className="text-xs text-gray-500 mt-1 font-mono">
                {rule.field} {rule.operator} {rule.value}{rule.unit ? ` ${rule.unit}` : ''}
                {rule.conditions && (
                  <span className="text-gray-400 ml-2">
                    | conditions: {typeof rule.conditions === 'object' ? Object.entries(rule.conditions).map(([k, v]) => `${k}=${v}`).join(', ') : rule.conditions}
                  </span>
                )}
              </p>
            </button>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={onAccept}
              disabled={updating}
              className="p-1.5 rounded hover:bg-green-200 text-green-700 disabled:opacity-30" title="Accept"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              onClick={onReject}
              disabled={updating}
              className="p-1.5 rounded hover:bg-red-200 text-red-700 disabled:opacity-30" title="Reject"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={onStartEdit}
              disabled={updating}
              className="p-1.5 rounded hover:bg-blue-200 text-blue-700 disabled:opacity-30" title="Edit & Accept"
            >
              <Edit3 className="h-4 w-4" />
            </button>
            <button
              onClick={onFlagRegulatory}
              disabled={updating}
              className="p-1.5 rounded hover:bg-amber-200 text-amber-700 disabled:opacity-30" title="Flag Regulatory"
            >
              <Flag className="h-4 w-4" />
            </button>
            <button
              onClick={onFlagUncertain}
              disabled={updating}
              className="p-1.5 rounded hover:bg-yellow-200 text-yellow-700 disabled:opacity-30" title="Flag Uncertain"
            >
              <AlertTriangle className="h-4 w-4" />
            </button>
            <button
              onClick={onToggle}
              className="p-1.5 rounded hover:bg-gray-200 text-gray-500 ml-1" title="Expand details"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t px-4 py-4 bg-white/60">
          {editing ? (
            <EditForm
              values={editValues}
              onChange={onEditChange}
              onSave={onSaveEdit}
              onCancel={onCancelEdit}
            />
          ) : (
            <RuleDetail rule={rule} />
          )}
        </div>
      )}
    </div>
  )
}

function RuleDetail({ rule }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div>
        <h4 className="text-sm font-medium text-gray-500 mb-2">Structured Fields</h4>
        <dl className="space-y-1.5">
          <DetailRow label="Field" value={rule.field} />
          <DetailRow label="Operator" value={rule.operator} />
          <DetailRow label="Value" value={`${rule.value}${rule.unit ? ' ' + rule.unit : ''}`} />
          <DetailRow label="Outcome" value={rule.outcome} />
          <DetailRow label="Failure Outcome" value={rule.failure_outcome} />
          <DetailRow label="Scope" value={rule.rule_scope} />
          <DetailRow label="Precedence" value={rule.precedence} />
          {rule.overrides_rule_id && <DetailRow label="Overrides" value={rule.overrides_rule_id} />}
          {rule.condition_logic && <DetailRow label="Logic" value={rule.condition_logic} />}
          {rule.footnote_ref && <DetailRow label="Footnote" value={rule.footnote_ref} />}
        </dl>
      </div>
      <div>
        <h4 className="text-sm font-medium text-gray-500 mb-2">Source</h4>
        <div className="bg-white border rounded p-3 text-sm italic text-gray-700 leading-relaxed mb-3">
          &ldquo;{rule.source_quote}&rdquo;
        </div>
        <p className="text-sm text-gray-500">
          Section: {rule.source_section || '—'} &nbsp;|&nbsp; Page: {rule.source_page || '—'}
        </p>

        {rule.guardrail_flags?.length > 0 && (
          <div className="mt-3">
            <h4 className="text-sm font-medium text-red-600 mb-2">Guardrail Flags</h4>
            {rule.guardrail_flags.map((flag, i) => (
              <div key={i} className="bg-red-50 border border-red-200 rounded p-2.5 mb-1.5 text-sm">
                <span className="font-mono font-bold text-red-700">{flag.type}</span>
                <p className="text-red-600 mt-0.5 leading-relaxed">{flag.reason}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DetailRow({ label, value }) {
  if (!value) return null
  return (
    <div className="flex text-sm">
      <dt className="w-32 text-gray-500 shrink-0">{label}:</dt>
      <dd className="text-gray-800">{value}</dd>
    </div>
  )
}

function EditForm({ values, onChange, onSave, onCancel }) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-blue-700">Edit Rule</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Field</label>
          <input
            value={values.field || ''}
            onChange={e => onChange('field', e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Value</label>
          <input
            value={values.value || ''}
            onChange={e => onChange('value', e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Operator</label>
          <input
            value={values.operator || ''}
            onChange={e => onChange('operator', e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">NL Statement</label>
          <input
            value={values.nl_statement || ''}
            onChange={e => onChange('nl_statement', e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button onClick={onSave} className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700">
          Save & Accept
        </button>
        <button onClick={onCancel} className="bg-gray-200 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-300">
          Cancel
        </button>
      </div>
    </div>
  )
}
