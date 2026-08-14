import React from 'react';

export default function Table({ columns = [], rows = [], className = '' }) {
  return (
    <div className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left">
          <thead className="bg-slate-50">
            <tr>
              {columns.map((column) => (
                <th key={column.key || column.header} className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-50/80">
                {columns.map((column) => (
                  <td key={column.key || column.header} className="px-4 py-3 text-sm text-slate-700">
                    {typeof column.render === 'function' ? column.render(row) : row[column.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
