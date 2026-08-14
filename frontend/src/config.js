const rawApiBase = import.meta.env.VITE_API_URL || "/api";

export const API_BASE = rawApiBase.replace(/\/$/, "");