import type { Platform } from "@/types";

export const platformOptions: Array<{ label: string; value: Platform }> = [
  { label: "小红书", value: "xiaohongshu" },
  { label: "知乎", value: "zhihu" },
  { label: "公众号", value: "official_account" },
  { label: "头条", value: "toutiao" },
  { label: "视频号", value: "shipinhao" },
];

export const platformLabels = platformOptions.reduce<Record<string, string>>((labels, item) => {
  labels[item.value] = item.label;
  return labels;
}, {});

export const overrideLabels: Record<string, string> = {
  app_database_url: "本地数据库",
  llm_api_key: "大模型 API Key",
  llm_base_url: "大模型 Base URL",
  llm_model: "大模型名称",
  external_database_url: "外部素材数据库",
  pending_output_dir: "待发布目录",
  wechat_app_id: "公众号 App ID",
  wechat_app_secret: "公众号 App Secret",
  wechat_auto_publish: "公众号自动发布",
  wechat_enable_mass_send: "公众号群发",
  scheduler_enabled: "定时任务",
  scheduler_interval_minutes: "定时间隔",
};
