import React from 'react';

export default function Drawer({ open, onClose, children, width = 'w-96' }) {
  return (
    <div className={`fixed inset-0 z-50 ${open ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div className={`absolute inset-0 bg-black/30 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
      <aside className={`absolute right-0 top-0 h-full ${width} transform bg-white shadow-xl transition-transform ${open ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="h-full overflow-auto p-4">{children}</div>
      </aside>
    </div>
  );
}
