import React, { useEffect, useMemo, useState } from 'react';
import PipelineBoard from '../components/PipelineBoard';
import { getPipelineBoard } from '../api';
import PageHeader from '../components/ui/PageHeader';
import StatCard from '../components/ui/StatCard';
import CustomerDrawer from '../components/Pipeline/CustomerDrawer';

export default function PipelinePage(){
  const [board, setBoard] = useState({});
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(()=>{ load(); }, []);
  const load = async () => {
    setLoading(true);
    try{
      const res = await getPipelineBoard();
      setBoard(res.data.board || {});
      setCounts(res.data.stage_counts || {});
    }catch(e){ console.error(e); }
    setLoading(false);
  };

  const locations = useMemo(()=>{
    const map = {};
    Object.values(board).forEach(list=> list.forEach(card => {
      const loc = (card.city || card.state || 'Unknown') || 'Unknown';
      const key = loc;
      map[key] = map[key] || { count:0, value:0 };
      map[key].count += 1;
      // value not provided reliably; skip sum
    }));
    return Object.keys(map).sort().map(k=>({ name:k, ...map[k]}));
  }, [board]);

  const [emailOpen, setEmailOpen] = useState(false);
  const [waOpen, setWaOpen] = useState(false);
  const [composerTo, setComposerTo] = useState(null);

  React.useEffect(()=>{
    const onEmail = (e)=>{
      setComposerTo(e.detail || null);
      setEmailOpen(true);
    };
    const onWA = (e)=>{
      setComposerTo(e.detail || null);
      setWaOpen(true);
    };
    window.addEventListener('openEmailComposer', onEmail);
    window.addEventListener('openWhatsAppComposer', onWA);
    return ()=>{
      window.removeEventListener('openEmailComposer', onEmail);
      window.removeEventListener('openWhatsAppComposer', onWA);
    };
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="col-span-1">
        <PageHeader title="Pipeline" subtitle="Visualize and manage your entire sales pipeline" />
        <div className="space-y-3">
          <div className="rounded-xl border bg-white p-3">
            <div className="text-sm text-slate-500">Stages</div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <StatCard label="Pipeline Value" value={"—"} hint={"Live"} />
              <StatCard label="Open Opportunities" value={Object.values(counts).reduce((a,b)=>a+b,0)} />
              <StatCard label="Win Rate" value={"—"} />
              <StatCard label="Follow-ups Due" value={"—"} />
            </div>
          </div>

          <div className="rounded-xl border bg-white p-3">
            <div className="text-sm text-slate-500">Locations</div>
            <div className="mt-2 space-y-2 max-h-[60vh] overflow-auto">
              {locations.length ? locations.map(loc => (
                <button key={loc.name} onClick={() => setSelectedLocation(loc.name)} className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left ${selectedLocation===loc.name? 'bg-slate-100': 'hover:bg-slate-50'}`}>
                  <div>
                    <div className="text-sm font-medium text-slate-800">{loc.name}</div>
                    <div className="text-xs text-slate-500">{loc.count} deals</div>
                  </div>
                  <div className="text-xs text-slate-500">›</div>
                </button>
              )) : <div className="text-sm text-slate-500">No locations found</div>}
            </div>
          </div>
        </div>
      </div>

      <div className="col-span-1 lg:col-span-1">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-xs text-slate-500">By Location</div>
              <h3 className="text-lg font-bold">Customers</h3>
            </div>
            <div className="text-sm text-slate-500">{selectedLocation || 'All locations'}</div>
          </div>

          <PipelineBoard onCompanyClick={(id)=>{ setSelectedCompany(id); setDrawerOpen(true);}} locationFilter={selectedLocation} />
        </div>
      </div>

      <div className="col-span-1">
        <div className="rounded-xl border bg-white p-3">
          <div className="text-sm text-slate-500">Details</div>
          {selectedCompany ? (
            <div className="mt-3">
              <div className="text-sm text-slate-700">Open details for company #{selectedCompany}</div>
              <div className="mt-3">
                <button onClick={()=>setDrawerOpen(true)} className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white">Open Details</button>
              </div>
            </div>
          ) : (
            <div className="mt-3 text-sm text-slate-500">Select a customer card to view details</div>
          )}
        </div>
      </div>

      <CustomerDrawer companyId={selectedCompany} open={drawerOpen} onClose={()=>setDrawerOpen(false)} />

      {/* Email / WhatsApp composers */}
      <EmailComposer open={emailOpen} onClose={()=>setEmailOpen(false)} to={composerTo?.email} companyId={composerTo?.companyId} />
      <WhatsAppComposer open={waOpen} onClose={()=>setWaOpen(false)} contactName={composerTo?.name} number={composerTo?.phone} companyId={composerTo?.companyId} />
    </div>
  );
}
