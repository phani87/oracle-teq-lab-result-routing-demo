import axios from "axios";

const api = axios.create({
  baseURL: "/api"
});

export const getOpenOrders = () => api.get("/orders/open");
export const submitResult = (payload) => api.post("/results", payload);
export const getResultProgress = (id) => api.get(`/results/${id}/progress`);

export default api;
