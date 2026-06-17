import axios from "axios";

import type {
  Article,
  BatchJob,
  ComplianceResult,
  ConfigEnvelope,
  ImageAsset,
  MaterialPayload,
  MaterialRecord,
  PublishTask,
} from "@/types";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
});

interface ApiResponse {
  success: boolean;
  message?: string;
  data?: unknown;
  [key: string]: unknown;
}

async function unwrap(request: Promise<{ data: ApiResponse }>): Promise<ApiResponse> {
  const response = await request;
  if (!response.data.success) {
    throw new Error(response.data.message || "请求失败");
  }
  return response.data;
}

export async function fetchConfig() {
  const payload = await unwrap(http.get("/api/config"));
  return payload.data as ConfigEnvelope;
}

export async function generateMaterial(material: MaterialPayload, config: object) {
  const payload = await unwrap(http.post("/api/materials/generate", { material, config }));
  return payload as unknown as { source: string; material: MaterialRecord; articles: Article[] };
}

export async function pullRecentMaterials(limit: number, config: object) {
  const payload = await unwrap(http.post("/api/materials/pull_recent", { limit, config }));
  return payload as unknown as { materials: MaterialRecord[] };
}

export async function publishArticles(articleIds: number[], mode: string, config: object) {
  const payload = await unwrap(http.post("/api/publish", { article_ids: articleIds, mode, config }));
  return payload as unknown as { tasks: PublishTask[] };
}

export async function fetchTasks(limit = 20) {
  const payload = await unwrap(http.get(`/api/tasks?limit=${limit}`));
  return payload.tasks as PublishTask[];
}

export async function checkCompliance(articles: Article[]) {
  const payload = await unwrap(http.post("/api/compliance/check", { articles }));
  return (payload.data as { results: ComplianceResult[] }).results;
}

export async function uploadBatchFile(file: File, config: object) {
  const form = new FormData();
  form.append("file", file);
  form.append("config", JSON.stringify(config || {}));
  const payload = await unwrap(http.post("/api/materials/batch_generate", form));
  return payload.job as BatchJob;
}

export async function fetchBatchJobs(limit = 20) {
  const payload = await unwrap(http.get(`/api/batch_jobs?limit=${limit}`));
  return payload.jobs as BatchJob[];
}

export async function fetchBatchJob(jobId: number) {
  const payload = await unwrap(http.get(`/api/batch_jobs/${jobId}`));
  return payload.job as BatchJob;
}

export async function processImages(files: File[], topic: string, platforms: string[]) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("topic", topic);
  form.append("platforms", platforms.join(","));
  const payload = await unwrap(http.post("/api/images/process", form));
  return payload.assets as ImageAsset[];
}
