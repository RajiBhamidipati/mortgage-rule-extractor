import { AlertTriangle } from 'lucide-react'

export default function RegulatoryBanner({ flagCount = 0 }) {
  return (
    <div className="bg-amber-50 border-b-2 border-amber-400 px-4 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
          <div>
            <span className="font-semibold text-amber-800">
              EU AI Act Classification: HIGH RISK
            </span>
            <span className="text-amber-700 mx-2">|</span>
            <span className="text-amber-700">
              FCA MCOB Compliance Required
            </span>
          </div>
        </div>
        {flagCount > 0 && (
          <div className="bg-red-100 text-red-800 px-3 py-1 rounded-full text-sm font-medium">
            {flagCount} unresolved flag{flagCount !== 1 ? 's' : ''}
          </div>
        )}
      </div>
    </div>
  )
}
