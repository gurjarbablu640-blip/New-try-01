import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

// System & Health
export const getHealth = () => api.get("/health");

// Lead Factory & Discovery
export const searchApolloLeads = (params) => api.get("/leads/apollo/search", { params });
export const enrichLeadContact = (data) => api.post("/leads/apollo/enrich", data);
export const validateEmail = (email) => api.get("/leads/validate-email", { params: { email } });
export const checkDeduplication = (params) => api.get("/leads/dedup-check", { params });
export const qualifyLead = (companyId) => api.post(`/leads/${companyId}/qualify`);
export const setQualificationStatus = (companyId, data) => api.put(`/leads/${companyId}/qualification-status`, data);

// Companies & Company 360
export const getCompanies = (params = {}) => api.get("/companies", { params });
export const getCompany = (id) => api.get(`/companies/${id}`);
export const getCompany360 = (id) => api.get(`/company-360/${id}`);
export const searchCompanies = (query, limit = 20) => api.get("/companies", { params: { q: query, limit } });
export const rateLead = (companyId, rating, reason) => api.post(`/companies/${companyId}/rate`, { rating, reason });
export const rescoreCompany = (companyId) => api.post(`/companies/${companyId}/rescore`);
export const getNextAction = (companyId) => api.get(`/companies/${companyId}/next-action`);

// Facilities & Customer Assets
export const getFacilities = (params = {}) => api.get("/facilities", { params });
export const getCompanyFacilities = (companyId) => api.get(`/facilities/company/${companyId}`);
export const createFacility = (data) => api.post("/facilities", data);
export const getCustomerAssets = (params = {}) => api.get("/customer-assets", { params });
export const getCompanyAssets = (companyId) => api.get(`/customer-assets/company/${companyId}`);
export const createCustomerAsset = (data) => api.post("/customer-assets", data);
export const getCalibrationDue = (params = {}) => api.get("/customer-assets/calibration-due", { params });
export const checkNablFit = (params) => api.get("/customer-assets/nabl-fit-check", { params });

// Pipeline & CRM
export const getPipelineBoard = () => api.get("/pipeline/board");
export const getPipelineTasks = () => api.get("/pipeline/tasks");
export const getPipelineStats = () => api.get("/pipeline/stats");
export const movePipelineStage = (data) => api.post("/pipeline/move", data);
export const logActivity = (data) => api.post("/pipeline/activity", data);
export const getBuyingWindow = () => api.get("/buying-window");
export const getLookalikes = () => api.get("/lookalikes");
export const approveLookalikes = (companyIds) => api.post("/lookalikes/approve", { company_ids: companyIds });
export const semanticSearch = (query, filters) => api.post("/search/semantic", { query, filters });

// Oorja Sales OS Core Entities
export const getSalesOSSummary = () => api.get("/sales-os/summary");
export const getSalesOSOpportunities = (params = {}) => api.get("/sales-os/opportunities", { params });
export const createSalesOSOpportunity = (data) => api.post("/sales-os/opportunities", data);
export const getSalesOSTasks = (params = {}) => api.get("/sales-os/tasks", { params });
export const createSalesOSTask = (data) => api.post("/sales-os/tasks", data);
export const createSalesOSNote = (data) => api.post("/sales-os/notes", data);
export const recordAIFeedback = (data) => api.post("/sales-os/ai-feedback", data);

// Quotation Intelligence & Revisioning
export const getSalesOSQuotations = (params = {}) => api.get("/sales-os/quotations", { params });
export const getQuotationDetail = (id) => api.get(`/sales-os/quotations/${id}`);
export const createSalesOSQuotation = (data) => api.post("/sales-os/quotations", data);
export const getQuotationItems = (quotationId) => api.get(`/sales-os/quotations/${quotationId}/items`);
export const addQuotationItem = (quotationId, data) => api.post(`/sales-os/quotations/${quotationId}/items`, data);
export const approveQuotation = (quotationId, approved) => api.post(`/sales-os/quotations/${quotationId}/approval`, { approved });
export const reviseQuotation = (id, data) => api.post(`/quotations/${id}/revise`, data);
export const getQuotationRevisions = (id) => api.get(`/quotations/${id}/revisions`);
export const compareQuotationRevisions = (id, otherId) => api.get(`/quotations/${id}/compare/${otherId}`);
export const generateQuoteFromAssets = (data) => api.post("/quotations/generate-from-assets", data);
export const updateQuotationStatus = (id, data) => api.put(`/quotations/${id}/status`, data);

// Campaigns & Outbound
export const getCampaigns = () => api.get("/campaigns");
export const getCampaignDetail = (id) => api.get(`/campaigns/${id}`);
export const createCampaign = (data) => api.post("/campaigns", data);
export const addCampaignStep = (id, data) => api.post(`/campaigns/${id}/steps`, data);
export const getCampaignRecipients = (id, params = {}) => api.get(`/campaigns/${id}/recipients`, { params });
export const addCampaignRecipients = (id, data) => api.post(`/campaigns/${id}/recipients`, data);
export const approveCampaign = (id, approved = true) => api.post(`/campaigns/${id}/approve`, { approved });
export const dispatchCampaign = (id, limit = 50) => api.post(`/campaigns/${id}/dispatch`, null, { params: { limit } });
export const getInboxReplies = (params = {}) => api.get("/campaigns/inbox/replies", { params });
export const getCampaignAnalytics = (id) => api.get(`/campaigns/${id}/analytics`);

// Competitor Intelligence
export const getCompetitors = (params = {}) => api.get("/competitors", { params });
export const createCompetitor = (data) => api.post("/competitors", data);
export const seedDefaultCompetitors = () => api.post("/competitors/seed-default-competitors");
export const getCompetitorObservations = (params = {}) => api.get("/competitors/observations", { params });
export const createCompetitorObservation = (data) => api.post("/competitors/observations", data);

// Territory & Industrial Clusters
export const getTerritoryClusters = () => api.get("/territory/clusters");
export const getVisitRecommendations = (maxStops = 4) => api.get("/territory/visit-recommendations", { params: { max_stops: maxStops } });

// Analytics & Closed-Loop Learning
export const getAnalyticsOverview = (days = 90) => api.get("/analytics/overview", { params: { days } });
export const getLeadQualityAnalytics = () => api.get("/analytics/lead-quality");
export const getLearningSummary = () => api.get("/learning/summary");
export const getLearningPatterns = (status = "Candidate", limit = 50) => api.get("/learning/patterns", { params: { status, limit } });
export const generateLearningRules = () => api.post("/learning/generate-rules");
export const approveLearningRule = (ruleId, approved = true) => api.post(`/learning/patterns/${ruleId}/approve`, null, { params: { approved } });
export const getABInsights = () => api.get("/ab-insights");
export const getICPInsights = () => api.get("/icp-insights");

// Ask Oorja AI Orchestrator
export const askOorjaAI = (question) => api.post("/assistant/ask", { question });
export const getAssistantTools = () => api.get("/assistant/tools");
export const runAssistantTool = (data) => api.post("/assistant/tool", data);
export const recordAssistantFeedback = (data) => api.post("/assistant/feedback", data);

// Activities & Follow-ups
export const getActivities = (params = {}) => api.get("/activities", { params });
export const getTodayFollowups = () => api.get("/activities/followups");
export const createActivity = (data) => api.post("/activities", data);

export default api;
