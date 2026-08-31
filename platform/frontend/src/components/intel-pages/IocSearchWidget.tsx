"use client";

import { useState } from "react";

// Calls the real, live GET /api/v1/ioc/lookup route (workers/intel-gateway/
// src/index.js) directly from the browser -- no server action, no mock
// data. Same route lookup.html (repo root) already uses for its public
// sandbox search. `prefill` seeds the input with the current page's CVE
// ID / actor name so a visitor lands with a relevant query already typed.

interface LookupResult {
  found: boolean;
  query: string;
  results: Array<{
    id: string;
    title: string;
    severity: string;
    risk_score: number;
    source: string;
    published: string;
    cve_ids: string[];
    ioc_count: number;
  }>;
  total_iocs_checked: number;
}

const API_BASE = "https://intel.cyberdudebivash.com";

export function IocSearchWidget({ prefill }: { prefill: string }) {
  const [query, setQuery] = useState(prefill);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LookupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/ioc/lookup?q=${encodeURIComponent(q)}`);
      if (res.status === 429) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message || "Daily lookup quota reached. Upgrade for higher limits.");
      }
      if (!res.ok) throw new Error(`Lookup failed (${res.status})`);
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong reaching the live feed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900/40 p-6">
      <h2 className="text-base font-semibold text-white mb-1">Instant IOC Analysis</h2>
      <p className="text-xs text-gray-500 mb-4">
        Free, unauthenticated lookup against the live SENTINEL APEX threat feed — no API key required.
      </p>
      <form onSubmit={runSearch} className="flex gap-2 mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="CVE ID, IP, domain, or hash"
          className="flex-1 bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-cyan-500 text-gray-950 font-semibold text-sm hover:bg-cyan-400 transition-colors disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {result && !error && (
        result.results.length === 0 ? (
          <p className="text-xs text-gray-500">No matches for &ldquo;{result.query}&rdquo; in the live feed.</p>
        ) : (
          <ul className="space-y-2">
            {result.results.map((r) => (
              <li key={r.id} className="rounded-lg bg-gray-800/60 border border-gray-700 p-3">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm text-white font-medium truncate">{r.title}</span>
                  <span className="text-xs text-gray-500 flex-shrink-0">{r.severity}</span>
                </div>
                <p className="text-xs text-gray-500">Risk {r.risk_score}/10 · {r.source} · {r.published}</p>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}
