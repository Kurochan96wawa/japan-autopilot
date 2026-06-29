/**
 * littletabi — Family Trip Planner (Cloudflare Worker)
 * 施策11: 子連れ日本旅程をAIで生成する /plan の実行時バックエンド。
 *
 * 使うAI: Cloudflare Workers AI（Worker内蔵・無料枠・外部APIキー不要）。
 *   → Worker設定の "Settings > Bindings" で AI バインディング(変数名: AI)を追加するだけ。
 *
 * モデル: @cf/meta/llama-3.1-8b-instruct-fast
 *   （旧 @cf/meta/llama-3.1-8b-instruct は 2026-05-30 に廃止されたため -fast 系に移行）
 *
 * セキュリティ: littletabi.com からのCORSのみ許可。入力は長さ制限。出力は<script>等を除去。
 */
const ALLOWED_ORIGIN = "https://littletabi.com";
const MODEL = "@cf/meta/llama-3.1-8b-instruct-fast";

function cors(extra) {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    ...(extra || {}),
  };
}

function sanitize(h) {
  return String(h || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/ on\w+="[^"]*"/gi, "")
    .replace(/<\/?(html|head|body|!doctype)[^>]*>/gi, "")
    .trim();
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors() });
    const json = (o, s) =>
      new Response(JSON.stringify(o), { status: s || 200, headers: cors({ "Content-Type": "application/json" }) });
    if (request.method !== "POST") return json({ error: "POST only" }, 405);

    let body;
    try { body = await request.json(); } catch (e) { return json({ error: "bad request" }, 400); }

    const ages = String(body.ages || "").slice(0, 80);
    const days = Math.max(1, Math.min(21, parseInt(body.days, 10) || 5));
    const cities = String(body.cities || "Tokyo").slice(0, 120);
    const interests = String(body.interests || "").slice(0, 240);
    const pace = ["relaxed", "balanced", "packed"].includes(body.pace) ? body.pace : "balanced";

    const prompt =
      "You are a warm, practical family-travel planner for Japan. Build a " + days +
      "-day itinerary for a family visiting " + cities + " with children aged " + ages +
      ". Interests: " + (interests || "general kid-friendly sightseeing") + ". Pace: " + pace + ". " +
      "Rules: be specific (areas, named attractions, approx durations and walking distances), kid-friendly " +
      "(plan naps and meal stops, note stroller access), and HONEST - never invent prices or hours; if relevant " +
      "say (check the official site). Keep each day to 3-5 short bullet points plus ONE practical parent tip. " +
      "Output CLEAN HTML ONLY: for each day a <h3>Day N</h3> then a <ul><li>item</li></ul>, then a " +
      "<p class=\"tip\"><strong>Tip:</strong> text</p>. No markdown, no preamble, no closing summary.";

    let html = "";
    try {
      const r = await env.AI.run(MODEL, {
        messages: [{ role: "user", content: prompt }],
        max_tokens: 1400,
        temperature: 0.7,
      });
      html = (r && (r.response || (r.result && r.result.response))) || "";
    } catch (e) {
      return json({ error: "The planner is busy right now - please try again in a moment." }, 503);
    }

    html = sanitize(html);
    if (!html) return json({ error: "Could not generate a plan - try simplifying the inputs." }, 502);
    return json({ html, meta: { ages, days, cities, interests, pace } });
  },
};
