import React, { useEffect, useState } from 'react';
import Drawer from '../ui/Drawer';
import api from '../../api';

export default function CustomerDrawer({ companyId, open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    api.get(`/company-360/${companyId}`).then((res) => setData(res.data)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [companyId]);

  return (
    <Drawer open={open} onClose={onClose} width="w-[40rem]">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-slate-500">Company</div>
          <div className="mt-1 text-xl font-bold text-slate-900">{data?.company?.name || 'Company'}</div>
          <div className="text-sm text-slate-500">{data?.company?.industry || ''} · {data?.company?.city || ''}</div>
        </div>
        <div className="flex gap-2">
          <button className="rounded-md border px-3 py-2 text-sm">Follow</button>
          <button className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white">Create Task</button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border p-3">
          <div className="text-xs text-slate-500">Open Opportunities</div>
          <div className="mt-1 text-lg font-semibold">{data?.opportunities?.length || 0}</div>
        </div>
        <div className="rounded-xl border p-3">
          <div className="text-xs text-slate-500">Active Quotations</div>
          <div className="mt-1 text-lg font-semibold">{data?.quotations?.length || 0}</div>
        </div>
        <div className="rounded-xl border p-3">
          <div className="text-xs text-slate-500">Last Activity</div>
          <div className="mt-1 text-lg font-semibold">{data?.company?.last_activity || '--'}</div>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-lg font-medium">Contacts</h3>
        <div className="mt-2 space-y-2">
          {data?.contacts?.length ? data.contacts.slice(0,6).map((c) => (
            <div key={c.id} className="rounded-md border p-2">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div className="text-sm text-slate-500">{c.designation || ''}</div>
                </div>
                <div className="text-sm text-slate-500">{c.email || '--'}</div>
              </div>
            </div>
          )) : <div className="text-sm text-slate-500">No contacts</div>}
        </div>
      </div>

    </Drawer>
  );
}
