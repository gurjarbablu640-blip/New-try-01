import React, { useState } from 'react';
import Drawer from '../ui/Drawer';
import api from '../../api';

export default function EmailComposer({ open, onClose, to, companyId }){
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const handleDraft = async ()=>{
    try{
      // Use assistant tool to generate a short summary as draft (best-effort)
      const payload = { tool: 'sales_summary', company_id: companyId };
      const res = await api.post('/assistant/tool', payload);
      if(res && res.data){
        setMessage((prev)=> prev ? prev + '\n\n' + (res.data.summary || JSON.stringify(res.data)) : (res.data.summary || JSON.stringify(res.data)));
      }
    }catch(e){
      console.error('AI draft failed', e);
      alert('AI draft is unavailable');
    }
  };

  const handleSend = async ()=>{
    setSending(true);
    try{
      // Use existing outreach API (best-effort) to send/generate outreach
      await api.post('/outreach/generate', { company_id: companyId, subject, message });
      alert('Outreach request submitted');
      onClose();
    }catch(e){
      console.error('Send failed', e);
      alert('Send failed');
    }finally{ setSending(false); }
  };

  return (
    <Drawer open={open} onClose={onClose} width="w-[40rem]">
      <div>
        <h3 className="text-lg font-semibold">Compose Email</h3>
        <div className="mt-3">
          <div className="text-xs text-slate-500">To</div>
          <input className="w-full rounded-md border px-3 py-2" value={to || ''} onChange={(e)=>{}} />
        </div>
        <div className="mt-3">
          <div className="text-xs text-slate-500">Subject</div>
          <input className="w-full rounded-md border px-3 py-2" value={subject} onChange={(e)=>setSubject(e.target.value)} />
        </div>
        <div className="mt-3">
          <div className="text-xs text-slate-500">Message</div>
          <textarea rows={10} className="w-full rounded-md border px-3 py-2" value={message} onChange={(e)=>setMessage(e.target.value)} />
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={handleDraft} className="rounded-md border px-3 py-2">Draft with Oorja AI</button>
          <button onClick={handleSend} disabled={sending} className="rounded-md bg-slate-900 px-3 py-2 text-white">{sending ? 'Sending...' : 'Send'}</button>
        </div>
      </div>
    </Drawer>
  );
}
