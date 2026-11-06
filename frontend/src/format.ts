export const isNil = (v: unknown) => v === null || v === undefined || (typeof v === "number" && !isFinite(v));

export function money(v: any, digits = 2): string {
  if (isNil(v)) return "—";
  return Number(v).toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function num(v: any, digits = 0): string {
  if (isNil(v)) return "—";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
}
export function pct(v: any, digits = 2): string {
  if (isNil(v)) return "—";
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: digits })}%`;
}
export function compact(v: any): string {
  if (isNil(v)) return "—";
  return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(v));
}
export function date(v: any): string {
  if (!v) return "—";
  const s = String(v);
  const d = new Date(s.length === 10 ? s + "T00:00:00" : s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
export function dateTime(v: any): string {
  if (!v) return "—";
  const d = new Date(String(v));
  if (isNaN(d.getTime())) return String(v);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
export function ago(v: any): string {
  if (!v) return "";
  const d = new Date(String(v)).getTime();
  if (isNaN(d)) return "";
  const s = Math.round((Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
export function bytes(v: any): string {
  if (isNil(v)) return "—";
  const n = Number(v);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export const INTENT_LABEL: Record<string, string> = {
  engagement: "Engagement",
  curiosity: "Curiosity",
  free_info_request: "Asks for free help",
  existing_spending: "Already spends",
  buying_question: "Buying question",
  paid_solution_request: "Asks to buy",
  verified_purchase: "Purchased",
};
export const INTENT_RANK: Record<string, number> = {
  engagement: 0, curiosity: 1, free_info_request: 2, existing_spending: 3, buying_question: 4, paid_solution_request: 5, verified_purchase: 6,
};
export const TYPE_LABEL: Record<string, string> = {
  question: "Question",
  frustration: "Frustration",
  unmet_need: "Unmet need",
  resource_request: "Resource request",
  dislikes_existing_solution: "Dislikes existing solution",
  repetitive_task: "Repetitive task",
  desired_outcome: "Desired outcome",
};
export const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook", x: "X", linkedin: "LinkedIn",
  reddit: "Reddit", substack: "Substack", newsletter: "Newsletter", podcast: "Podcast", web: "Website", feed: "RSS feed",
  community: "Community", other: "Other",
};
export const platformLabel = (p: any) => PLATFORM_LABEL[p] || (p ? String(p) : "—");
export const cap = (s: any) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : "");
export const human = (s: any) => cap(String(s || "").replace(/_/g, " "));

/** Today's date as YYYY-MM-DD in the user's local time zone (toISOString() would give the UTC date). */
export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
