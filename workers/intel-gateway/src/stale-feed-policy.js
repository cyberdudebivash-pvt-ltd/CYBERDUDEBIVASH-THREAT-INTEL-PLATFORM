/**
 * P0 R36: hard denial boundary for live intelligence API responses.
 *
 * Never returns the stored historical/stale item list in a LIVE route.
 * The origin feed is not mutated; historical archives remain separate.
 */
import { publicationEnvelope } from "./freshness-contract.js";

export function denyNonFreshLiveFeed(feed, nowMs = Date.now()) {
  const truth = publicationEnvelope(feed, nowMs, 0);
  if (truth.evaluation.healthy) return null;
  return {
    status: 503,
    headers: {
      ...truth.headers,
      "Cache-Control": "no-store, max-age=0",
      "Pragma": "no-cache",
      "X-Content-Type-Options": "nosniff",
    },
    body: {
      error: "live_intelligence_unavailable",
      reason: truth.evaluation.reason || "freshness_unverified",
      publication_state: truth.fields.publication_state,
      freshness_status: truth.fields.freshness_status,
      freshness_reason: truth.fields.freshness_reason,
      generated_at: truth.evaluation.intelligence.generated_at,
      age_seconds: truth.fields.age_seconds,
      max_age_seconds: truth.fields.max_age_seconds,
      items: [],
      count: 0,
      live_data_available: false,
      // A previously published item list can still exist in storage, but it
      // is never returned to live consumers until authoritative recovery.
      message: "No verified fresh threat intelligence is currently available.",
    },
  };
}
