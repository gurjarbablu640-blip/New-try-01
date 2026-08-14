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
  api.post("/lookalikes/approve", { company_ids: companyIds });

// A/B Insights
export const getABInsights = () => api.get("/ab-insights");

// ICP Insights
export const getICPInsights = () => api.get("/icp-insights");

// Lead Rating
export const rateLead = (companyId, rating, reason) =>
  api.post(`/companies/${companyId}/rate`, { rating, reason });

// Outreach
export const generateOutreach = (companyId) =>
  api.post("/outreach/generate", { company_id: companyId });

// Next Action
export const getNextAction = (companyId) =>
  api.get(`/companies/${companyId}/next-action`);

// Triggers
export const runTriggers = () => api.post("/triggers/run-now");

// Scoring
export const rescoreCompany = (companyId) =>
  api.post(`/companies/${companyId}/rescore`);

// ============================================================
// OORJA SALES OS
// ============================================================
export const getSalesOSSummary = () => api.get("/sales-os/summary");
export const getSalesOSOpportunities = (params = {}) =>
  api.get("/sales-os/opportunities", { params });
export const createSalesOSOpportunity = (data) =>
  api.post("/sales-os/opportunities", data);
export const getSalesOSTasks = (params = {}) =>
  api.get("/sales-os/tasks", { params });
export const createSalesOSTask = (data) =>
  api.post("/sales-os/tasks", data);
export const createSalesOSNote = (data) =>
  api.post("/sales-os/notes", data);
export const recordAIFeedback = (data) =>
  api.post("/sales-os/ai-feedback", data);

// Quotations
export const getSalesOSQuotations = (params = {}) =>
  api.get("/sales-os/quotations", { params });
export const createSalesOSQuotation = (data) =>
  api.post("/sales-os/quotations", data);
export const getQuotationItems = (quotationId) =>
  api.get(`/sales-os/quotations/${quotationId}/items`);
export const addQuotationItem = (quotationId, data) =>
  api.post(`/sales-os/quotations/${quotationId}/items`, data);
export const approveQuotation = (quotationId, approved) =>
  api.post(`/sales-os/quotations/${quotationId}/approval`, { approved });
export const importHistoricalQuotations = (file) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/sales-os/quotations/import", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

// Instrument / pricing intelligence
export const normalizeInstrument = (name) =>
  api.get("/sales-os/instrument/normalize", { params: { name } });
export const resolveInstrument = (data) =>
  api.post("/sales-os/instrument/resolve", data);
export const findSimilarQuotes = (params) =>
  api.get("/sales-os/quotation-intelligence/similar", { params });
export const getPriceRecommendation = (params) =>
  api.get("/sales-os/quotation-intelligence/price-recommendation", { params });

export default api;
