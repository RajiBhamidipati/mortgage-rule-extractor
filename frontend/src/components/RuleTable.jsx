import { useState } from 'react'
import { Check, X, Edit3, Flag, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'

const STATUS_STYLES = {
  pending_review: 'bg-blue-50',
  approved: 'bg-green-50',
  rejected: 'bg-red-50',
  flagged_regulatory: 'bg-amber-50',
  flagged_uncertain: 'bg-yellow-50',
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
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">
          Extracted Rules ({rules.length})
        </h2>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="text-sm border rounded px-2 py-1"
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
            className="text-sm border rounded px-2 py-1"
          >
            <option value="all">All Categories</option>
            {categories.map(c => (
              <option key={c} value={c}>{c.toUpperCase()}</option>
            ))}
          </select>
          <button
            onClick={handleBulkAccept}
            className="text-sm bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700"
          >
            Accept All Unflagged
          </button>
        </div>
      </div>

      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-700 text-white">
            <tr>
              <th className="px-3 py-2 text-left w-24">Rule ID</th>
              <th className="px-3 py-2 text-left w-24">Category</th>
              <th className="px-3 py-2 text-left">NL Statement</th>
              <th className="px-3 py-2 text-left w-20">Value</th>
              <th className="px-3 py-2 text-left w-24">Status</th>
              <th className="px-3 py-2 text-left w-16">Flags</th>
              <th className="px-3 py-2 text-center w-40">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredRules.map(rule => (
              <RuleRow
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
          </tbody>
        </table>
        {filteredRules.length === 0 && (
          <div className="p-8 text-center text-gray-500">
            No rules match the current filters.
          </div>
        )}
      </div>
    </div>
  )
}

function RuleRow({
  rule, expanded, editing, editValues, updating,
  onToggle, onAccept, onReject, onFlagRegulatory, onFlagUncertain,
  onStartEdit, onSaveEdit, onCancelEdit, onEditChange,
}) {
  const badge = STATUS_BADGES[rule.status] || STATUS_BADGES.pending_review
  const flagCount = rule.guardrail_flags?.length || 0

  return (
    <>
      <tr className={clsx(STATUS_STYLES[rule.status], 'border-b hover:opacity-90 transition-opacity')}>
        <td className="px-3 py-2 font-mono text-xs">{rule.rule_id}</td>
        <td className="px-3 py-2">
          <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-xs font-medium uppercase">
            {rule.category}
          </span>
        </td>
        <td className="px-3 py-2">
          <button onClick={onToggle} className="flex items-center gap-1 text-left w-full">
            {expanded ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
            <span className="truncate">{rule.nl_statement}</span>
          </button>
        </td>
        <td className="px-3 py-2 font-mono text-xs">
          {rule.operator} {rule.value}{rule.unit ? ` ${rule.unit}` : ''}
        </td>
        <td className="px-3 py-2">
          <span className={clsx('px-2 py-0.5 rounded text-xs font-medium', badge.color)}>
            {badge.label}
          </span>
        </td>
        <td className="px-3 py-2 text-center">
          {flagCount > 0 && (
            <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full text-xs font-medium">
              {flagCount}
            </span>
          )}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center justify-center gap-1">
            <button
              onClick={onAccept}
              disabled={updating}
              className="p-1 rounded hover:bg-green-200 text-green-700" title="Accept"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              onClick={onReject}
              disabled={updating}
              className="p-1 rounded hover:bg-red-200 text-red-700" title="Reject"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={onStartEdit}
              disabled={updating}
              className="p-1 rounded hover:bg-blue-200 text-blue-700" title="Edit & Accept"
            >
              <Edit3 className="h-4 w-4" />
            </button>
            <button
              onClick={onFlagRegulatory}
              disabled={updating}
              className="p-1 rounded hover:bg-amber-200 text-amber-700" title="Flag Regulatory"
            >
              <Flag className="h-4 w-4" />
            </button>
            <button
              onClick={onFlagUncertain}
              disabled={updating}
              className="p-1 rounded hover:bg-yellow-200 text-yellow-700" title="Flag Uncertain"
            >
              <AlertTriangle className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className={clsx(STATUS_STYLES[rule.status], 'border-b')}>
          <td colSpan={7} className="px-6 py-4">
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
          </td>
        </tr>
      )}
    </>
  )
}

function RuleDetail({ rule }) {
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <h4 className="font-medium text-gray-500 mb-1">Structured Fields</h4>
        <dl className="space-y-1">
          <DetailRow label="Field" value={rule.field} />
          <DetailRow label="Operator" value={rule.operator} />
          <DetailRow label="Value" value={`${rule.value}${rule.unit ? ' ' + rule.unit : ''}`} />
          <DetailRow label="Outcome" value={rule.outcome} />
          <DetailRow label="Failure Outcome" value={rule.failure_outcome} />
          <DetailRow label="Scope" value={rule.rule_scope} />
          {rule.overrides_rule_id && <DetailRow label="Overrides" value={rule.overrides_rule_id} />}
          {rule.condition_logic && <DetailRow label="Logic" value={rule.condition_logic} />}
          {rule.footnote_ref && <DetailRow label="Footnote" value={rule.footnote_ref} />}
        </dl>
      </div>
      <div>
        <h4 className="font-medium text-gray-500 mb-1">Source</h4>
        <div className="bg-white border rounded p-3 text-sm italic text-gray-700 mb-3">
          "{rule.source_quote}"
        </div>
        <p className="text-xs text-gray-500">
          Section: {rule.source_section || '—'} | Page: {rule.source_page || '—'}
        </p>

        {rule.guardrail_flags?.length > 0 && (
          <div className="mt-3">
            <h4 className="font-medium text-red-600 mb-1">Guardrail Flags</h4>
            {rule.guardrail_flags.map((flag, i) => (
              <div key={i} className="bg-red-50 border border-red-200 rounded p-2 mb-1 text-xs">
                <span className="font-mono font-bold text-red-700">{flag.type}</span>
                <span className="text-red-600 ml-2">{flag.reason}</span>
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
    <div className="flex">
      <dt className="w-28 text-gray-500 shrink-0">{label}:</dt>
      <dd className="text-gray-800 font-mono text-xs">{value}</dd>
    </div>
  )
}

function EditForm({ values, onChange, onSave, onCancel }) {
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-blue-700">Edit Rule</h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Field</label>
          <input
            value={values.field || ''}
            onChange={e => onChange('field', e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Value</label>
          <input
            value={values.value || ''}
            onChange={e => onChange('value', e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Operator</label>
          <input
            value={values.operator || ''}
            onChange={e => onChange('operator', e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">NL Statement</label>
          <input
            value={values.nl_statement || ''}
            onChange={e => onChange('nl_statement', e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button onClick={onSave} className="bg-green-600 text-white px-4 py-1.5 rounded text-sm hover:bg-green-700">
          Save & Accept
        </button>
        <button onClick={onCancel} className="bg-gray-200 text-gray-700 px-4 py-1.5 rounded text-sm hover:bg-gray-300">
          Cancel
        </button>
      </div>
    </div>
  )
}
