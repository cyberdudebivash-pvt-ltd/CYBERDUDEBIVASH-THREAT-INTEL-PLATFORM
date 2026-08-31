// General capability-gate upsell -- states what Sentinel Pro unlocks as a
// tier-wide capability (true regardless of which specific CVE/actor page
// this renders on), not a claim that specific hidden data exists for
// *this* item. Blurred lines below are illustrative placeholders (this
// is a static page with no per-item paywall signal to key off, unlike
// lookup.html's teaser, which conditions on real *_paywall stubs the
// live /api/feed route attaches server-side) -- copy is deliberately
// general ("Pro unlocks X for every CVE"), not a specific, possibly-false
// claim ("we found an active exploit for this exact CVE").
//
// Checkout links go through GET /api/billing/checkout (workers/intel-
// gateway/src/billing-checkout.js), which redirects to the real, live
// Gumroad (USD) / Razorpay-via-upgrade.html (INR) destination -- never a
// hardcoded gateway URL.

const API_BASE = "https://intel.cyberdudebivash.com";

export function ProTelemetryTeaser({ contextLabel, refTag }: { contextLabel: string; refTag: string }) {
  return (
    <section className="rounded-xl border border-dashed border-gray-700 bg-gray-900/40 overflow-hidden">
      <div
        aria-hidden="true"
        className="p-5 font-mono text-xs text-gray-600 leading-loose blur-[5px] select-none pointer-events-none"
      >
        c2_ip: ██.██.██.██
        <br />
        mitre_sub_technique: T15██.███
        <br />
        yara_rule: rule SENTINEL_████ {"{ ... }"}
        <br />
        weaponization_status: ████████████
      </div>
      <div className="relative -mt-24 p-5 pt-0 flex flex-col items-center text-center gap-3 bg-gradient-to-t from-gray-900/95 via-gray-900/80 to-transparent">
        <h3 className="text-sm font-semibold text-white">Unlock Full {contextLabel} Telemetry</h3>
        <p className="text-xs text-gray-400 max-w-sm">
          Sentinel Pro unlocks active weaponization exploit tracking, matched YARA/Sigma detection rules, and full
          STIX 2.1 export for every CVE and threat actor — not just this one.
        </p>
        <div className="flex gap-2 flex-wrap justify-center">
          <a
            href={`${API_BASE}/api/billing/checkout?tier=pro&currency=usd&ref=${refTag}`}
            className="px-4 py-2 rounded-lg bg-cyan-500 text-gray-950 font-semibold text-xs hover:bg-cyan-400 transition-colors"
          >
            Upgrade — $49/mo
          </a>
          <a
            href={`${API_BASE}/api/billing/checkout?tier=pro&currency=inr&ref=${refTag}`}
            className="px-4 py-2 rounded-lg border border-cyan-500/40 text-cyan-400 font-semibold text-xs hover:bg-cyan-500/10 transition-colors"
          >
            ₹4,100/mo (India)
          </a>
        </div>
      </div>
    </section>
  );
}
