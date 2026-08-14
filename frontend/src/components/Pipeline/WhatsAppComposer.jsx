import React, { useState } from 'react';
import Drawer from '../ui/Drawer';

export default function WhatsAppComposer({ open, onClose, contactName, number, companyId }){
  const [message, setMessage] = useState('');

  const handleDraft = ()=>{
    // Best-effort placeholder: ask assistant via existing endpoint (omitted) — fallback: leave empty
    setMessage((m)=> m || `Hello ${contactName || ''},\n\n`);
  };

  const openWhatsApp = ()=>{
    const phone = (number || '').toString().replace(/\D/g,'');
    const text = encodeURIComponent(message || '');
    const url = `https://wa.me/${phone}?text=${text}`;
    window.open(url, '_blank');
  };

  return (
    <Drawer open={open} onClose={onClose} width="w-[28rem]">
      <div>
        <h3 className="text-lg font-semibold">WhatsApp</h3>
        <div className="mt-3 text-sm text-slate-500">Contact: {contactName || '--'}</div>
        <div className="mt-1 text-sm text-slate-500">Number: {number || '--'}</div>
        <div className="mt-3">
          <textarea rows={8} className="w-full rounded-md border px-3 py-2" value={message} onChange={(e)=>setMessage(e.target.value)} />
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={handleDraft} className="rounded-md border px-3 py-2">Draft with Oorja AI</button>
          <button onClick={openWhatsApp} className="rounded-md bg-green-600 px-3 py-2 text-white">Open WhatsApp</button>
        </div>
      </div>
    </Drawer>
  );
}
