/**
 * TaskList Component
 * ===================
 * Daily action list sorted by: NABL_RENEWAL_DUE first, then ICP score.
 * Each task shows: company, person name, suggested action, channel icon.
 * One-click to: copy outreach → mark as sent → move stage.
 */
import React, { useState, useEffect } from 'react';
import { getTodayTasks, logActivity, movePipelineStage } from '../api';

const CHANNEL_ICONS = {
  email: '📧',
  whatsapp: '💬',
  phone: '📞',
  linkedin: '🔗',
};

const ACTION_ICONS = {
  SEND_EMAIL: '📧',
  SEND_WHATSAPP: '💬',
  MAKE_CALL: '📞',
  SEND_VALUE_EMAIL: '🎁',
  CONNECT_LINKEDIN: '🔗',
  WAIT_7_DAYS: '⏳',
  MARK_NURTURE: '🌱',
  REQUEST_REFERRAL: '🤝',
};

export default function TaskList({ onCompanyClick }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    try {
      const res = await getTodayTasks();
      setTasks(res.data.tasks || []);
      setStats({
        total: res.data.total_tasks,
        overdue: res.data.overdue_count,
        today: res.data.today_count,
      });
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  const markAsDone = async (task, activityType) => {
    try {
      await logActivity({
        company_id: task.company_id,
        activity_type: activityType,
        outcome: 'completed',
      });
      // Remove from list
      setTasks(tasks.filter(t => t.pipeline_id !== task.pipeline_id));
    } catch (err) {
      console.error('Failed to mark done:', err);
    }
  };

  if (loading) {
    return <div className="animate-pulse p-4">Loading tasks...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-gray-900">Today's Tasks</h2>
        <div className="flex items-center gap-3 text-sm">
          {stats.overdue > 0 && (
            <span className="text-red-600 font-medium">
              {stats.overdue} overdue
            </span>
          )}
          <span className="text-gray-500">{stats.total} total</span>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          <p className="text-2xl mb-2">✅</p>
          <p>All caught up! No tasks due today.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {tasks.map((task) => (
            <TaskCard
              key={task.pipeline_id}
              task={task}
              onClick={() => onCompanyClick?.(task.company_id)}
              onMarkDone={markAsDone}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TaskCard({ task, onClick, onMarkDone }) {
  const isOverdue = task.is_overdue;
  const signalIcon = task.top_signal === 'NABL_RENEWAL_DUE' ? '🔴' :
                     task.top_signal === 'ISO_AUDIT_WINDOW' ? '🟠' : '🟡';

  return (
    <div
      className={`border rounded-md p-3 ${isOverdue ? 'border-red-300 bg-red-50' : 'bg-white'} hover:shadow-sm transition-shadow`}
    >
      <div className="flex items-start gap-3">
        <div className="text-lg">{signalIcon}</div>

        <div className="flex-1 min-w-0" onClick={onClick}>
          <div className="flex items-center gap-2">
            <p className="font-medium text-sm text-gray-900 truncate cursor-pointer hover:text-blue-600">
              {task.company_name}
            </p>
            {isOverdue && (
              <span className="text-xs bg-red-100 text-red-700 px-1.5 rounded">
                {task.days_overdue}d overdue
              </span>
            )}
          </div>

          <p className="text-xs text-gray-500">
            {task.person_name && `${task.person_name} · `}
            {task.city} · ICP: {task.icp_score}
          </p>

          {task.next_action && (
            <p className="text-xs text-blue-700 mt-1 truncate">
              → {task.next_action}
            </p>
          )}

          {task.urgency_reason && (
            <p className="text-xs text-orange-600 mt-0.5 truncate">
              {task.urgency_reason}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => onMarkDone(task, 'email_sent')}
            className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
            title="Mark email sent"
          >
            📧
          </button>
          <button
            onClick={() => onMarkDone(task, 'whatsapp_sent')}
            className="text-xs px-2 py-1 bg-green-50 text-green-700 rounded hover:bg-green-100"
            title="Mark WhatsApp sent"
          >
            💬
          </button>
          <button
            onClick={() => onMarkDone(task, 'call_made')}
            className="text-xs px-2 py-1 bg-purple-50 text-purple-700 rounded hover:bg-purple-100"
            title="Mark call made"
          >
            📞
          </button>
        </div>
      </div>
    </div>
  );
}
