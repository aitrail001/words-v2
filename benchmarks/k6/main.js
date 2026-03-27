import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const baseUrl = __ENV.BASE_URL || "http://host.docker.internal:8088/api";
const userEmail = __ENV.BENCH_USER_EMAIL;
const userPassword = __ENV.BENCH_USER_PASSWORD;
const adminEmail = __ENV.BENCH_ADMIN_EMAIL;
const adminPassword = __ENV.BENCH_ADMIN_PASSWORD;
const wordId = __ENV.BENCH_WORD_ID;
const phraseId = __ENV.BENCH_PHRASE_ID;
const meaningIds = (__ENV.BENCH_MEANING_IDS || "").split(",").filter(Boolean);

const flowFailureRate = new Rate("flow_failures");
const authDuration = new Trend("auth_flow_duration");
const learnerDuration = new Trend("learner_flow_duration");
const reviewDuration = new Trend("review_flow_duration");
const adminDuration = new Trend("admin_flow_duration");

export const options = {
  vus: Number(__ENV.K6_VUS || 1),
  duration: __ENV.K6_DURATION || "45s",
  noConnectionReuse: false,
  thresholds: {
    http_req_failed: ["rate<0.05"],
    flow_failures: ["rate<0.05"],
  },
};

function jsonHeaders(token) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function login(email, password) {
  const response = http.post(
    `${baseUrl}/auth/login`,
    JSON.stringify({ email, password }),
    { headers: jsonHeaders() },
  );

  const ok = check(response, {
    "login status 200": (r) => r.status === 200,
    "login access token present": (r) => Boolean(r.json("access_token")),
    "login refresh token present": (r) => Boolean(r.json("refresh_token")),
  });

  return ok ? response.json() : null;
}

function authFlow() {
  const start = Date.now();
  let failed = false;
  const tokens = login(userEmail, userPassword);
  if (!tokens) {
    failed = true;
    flowFailureRate.add(failed);
    authDuration.add(Date.now() - start);
    return;
  }

  const refreshResponse = http.post(
    `${baseUrl}/auth/refresh`,
    JSON.stringify({ refresh_token: tokens.refresh_token }),
    { headers: jsonHeaders() },
  );

  const refreshOk = check(refreshResponse, {
    "refresh status 200": (r) => r.status === 200,
    "refresh access token present": (r) => Boolean(r.json("access_token")),
  });
  if (!refreshOk) {
    failed = true;
    flowFailureRate.add(failed);
    authDuration.add(Date.now() - start);
    return;
  }

  const meResponse = http.get(`${baseUrl}/auth/me`, {
    headers: { Authorization: `Bearer ${refreshResponse.json("access_token")}` },
  });

  const meOk = check(meResponse, {
    "me status 200": (r) => r.status === 200,
    "me email present": (r) => Boolean(r.json("email")),
  });
  if (!meOk) {
    failed = true;
  }

  flowFailureRate.add(failed);
  authDuration.add(Date.now() - start);
}

function learnerFlow(userToken) {
  const start = Date.now();
  const params = { headers: { Authorization: `Bearer ${userToken}` } };

  const responses = http.batch([
    ["GET", `${baseUrl}/knowledge-map/overview`, null, params],
    ["GET", `${baseUrl}/knowledge-map/dashboard`, null, params],
    ["GET", `${baseUrl}/knowledge-map/ranges/1`, null, params],
    ["GET", `${baseUrl}/knowledge-map/list?status=new&sort=rank&limit=25&offset=0`, null, params],
    ["GET", `${baseUrl}/knowledge-map/search?q=bank`, null, params],
    ["GET", `${baseUrl}/knowledge-map/entries/word/${wordId}`, null, params],
    ["GET", `${baseUrl}/knowledge-map/entries/phrase/${phraseId}`, null, params],
  ]);

  const failed = !responses.every((response) => response.status === 200);
  flowFailureRate.add(failed);
  learnerDuration.add(Date.now() - start);
}

function reviewFlow(userToken) {
  const start = Date.now();
  let failed = false;
  const params = { headers: jsonHeaders(userToken) };

  const statsResponse = http.get(`${baseUrl}/reviews/queue/stats`, params);
  if (statsResponse.status !== 200) {
    failed = true;
    flowFailureRate.add(failed);
    reviewDuration.add(Date.now() - start);
    return;
  }

  let dueResponse = http.get(`${baseUrl}/reviews/queue/due?limit=5`, params);
  if (dueResponse.status !== 200) {
    failed = true;
    flowFailureRate.add(failed);
    reviewDuration.add(Date.now() - start);
    return;
  }

  let dueItems = dueResponse.json();
  if ((!Array.isArray(dueItems) || dueItems.length === 0) && meaningIds.length > 0) {
    const meaningId = meaningIds[Math.floor(Math.random() * meaningIds.length)];
    const queueResponse = http.post(
      `${baseUrl}/reviews/queue`,
      JSON.stringify({ meaning_id: meaningId }),
      params,
    );
    if (queueResponse.status !== 201 && queueResponse.status !== 200 && queueResponse.status !== 409) {
      failed = true;
      flowFailureRate.add(failed);
      reviewDuration.add(Date.now() - start);
      return;
    }
    dueResponse = http.get(`${baseUrl}/reviews/queue/due?limit=5`, params);
    dueItems = dueResponse.status === 200 ? dueResponse.json() : [];
  }

  if (Array.isArray(dueItems) && dueItems.length > 0) {
    const item = dueItems[0];
    const submitResponse = http.post(
      `${baseUrl}/reviews/queue/${item.id}/submit`,
      JSON.stringify({
        quality: 4,
        time_spent_ms: 1200,
        card_type: item.card_type || "flashcard",
      }),
      params,
    );
    if (submitResponse.status !== 200) {
      failed = true;
    }
  }

  flowFailureRate.add(failed);
  reviewDuration.add(Date.now() - start);
}

function adminFlow(adminToken) {
  const start = Date.now();
  const params = { headers: { Authorization: `Bearer ${adminToken}` } };
  const responses = http.batch([
    ["GET", `${baseUrl}/lexicon-inspector/entries?family=all&sort=alpha_asc&limit=25&offset=0`, null, params],
    ["GET", `${baseUrl}/lexicon-inspector/entries/word/${wordId}`, null, params],
    ["GET", `${baseUrl}/lexicon-inspector/entries/phrase/${phraseId}`, null, params],
  ]);
  const failed = !responses.every((response) => response.status === 200);
  flowFailureRate.add(failed);
  adminDuration.add(Date.now() - start);
}

export function setup() {
  const userTokens = login(userEmail, userPassword);
  const adminTokens = login(adminEmail, adminPassword);

  if (!userTokens || !adminTokens) {
    throw new Error("benchmark setup login failed");
  }

  return {
    userAccessToken: userTokens.access_token,
    adminAccessToken: adminTokens.access_token,
  };
}

export default function (data) {
  const roll = Math.random();

  if (roll < 0.15) {
    authFlow();
  } else if (roll < 0.70) {
    learnerFlow(data.userAccessToken);
  } else if (roll < 0.90) {
    reviewFlow(data.userAccessToken);
  } else {
    adminFlow(data.adminAccessToken);
  }

  sleep(1);
}

export function handleSummary(data) {
  const outputPath = __ENV.K6_SUMMARY_PATH || "benchmarks/results/k6-summary.json";
  return {
    [outputPath]: JSON.stringify(data, null, 2),
  };
}
