import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

// Pipeline
export const getPipelineBoard = () => api.get("/pipeline/board");
export const getPipelineTasks = () => api.get("/pipeline/tasks");
export const getPipelineStats = () => api.get("/pipeline/stats");
export const movePipelineStage = (data) => api.post("/pipeline/move", data);
export const logActivity = (data) => api.post("/pipeline/activity", data);
export const recordABResult = (data) => api.post("/pipeline/ab-result", data);

// Buying Window
export const getBuyingWindow = () => api.get("/buying-window");

// Tasks
export const getTodayTasks = () => api.get("/tasks/today");

// Semantic Search
export const semanticSearch = (query, filters) =>
  api.post("/search/semantic", { query, filters });

// Lookalikes
export const getLookalikes = () => api.get("/lookalikes");

export const approveLookalikes = (companyIds) =>
  api.post("/lookalikes/approve", {
    company_ids: companyIds,
  });

// A/B Insights
export const getABInsights = () => api.get("/ab-insights");

// ICP Insights
export const getICPInsights = () => api.get("/icp-insights");

// Lead Rating
export const rateLead = (companyId, rating, reason) =>
  api.post(`/companies/${companyId}/rate`, {
    rating,
    reason,
  });

// Outreach
export const generateOutreach = (companyId) =>
  api.post("/outreach/generate", {
    company_id: companyId,
  });

// Next Action
export const getNextAction = (companyId) =>
  api.get(`/companies/${companyId}/next-action`);

// Triggers
export const runTriggers = () => api.post("/triggers/run-now");

// Scoring
export const rescoreCompany = (companyId) =>
  api.post(`/companies/${companyId}/rescore`);

export default api;