import React, { useEffect, useRef, useState } from 'react';

export default function DropdownMenu({ trigger, items = [] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (event) => {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open && (
        <div className="absolute right-0 z-50 mt-2 min-w-40 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
          {items.map((item, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { item.onSelect?.(); setOpen(false); }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
