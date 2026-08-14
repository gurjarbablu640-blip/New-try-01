import React, { useEffect } from 'react';

export default function Toast({ open, title, description, onClose }) {
  useEffect(() => {
    if (!open) return;
    const id = setTimeout(onClose, 3000);
    return () => clearTimeout(id);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed bottom-5 right-5 z-[60] rounded-2xl border border-emerald-200 bg-white p-4 shadow-xl">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      {description && <div className="mt-1 text-xs text-slate-500">{description}</div>}
    </div>
  );
}
