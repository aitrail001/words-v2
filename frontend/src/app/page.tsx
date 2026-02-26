"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

type HealthStatus = {
  status: string;
  database: string;
  redis: string;
} | null;

export default function Home() {
  const [health, setHealth] = useState<HealthStatus>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<HealthStatus>("/health")
      .then(setHealth)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 font-medium">System Health</h3>
        {error && <p className="text-red-600">Backend unreachable: {error}</p>}
        {health && (
          <dl className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <dt className="text-gray-500">Status</dt>
              <dd className="font-mono">{health.status}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Database</dt>
              <dd className="font-mono">{health.database}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Redis</dt>
              <dd className="font-mono">{health.redis}</dd>
            </div>
          </dl>
        )}
        {!health && !error && <p className="text-gray-400">Checking...</p>}
      </div>
    </div>
  );
}
