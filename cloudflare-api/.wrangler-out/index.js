var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.js
var MAX_BATCH_SIZE = 5;
var MAX_HTML_BYTES = 19e5;
function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...extraHeaders
    }
  });
}
__name(jsonResponse, "jsonResponse");
function publicResponse(request, response) {
  const headers = new Headers(response.headers);
  if (request.headers.has("Origin")) {
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
    headers.set("Access-Control-Allow-Headers", "Accept, If-None-Match");
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}
__name(publicResponse, "publicResponse");
function isCalendarDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = /* @__PURE__ */ new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}
__name(isCalendarDate, "isCalendarDate");
function constantTimeEqual(left, right) {
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return difference === 0;
}
__name(constantTimeEqual, "constantTimeEqual");
function isAuthorized(request, env) {
  const token = env.PUBLISH_TOKEN;
  const authorization = request.headers.get("Authorization") || "";
  if (!token || token.length < 32 || !authorization.startsWith("Bearer ")) return false;
  return constantTimeEqual(authorization.slice(7), token);
}
__name(isAuthorized, "isAuthorized");
function decodePlan(plan) {
  if (!plan || typeof plan !== "object") throw new Error("Invalid plan");
  if (!isCalendarDate(plan.date)) throw new Error("Invalid plan date");
  if (typeof plan.title !== "string" || plan.title.length > 2e3) throw new Error("Invalid plan title");
  if (typeof plan.content_type !== "string" || !plan.content_type.toLowerCase().startsWith("text/html")) {
    throw new Error("Invalid plan content type");
  }
  if (typeof plan.content_hash !== "string" || !/^[a-f0-9]{64}$/.test(plan.content_hash)) {
    throw new Error("Invalid plan hash");
  }
  if (typeof plan.updated_at !== "string" || Number.isNaN(Date.parse(plan.updated_at))) {
    throw new Error("Invalid plan timestamp");
  }
  if (typeof plan.html_base64 !== "string" || plan.html_base64.length > Math.ceil(MAX_HTML_BYTES * 4 / 3) + 8) {
    throw new Error("Invalid plan body");
  }
  let binary;
  try {
    binary = atob(plan.html_base64);
  } catch {
    throw new Error("Invalid plan body");
  }
  if (binary.length === 0 || binary.length > MAX_HTML_BYTES) throw new Error("Invalid plan body size");
  const html = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) html[index] = binary.charCodeAt(index);
  return {
    date: plan.date,
    title: plan.title,
    content_type: plan.content_type,
    content_hash: plan.content_hash,
    updated_at: plan.updated_at,
    html_content: html
  };
}
__name(decodePlan, "decodePlan");
async function publishPlans(request, env) {
  if (!isAuthorized(request, env)) return jsonResponse({ detail: "Unauthorized" }, 401);
  const contentLength = Number(request.headers.get("Content-Length") || 0);
  if (contentLength > 12e6) return jsonResponse({ detail: "Request too large" }, 413);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ detail: "Invalid JSON" }, 400);
  }
  if (!payload || !Array.isArray(payload.plans) || payload.plans.length > MAX_BATCH_SIZE) {
    return jsonResponse({ detail: "Invalid plan batch" }, 422);
  }
  let plans;
  try {
    plans = payload.plans.map(decodePlan);
  } catch (error) {
    return jsonResponse({ detail: error.message }, 422);
  }
  if (new Set(plans.map((plan) => plan.date)).size !== plans.length) {
    return jsonResponse({ detail: "Duplicate plan dates" }, 422);
  }
  try {
    if (plans.length > 0) {
      const statements = plans.map((plan) => env.DB.prepare(`
        INSERT INTO plans (date, title, html_content, content_type, content_hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
          title = excluded.title,
          html_content = excluded.html_content,
          content_type = excluded.content_type,
          content_hash = excluded.content_hash,
          updated_at = excluded.updated_at
        WHERE excluded.updated_at >= plans.updated_at
      `).bind(
        plan.date,
        plan.title,
        plan.html_content,
        plan.content_type,
        plan.content_hash,
        plan.updated_at
      ));
      await env.DB.batch(statements);
    }
  } catch {
    return jsonResponse({ detail: "Plan storage failed" }, 503);
  }
  return jsonResponse({ accepted: plans.length });
}
__name(publishPlans, "publishPlans");
async function publishSyncStatus(request, env) {
  if (!isAuthorized(request, env)) return jsonResponse({ detail: "Unauthorized" }, 401);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ detail: "Invalid JSON" }, 400);
  }
  const timestamp = payload?.last_successful_sync;
  if (typeof timestamp !== "string" || Number.isNaN(Date.parse(timestamp))) {
    return jsonResponse({ detail: "Invalid sync timestamp" }, 422);
  }
  try {
    await env.DB.prepare(`
      INSERT INTO sync_state (id, last_successful_sync) VALUES (1, ?)
      ON CONFLICT(id) DO UPDATE SET last_successful_sync = excluded.last_successful_sync
      WHERE sync_state.last_successful_sync IS NULL
        OR excluded.last_successful_sync >= sync_state.last_successful_sync
    `).bind(timestamp).run();
  } catch {
    return jsonResponse({ detail: "Sync status storage failed" }, 503);
  }
  return jsonResponse({ status: "ok" });
}
__name(publishSyncStatus, "publishSyncStatus");
async function handlePublicRequest(request, env, url) {
  if (request.method === "OPTIONS") {
    return publicResponse(request, new Response(null, { status: 204 }));
  }
  if (request.method !== "GET") {
    return publicResponse(request, jsonResponse({ detail: "Method not allowed" }, 405));
  }
  if (url.pathname === "/healthz") {
    try {
      await env.DB.prepare("SELECT 1").first();
      return publicResponse(request, jsonResponse({ status: "ok" }));
    } catch {
      return publicResponse(request, jsonResponse({ status: "unavailable" }, 503));
    }
  }
  if (url.pathname === "/api/v1/sync-status") {
    try {
      const row = await env.DB.prepare(
        "SELECT last_successful_sync FROM sync_state WHERE id = 1"
      ).first();
      return publicResponse(request, jsonResponse({
        last_successful_sync: row?.last_successful_sync ?? null
      }));
    } catch {
      return publicResponse(request, jsonResponse({ detail: "API unavailable" }, 503));
    }
  }
  if (url.pathname === "/api/v1/plans") {
    const from = url.searchParams.get("from");
    const to = url.searchParams.get("to");
    if (from && !isCalendarDate(from) || to && !isCalendarDate(to)) {
      return publicResponse(request, jsonResponse({ detail: "Invalid date" }, 422));
    }
    if (from && to && from > to) {
      return publicResponse(request, jsonResponse({ detail: "'from' must not be after 'to'" }, 422));
    }
    let query = "SELECT date, title, updated_at FROM plans";
    const conditions = [];
    const bindings = [];
    if (from) {
      conditions.push("date >= ?");
      bindings.push(from);
    }
    if (to) {
      conditions.push("date <= ?");
      bindings.push(to);
    }
    if (conditions.length) query += ` WHERE ${conditions.join(" AND ")}`;
    query += " ORDER BY date";
    try {
      const result = await env.DB.prepare(query).bind(...bindings).all();
      return publicResponse(request, jsonResponse({
        plans: result.results.map((plan) => ({
          date: plan.date,
          title: plan.title,
          updated_at: plan.updated_at,
          html_url: `/api/v1/plans/${plan.date}/html`
        }))
      }));
    } catch {
      return publicResponse(request, jsonResponse({ detail: "API unavailable" }, 503));
    }
  }
  const htmlMatch = url.pathname.match(/^\/api\/v1\/plans\/(\d{4}-\d{2}-\d{2})\/html$/);
  if (htmlMatch) {
    if (!isCalendarDate(htmlMatch[1])) {
      return publicResponse(request, jsonResponse({ detail: "Invalid date" }, 422));
    }
    try {
      const plan = await env.DB.prepare(
        "SELECT html_content, content_type, content_hash FROM plans WHERE date = ?"
      ).bind(htmlMatch[1]).first();
      if (!plan) return publicResponse(request, jsonResponse({ detail: "Schedule not found" }, 404));
      const body = plan.html_content instanceof ArrayBuffer ? plan.html_content : new Uint8Array(plan.html_content);
      return publicResponse(request, new Response(body, {
        headers: {
          "Content-Type": plan.content_type,
          ETag: `"${plan.content_hash}"`,
          "Cache-Control": "public, max-age=60",
          "X-Content-Type-Options": "nosniff"
        }
      }));
    } catch {
      return publicResponse(request, jsonResponse({ detail: "API unavailable" }, 503));
    }
  }
  const metadataMatch = url.pathname.match(/^\/api\/v1\/plans\/(\d{4}-\d{2}-\d{2})$/);
  if (metadataMatch) {
    if (!isCalendarDate(metadataMatch[1])) {
      return publicResponse(request, jsonResponse({ detail: "Invalid date" }, 422));
    }
    try {
      const plan = await env.DB.prepare(
        "SELECT date, title, updated_at FROM plans WHERE date = ?"
      ).bind(metadataMatch[1]).first();
      if (!plan) return publicResponse(request, jsonResponse({ detail: "Schedule not found" }, 404));
      return publicResponse(request, jsonResponse({
        ...plan,
        html_url: `/api/v1/plans/${plan.date}/html`
      }));
    } catch {
      return publicResponse(request, jsonResponse({ detail: "API unavailable" }, 503));
    }
  }
  return publicResponse(request, jsonResponse({ detail: "Not found" }, 404));
}
__name(handlePublicRequest, "handlePublicRequest");
var index_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/internal/v1/plans" && request.method === "POST") {
      return publishPlans(request, env);
    }
    if (url.pathname === "/internal/v1/sync-status" && request.method === "POST") {
      return publishSyncStatus(request, env);
    }
    return handlePublicRequest(request, env, url);
  }
};
export {
  index_default as default
};
//# sourceMappingURL=index.js.map
