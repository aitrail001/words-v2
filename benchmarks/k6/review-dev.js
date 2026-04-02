import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const baseUrl = __ENV.BASE_URL || "http://host.docker.internal:4200/api";
const userEmail = __ENV.BENCH_USER_EMAIL;
const userPassword = __ENV.BENCH_USER_PASSWORD;

const flowFailureRate = new Rate("flow_failures");
const dueFailureRate = new Rate("review_due_failures");
const statsFailureRate = new Rate("review_stats_failures");
const submitFailureRate = new Rate("review_submit_failures");
const emptyDueRate = new Rate("review_empty_due");
const dueLatency = new Trend("review_due_duration");
const dueQueryCount = new Trend("review_due_query_count");
const dueQueryTime = new Trend("review_due_query_time_ms");
const statsLatency = new Trend("review_stats_duration");
const statsQueryCount = new Trend("review_stats_query_count");
const statsQueryTime = new Trend("review_stats_query_time_ms");
const submitLatency = new Trend("review_submit_duration");
const submitQueryCount = new Trend("review_submit_query_count");
const submitQueryTime = new Trend("review_submit_query_time_ms");

export const options = {
  vus: Number(__ENV.K6_VUS || 2),
  duration: __ENV.K6_DURATION || "20s",
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

function parseMetricHeader(response, headerName) {
  const rawValue = response.headers[headerName];
  if (!rawValue) {
    return null;
  }
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : null;
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
  });

  return ok ? response.json() : null;
}

function loadDueItems(token, limit) {
  const response = http.get(`${baseUrl}/reviews/queue/due?limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  dueLatency.add(response.timings.duration);
  const headerQueryCount = parseMetricHeader(response, "X-Reviews-Query-Count");
  const headerQueryTime = parseMetricHeader(response, "X-Reviews-Query-Time-Ms");
  if (headerQueryCount !== null) {
    dueQueryCount.add(headerQueryCount);
  }
  if (headerQueryTime !== null) {
    dueQueryTime.add(headerQueryTime);
  }
  return response;
}

function statsFlow(token) {
  const response = http.get(`${baseUrl}/reviews/queue/stats`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  statsLatency.add(response.timings.duration);
  const headerQueryCount = parseMetricHeader(response, "X-Reviews-Query-Count");
  const headerQueryTime = parseMetricHeader(response, "X-Reviews-Query-Time-Ms");
  if (headerQueryCount !== null) {
    statsQueryCount.add(headerQueryCount);
  }
  if (headerQueryTime !== null) {
    statsQueryTime.add(headerQueryTime);
  }
  const ok = check(response, {
    "stats status 200": (r) => r.status === 200,
  });
  flowFailureRate.add(!ok);
  statsFailureRate.add(!ok);
}

function buildSubmitPayload(item) {
  const prompt = item.prompt || {};
  const payload = {
    quality: 2,
    time_spent_ms: 1200,
    audio_replay_count: 0,
    prompt_token: prompt.prompt_token,
  };

  if (prompt.input_mode === "confidence") {
    payload.outcome = "lookup";
    return payload;
  }
  if (prompt.input_mode === "typed" || prompt.input_mode === "speech_placeholder") {
    payload.typed_answer = "__benchmark_wrong__";
    return payload;
  }
  payload.selected_option_id = "Z";
  return payload;
}

function submitFlow(token) {
  const dueResponse = loadDueItems(token, 1);
  if (dueResponse.status !== 200) {
    flowFailureRate.add(true);
    submitFailureRate.add(true);
    return;
  }

  const dueItems = dueResponse.json();
  if (!Array.isArray(dueItems) || dueItems.length === 0) {
    flowFailureRate.add(true);
    submitFailureRate.add(true);
    emptyDueRate.add(true);
    return;
  }
  emptyDueRate.add(false);

  const item = dueItems[0];
  const submitResponse = http.post(
    `${baseUrl}/reviews/queue/${item.id}/submit`,
    JSON.stringify(buildSubmitPayload(item)),
    { headers: jsonHeaders(token) },
  );
  submitLatency.add(submitResponse.timings.duration);
  const headerQueryCount = parseMetricHeader(submitResponse, "X-Reviews-Query-Count");
  const headerQueryTime = parseMetricHeader(submitResponse, "X-Reviews-Query-Time-Ms");
  if (headerQueryCount !== null) {
    submitQueryCount.add(headerQueryCount);
  }
  if (headerQueryTime !== null) {
    submitQueryTime.add(headerQueryTime);
  }
  const ok = check(submitResponse, {
    "submit status 200": (r) => r.status === 200,
  });
  flowFailureRate.add(!ok);
  submitFailureRate.add(!ok);
}

function dueFlow(token) {
  const response = loadDueItems(token, 20);
  const ok = check(response, {
    "due status 200": (r) => r.status === 200,
  });
  flowFailureRate.add(!ok);
  dueFailureRate.add(!ok);
}

export function setup() {
  const tokens = login(userEmail, userPassword);
  if (!tokens) {
    throw new Error("review benchmark setup login failed");
  }

  return {
    userAccessToken: tokens.access_token,
  };
}

export default function (data) {
  const roll = Math.random();

  if (roll < 0.20) {
    statsFlow(data.userAccessToken);
  } else if (roll < 0.75) {
    dueFlow(data.userAccessToken);
  } else {
    submitFlow(data.userAccessToken);
  }

  sleep(1);
}

export function handleSummary(data) {
  const outputPath = __ENV.K6_SUMMARY_PATH || "benchmarks/results/review-dev-summary.json";
  return {
    [outputPath]: JSON.stringify(data, null, 2),
  };
}
