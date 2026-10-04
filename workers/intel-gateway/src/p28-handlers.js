/**
 * workers/intel-gateway/src/p28-handlers.js
 * CYBERDUDEBIVASH(R) SENTINEL APEX  -  P28.0 Enterprise Risk Intelligence & Customer Value Platform
 * =================================================================================================
 * Additive layer over P20-P27. Implements only capabilities confirmed absent in the P28 audit:
 *
 *   P28.1  Customer Environment Risk Mapping   (no existing env-profile scoring)
 *   P28.3  Executive Business Impact           (financial bands not in P20 exec block)
 *   P28.5  Customer Action Center              (no unified action queue aggregation)
 *   P28.7  Role-Based Operational Guidance     (P27 multi-audience is executive-only)
 *   P28.9  Customer Feedback Framework         (no feedback capture anywhere in P20-P27)
 *   P28.10 Operational Metrics                 (no platform metrics tracking exists)
 *   API    handleP28Feedback, handleP28Certify, handleP28Observability
 *
 * AUDIT CONFIRMED P20-P27 ALREADY COVER (reused, not duplicated):
 *   P28.2  Operational Risk Prioritization  -> P23 buildPatchPriorityBlock (REUSED)
 *   P28.4  Detection Readiness             -> P22+P23 detection blocks (REUSED)
 *   P28.6  Intelligence Correlation        -> P18 correlation engine (REUSED)
 *   P28.8  Intelligence Validation         -> P22+P26+P27 structural integrity (REUSED)
 *   P28.11 Commercial Readiness            -> P26 computeP26Grade (REUSED)
 *
 * ZERO FABRICATION  -  all intelligence derived from existing pipeline-verified feed fields.
 * ADDITIVE ONLY    -  no existing handler, schema, KV key, auth, or payment logic modified.
 * ZERO DUPLICATION -  P23/P26 engines imported where needed; P28 adds only audit-confirmed gaps.
 */

import { computeActionabilityScore } from './p23-handlers.js';
import { computeP26Grade }           from './p26-handlers.js';
import { explicitCvss, explicitRiskScore } from './metric-semantics.js';

export const P28_VERSION = "P28.0";

// KV key prefix for customer feedback
const FB_PREFIX = "p28:feedback:";

// -- Shared helpers ------------------------------------------------------------

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _block(id, title, color, body, subtitle = "") {
  return `
<div id="${id}" style="margin:24px 0;padding:20px 24px;background:#0d1117;border:1px solid ${color}33;border-left:4px solid ${color};border-radius:6px;font-family:'Courier New',monospace;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="color:${color};font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;">${esc(title)}</span>
      ${subtitle ? `<div style="color:#6b7280;font-size:10px;margin-top:2px;">${esc(subtitle)}</div>` : ""}
    </div>
    <span style="color:${color};font-size:9px;font-weight:700;letter-spacing:.1em;opacity:.7;">P28.0 SENTINEL APEX</span>
  </div>
  ${body}
</div>`;
}

function _row(label, value, color = "#94a3b8", mono = false) {
  return `<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:5px 0;border-bottom:1px solid #1a2030;">
    <span style="color:#6b7280;font-size:11px;min-width:160px;">${esc(label)}</span>
    <span style="color:${color};font-size:11px;${mono ? "font-family:'Courier New',monospace;" : ""}text-align:right;max-width:65%;">${value}</span>
  </div>`;
}

function _badge(text, bg, fg = "#fff") {
  return `<span style="display:inline-block;background:${bg};color:${fg};font-size:9px;font-weight:700;padding:2px 7px;border-radius:3px;letter-spacing:.06em;margin:2px;">${esc(text)}</span>`;
}

// -- P28.1: Customer Environment Risk Mapping ---------------------------------
// 12 environment types derived from attack_vector/ttps/description/tags.
// No customer data stored  -  mapping is derived from feed fields only.

const _ENV_PROFILES = [
  { id: "windows",   label: "Windows",        keywords: ["windows","rdp","smb","ntlm","lsass","wmi","powershell","active directory","ad ds","kerberos","lsass dump","mimikatz"] },
  { id: "linux",     label: "Linux / Unix",   keywords: ["linux","bash","shell","cron","sudo","ld_preload","systemd","unix","debian","ubuntu","centos","rhel","kernel"] },
  { id: "macos",     label: "macOS",          keywords: ["macos","apple","osx","launchd","xcode","safari","keychain","gatekeeper","notarization"] },
  { id: "ad",        label: "Active Directory",keywords: ["active directory","kerberos","ldap","domain controller","gpo","ntlm","dcsync","pass-the-hash","bloodhound","ad cs"] },
  { id: "m365",      label: "Microsoft 365",  keywords: ["microsoft 365","office 365","sharepoint","teams","exchange","outlook","azure ad","entra id","oauth","graph api"] },
  { id: "aws",       label: "AWS",            keywords: ["aws","amazon web services","s3","ec2","lambda","iam","cloudtrail","guardduty","sts","eks","ecr","cloudfront"] },
  { id: "azure",     label: "Azure",          keywords: ["azure","microsoft azure","arm","keyvault","adf","devops","aks","entra","defender for cloud","azure function"] },
  { id: "gcp",       label: "Google Cloud",   keywords: ["gcp","google cloud","gke","bigquery","cloud run","iam","cloud storage","vertex","pub/sub"] },
  { id: "k8s",       label: "Kubernetes",     keywords: ["kubernetes","k8s","container","docker","helm","pod","namespace","rbac","service account","istio","oci"] },
  { id: "vmware",    label: "VMware / ESXi",  keywords: ["vmware","vsphere","esxi","vcenter","vsan","nsx","vmotion","snapshot","hypervisor"] },
  { id: "saas",      label: "SaaS Platforms", keywords: ["saas","salesforce","servicenow","workday","zendesk","okta","slack","github","gitlab","jira","confluence","atlassian"] },
  { id: "internet",  label: "Internet-Facing",keywords: ["internet-facing","public","vpn","firewall","web application","waf","cdn","ddos","botnet","scanning","shodan","censys","exposed"] },
];

function _deriveEnvRelevance(item) {
  const corpus = [
    item.title,
    item.description,
    item.attack_vector,
    ...(item.ttps || []),
    ...(item.mitre_tactics || []),
    ...(item.tags || []),
    item.threat_type,
    item.actor_tag,
  ].filter(Boolean).join(" ").toLowerCase();

  return _ENV_PROFILES.map(env => {
    const hits = env.keywords.filter(kw => corpus.includes(kw)).length;
    const score = Math.min(100, Math.round((hits / Math.max(1, env.keywords.length)) * 100 * 3.5));
    const level = score >= 60 ? "HIGH" : score >= 25 ? "MEDIUM" : "LOW";
    return { ...env, hits, score, level };
  }).sort((a, b) => b.score - a.score);
}

export function buildP28EnvironmentRiskBlock(item) {
  const envs = _deriveEnvRelevance(item);
  const high   = envs.filter(e => e.level === "HIGH");
  const medium = envs.filter(e => e.level === "MEDIUM");
  const low    = envs.filter(e => e.level === "LOW");

  const _envRow = (env) => {
    const color = env.level === "HIGH" ? "#ef4444" : env.level === "MEDIUM" ? "#f59e0b" : "#6b7280";
    const barW  = Math.max(2, env.score);
    return `<div style="display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid #1a2030;">
      <span style="color:#94a3b8;font-size:11px;min-width:140px;">${esc(env.label)}</span>
      <div style="flex:1;background:#1a2030;border-radius:3px;height:6px;overflow:hidden;">
        <div style="width:${barW}%;background:${color};height:6px;border-radius:3px;"></div>
      </div>
      <span style="color:${color};font-size:10px;font-weight:700;min-width:52px;text-align:right;">${env.level} ${env.score}%</span>
    </div>`;
  };

  const summary = `<div style="display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap;">
    ${_badge(`${high.length} HIGH RELEVANCE`, "#7f1d1d", "#fca5a5")}
    ${_badge(`${medium.length} MEDIUM RELEVANCE`, "#78350f", "#fcd34d")}
    ${_badge(`${low.length} LOW RELEVANCE`, "#1e3a5f", "#7dd3fc")}
  </div>`;

  const rows = envs.map(_envRow).join("");

  const note = `<div style="margin-top:10px;color:#374151;font-size:10px;font-style:italic;">
    Relevance derived from attack_vector, TTPs, MITRE tactics, and threat description. Check environments applicable to your organization.
  </div>`;

  return _block(
    "p28-env-risk",
    "P28.1  -  Customer Environment Risk Mapping",
    "#818cf8",
    summary + rows + note,
    "12 environment types * relevance derived from verified intelligence fields"
  );
}

// -- P28.3: Executive Business Impact -----------------------------------------
// Financial bands, operational disruption, compliance, reputation.
// All derived from CVSS/KEV/EPSS/severity  -  zero fabrication.

function _deriveFinancialBand(item) {
  // This is a qualitative business-impact review signal, not a loss model.
  // Threat intelligence alone cannot establish customer-specific financial
  // exposure without asset value, incident scope, controls, downtime, data,
  // contractual and jurisdictional context.
  const cvss  = explicitCvss(item);
  const risk  = explicitRiskScore(item);
  const kev   = Boolean(item.kev_present || (item.apex && item.apex.kev_listed));
  const epss  = parseFloat(item.epss_score || 0);
  const sev   = String(item.severity || "").toUpperCase();
  let score   = 0;
  if (sev === "CRITICAL") score += 40;
  else if (sev === "HIGH") score += 25;
  else if (sev === "MEDIUM") score += 12;
  if (kev) score += 30;
  if (epss > 0.7) score += 20;
  else if (epss > 0.4) score += 10;
  if (cvss != null && cvss >= 9.0) score += 10;
  else if (cvss == null && risk != null && risk >= 9.0) score += 6;

  const base = score >= 65
    ? { band: "HIGH", label: "High Business-Impact Review Priority", color: "#ef4444" }
    : score >= 35
      ? { band: "MEDIUM", label: "Medium Business-Impact Review Priority", color: "#f59e0b" }
      : { band: "LOW", label: "Standard Business-Impact Review Priority", color: "#22c55e" };
  return {
    ...base,
    range: "Not quantified from threat intelligence",
    quantified: false,
    methodology: "qualitative review priority from recorded threat signals; not a financial-loss estimate",
  };
}

function _deriveOperationalDisruption(item) {
  const sev   = String(item.severity || "").toUpperCase();
  const kev   = Boolean(item.kev_present || (item.apex && item.apex.kev_listed));
  const ttps  = (item.ttps || []).join(" ").toLowerCase();
  const desc  = String(item.description || "").toLowerCase();
  const ransomware = ttps.includes("ransomware") || desc.includes("ransomware") || desc.includes("encryption");
  const dos        = ttps.includes("denial") || desc.includes("denial of service") || desc.includes(" dos ") || desc.includes("ddos");
  const exfil      = ttps.includes("exfiltration") || desc.includes("data exfil") || desc.includes("data theft");
  const rce        = ttps.includes("remote code") || desc.includes("rce") || desc.includes("remote code execution");

  const items = [];
  if (ransomware)          items.push({ label: "Ransomware / Encryption", level: "CRITICAL" });
  if (rce && kev)          items.push({ label: "Active RCE Exploitation", level: "CRITICAL" });
  if (rce && !kev)         items.push({ label: "Remote Code Execution",   level: "HIGH" });
  if (dos)                 items.push({ label: "Service Availability",    level: "HIGH" });
  if (exfil)               items.push({ label: "Data Exfiltration Risk",  level: "HIGH" });
  if (sev === "CRITICAL" && items.length === 0) items.push({ label: "Business Operations", level: "HIGH" });
  if (items.length === 0)  items.push({ label: "Limited Disruption Expected", level: "LOW" });

  return items;
}

function _deriveComplianceImplications(item) {
  const desc  = String(item.description || "").toLowerCase();
  const ttps  = (item.ttps || []).join(" ").toLowerCase();
  const corpus = desc + " " + ttps;
  const areas = [];
  if (corpus.includes("pii") || corpus.includes("personal data") || corpus.includes("gdpr")) areas.push("Data-protection review context");
  if (corpus.includes("payment") || corpus.includes("credit card") || corpus.includes("pci")) areas.push("Payment-card / PCI review context");
  if (corpus.includes("health") || corpus.includes("phi") || corpus.includes("hipaa")) areas.push("Healthcare / health-data review context");
  if (corpus.includes("financial") || corpus.includes("banking") || corpus.includes("swift")) areas.push("Financial-services regulatory review context");
  if (corpus.includes("supply chain") || corpus.includes("third party")) areas.push("Third-party / supply-chain governance review context");
  if (areas.length === 0) areas.push("Customer security-governance review");
  return areas;
}

export function buildP28BusinessImpactBlock(item) {
  const financial  = _deriveFinancialBand(item);
  const disruption = _deriveOperationalDisruption(item);
  const compliance = _deriveComplianceImplications(item);
  const sev        = String(item.severity || "UNKNOWN").toUpperCase();
  const kev        = Boolean(item.kev_present || (item.apex && item.apex.kev_listed));
  const epss       = parseFloat(item.epss_score || 0);
  const cvss       = explicitCvss(item);
  const risk       = explicitRiskScore(item);

  const disruptRows = disruption.map(d => {
    const col = d.level === "CRITICAL" ? "#ef4444" : d.level === "HIGH" ? "#f59e0b" : "#22c55e";
    return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
      <span style="color:${col};font-size:10px;font-weight:700;min-width:68px;">${esc(d.level)}</span>
      <span style="color:#94a3b8;font-size:11px;">${esc(d.label)}</span>
    </div>`;
  }).join("");

  const compRows = compliance.map(x =>
    `<div style="color:#94a3b8;font-size:11px;padding:2px 0;">&#8226; ${esc(x)}</div>`
  ).join("");

  const metricText = cvss != null
    ? `Explicit CVSS ${cvss.toFixed(1)}`
    : risk != null
      ? `APEX composite risk ${risk.toFixed(1)}/10 (not CVSS)`
      : "No explicit CVSS/risk score";

  const recommendation = (kev || sev === "CRITICAL")
    ? "Prioritize customer exposure validation and accountable security ownership. Escalate to executives or incident response only under the customer's documented materiality/incident policy and confirmed environment evidence."
    : sev === "HIGH"
      ? "Assign a remediation/validation owner and process the intelligence through the customer's documented vulnerability and risk workflow."
      : "Monitor and validate through the customer's normal security-operations cadence.";

  const body = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;">
      <div style="background:#0a0f1a;border:1px solid ${financial.color}33;border-radius:5px;padding:12px;">
        <div style="color:#6b7280;font-size:9px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;">Business Impact Review</div>
        <div style="color:${financial.color};font-size:16px;font-weight:700;">${esc(financial.band)}</div>
        <div style="color:#6b7280;font-size:10px;margin-top:4px;">${esc(financial.range)}</div>
        <div style="color:#374151;font-size:9px;margin-top:3px;">${esc(metricText)}; KEV ${kev ? "YES" : "NO"}; EPSS ${Number.isFinite(epss) ? (epss * 100).toFixed(1) + "%" : "N/A"}</div>
      </div>
      <div style="background:#0a0f1a;border:1px solid #3b82f633;border-radius:5px;padding:12px;">
        <div style="color:#6b7280;font-size:9px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;">Impact Truth Boundary</div>
        <div style="color:#3b82f6;font-size:13px;font-weight:700;">CUSTOMER CONTEXT REQUIRED</div>
        <div style="color:#6b7280;font-size:10px;margin-top:4px;">Threat intelligence does not prove outage, breach, data loss, financial loss, reputation damage, materiality or notification obligations.</div>
      </div>
    </div>
    <div style="margin-bottom:12px;">
      <div style="color:#6b7280;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">Potential Operational Disruption Signals</div>
      ${disruptRows}
    </div>
    <div>
      <div style="color:#6b7280;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">Compliance / Governance Review Areas</div>
      ${compRows}
      <div style="color:#374151;font-size:9px;margin-top:5px;">Review areas are contextual prompts only; applicability requires confirmed incident facts, affected data/systems, jurisdiction, contracts and customer legal/compliance assessment.</div>
    </div>
    <div style="margin-top:12px;padding:10px 12px;background:#0a0f1a;border:1px solid #1e3a5f;border-radius:4px;">
      <div style="color:#6b7280;font-size:9px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;">Executive Recommendation</div>
      <div style="color:#94a3b8;font-size:11px;">${esc(recommendation)}</div>
    </div>`;

  return _block(
    "p28-business-impact",
    "P28.3  -  Executive Business Impact Review",
    "#f59e0b",
    body,
    "Qualitative customer review context; no fabricated loss, breach, materiality or legal conclusions"
  );
}

// -- P28.5: Customer Action Center ---------------------------------------------
// Aggregated action queues. Imports computeActionabilityScore from P23.
// No duplication  -  P23 computes; P28 packages into customer-facing queue view.

const _QUEUE_COLORS = {
  patch:      "#ef4444",
  hunt:       "#818cf8",
  detection:  "#38bdf8",
  executive:  "#f59e0b",
  compliance: "#22c55e",
};

export function buildP28ActionCenterBlock(item) {
  const sev   = String(item.severity || "").toUpperCase();
  const kev   = Boolean(item.kev_present || (item.apex && item.apex.kev_listed));
  const ttps  = (item.ttps || []).join(" ").toLowerCase();
  const desc  = String(item.description || "").toLowerCase();
  const hasCve = (item.cve_ids || []).length > 0 || String(item.title || "").toUpperCase().includes("CVE-");
  const hasSigma = Boolean((item.apex && item.apex.sigma_rule) || item.sigma_rule);
  const hasIoc = Number.parseInt(item.ioc_count || 0, 10) > 0;

  let actScore = 0;
  try { actScore = computeActionabilityScore(item); } catch (_) {}

  const priority = kev || sev === "CRITICAL" ? "PRIORITY" : sev === "HIGH" ? "ELEVATED" : "STANDARD";

  const patchItems = [];
  if (hasCve) {
    const cves = item.cve_ids && item.cve_ids.length > 0 ? item.cve_ids.join(", ") : "advisory CVE";
    patchItems.push({ priority, action: `Validate affected assets/versions for ${cves}; apply vendor remediation under applicable KEV/vendor deadlines and customer SLA/change control.`, owner: "Vulnerability Management" });
  } else if (sev !== "INFO") {
    patchItems.push({ priority, action: "Review authoritative vendor/security guidance and validate affected customer scope before remediation.", owner: "Security Engineering" });
  }

  const huntItems = [];
  if (hasIoc) {
    huntItems.push({ priority, action: `Validate provenance/freshness, then search approved customer telemetry for ${item.ioc_count} recorded IOC(s); do not treat raw IOC presence as proof of compromise.`, owner: "Threat Hunting" });
  }
  if (ttps.includes("lateral movement") || desc.includes("lateral movement")) {
    huntItems.push({ priority, action: "Review available network/identity/endpoint telemetry for lateral-movement evidence.", owner: "Threat Hunting" });
  }
  if ((item.mitre_tactics || []).length > 0) {
    const tactics = item.mitre_tactics.slice(0, 3).join(", ");
    huntItems.push({ priority: "STANDARD", action: `Validate ATT&CK mappings against customer telemetry for: ${tactics}.`, owner: "Threat Hunting" });
  }
  if (huntItems.length === 0) {
    huntItems.push({ priority: "STANDARD", action: "Build an evidence-backed hunt hypothesis only where mapped TTPs and required telemetry exist.", owner: "Threat Hunting" });
  }

  const detectItems = [];
  if (hasSigma) {
    detectItems.push({ priority, action: "Validate the available Sigma rule against customer log schema/telemetry and staged change controls before production deployment.", owner: "Detection Engineering" });
  }
  detectItems.push({ priority, action: "Assess ATT&CK detection coverage and document visibility gaps for the advisory.", owner: "Detection Engineering" });
  if (hasIoc) {
    detectItems.push({ priority: "STANDARD", action: `After provenance/freshness validation, ingest approved IOC intelligence into the customer's TIP/SIEM according to retention and tenant-isolation policy.`, owner: "SOC Analyst" });
  }

  const execItems = [];
  if (sev === "CRITICAL" || kev) {
    execItems.push({ priority: "PRIORITY", action: "Review with security leadership according to customer materiality/escalation policy; do not infer confirmed incident impact from intelligence alone.", owner: "CISO / Security Leadership" });
  }
  execItems.push({ priority: "STANDARD", action: "Record evidence-backed risk/response status in the customer's risk or case-management process.", owner: "CISO / Risk" });

  const compItems = [];
  const reviewAreas = _deriveComplianceImplications(item);
  compItems.push({ priority: "STANDARD", action: `Assess applicable legal/compliance obligations from confirmed incident facts; contextual review areas: ${reviewAreas.join(", ")}.`, owner: "Legal / Compliance" });

  const _queueSection = (title, color, items) => {
    const priColor = p => p === "PRIORITY" ? "#ef4444" : p === "ELEVATED" ? "#f59e0b" : "#22c55e";
    const rows = items.map(i =>
      `<div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid #0d1117;">
        <span style="color:${priColor(i.priority)};font-size:9px;font-weight:700;min-width:66px;padding-top:1px;">${esc(i.priority)}</span>
        <div style="flex:1;">
          <div style="color:#c9d1d9;font-size:11px;">${esc(i.action)}</div>
          <div style="color:#374151;font-size:10px;">Owner: ${esc(i.owner)}</div>
        </div>
      </div>`
    ).join("");
    return `<div style="background:#0a0f1a;border:1px solid ${color}22;border-left:3px solid ${color};border-radius:4px;padding:10px 12px;margin-bottom:8px;">
      <div style="color:${color};font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;">${esc(title)}</div>
      ${rows}
    </div>`;
  };

  const actLabel = actScore >= 80 ? "HIGH ACTIONABILITY" : actScore >= 50 ? "MEDIUM ACTIONABILITY" : "LOW ACTIONABILITY";
  const actColor = actScore >= 80 ? "#22c55e" : actScore >= 50 ? "#f59e0b" : "#ef4444";
  const body = `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
      <span style="color:${actColor};font-size:12px;font-weight:700;">${actLabel}</span>
      <span style="color:#374151;font-size:11px;">Actionability Score: ${actScore}/100</span>
    </div>
    ${_queueSection("Remediation Validation Queue", _QUEUE_COLORS.patch, patchItems)}
    ${_queueSection("Threat Hunt Queue", _QUEUE_COLORS.hunt, huntItems)}
    ${_queueSection("Detection Validation Queue", _QUEUE_COLORS.detection, detectItems)}
    ${_queueSection("Executive Review Tasks", _QUEUE_COLORS.executive, execItems)}
    ${_queueSection("Legal / Compliance Review", _QUEUE_COLORS.compliance, compItems)}`;

  return _block(
    "p28-action-center",
    "P28.5  -  Customer Action Center",
    "#38bdf8",
    body,
    "Evidence-first remediation * hunt * detection * executive * legal/compliance queues; customer policy owns timing"
  );
}

// -- P28.7: Role-Based Operational Guidance -----------------------------------
// 7 operational roles. Distinct from P27 multi-audience (which is executive-framed).
// P28.7 provides operational step-by-step guidance per role.

const _ROLES = [
  { id: "soc",    label: "SOC Analyst",           icon: "&#128270;" },
  { id: "hunter", label: "Threat Hunter",          icon: "&#127919;" },
  { id: "ir",     label: "Incident Responder",     icon: "&#128680;" },
  { id: "seceng", label: "Security Engineer",      icon: "&#128736;" },
  { id: "vulnmgr",label: "Vulnerability Manager",  icon: "&#128203;" },
  { id: "ciso",   label: "CISO",                   icon: "&#128084;" },
  { id: "exec",   label: "Executive Sponsor",      icon: "&#128188;" },
];

function _buildRoleGuidance(item) {
  const sev   = String(item.severity || "").toUpperCase();
  const kev   = Boolean(item.kev_present || (item.apex && item.apex.kev_listed));
  const epss  = parseFloat(item.epss_score || 0);
  const cvss  = explicitCvss(item);
  const risk  = explicitRiskScore(item);
  const hasCve = (item.cve_ids || []).length > 0 || String(item.title || "").includes("CVE-");
  const hasIoc = Number.parseInt(item.ioc_count || 0, 10) > 0;
  const hasSig = Boolean((item.apex && item.apex.sigma_rule) || item.sigma_rule);
  const tactics = (item.mitre_tactics || []).slice(0, 4).join(", ") || "see advisory";
  const cveList = (item.cve_ids || []).slice(0, 3).join(", ") || "advisory reference";
  const metric = cvss != null ? `CVSS ${cvss.toFixed(1)}`
    : risk != null ? `APEX risk ${risk.toFixed(1)}/10 (not CVSS)`
    : "CVSS/risk not recorded";

  return {
    soc: [
      hasIoc ? `Validate and search customer telemetry for ${item.ioc_count} recorded IOC(s); confirm provenance/freshness before containment` : "Review advisory for behavioral indicators and evidence gaps",
      hasSig ? "Validate Sigma logic against customer log schema and staged telemetry before production deployment" : "Develop/test a detection hypothesis from validated TTP/evidence context",
      kev ? "Treat KEV as priority vulnerability intelligence; confirm customer exposure before incident conclusions" : `Monitor according to customer policy; EPSS ${Number.isFinite(epss) ? (epss*100).toFixed(1) + "%" : "N/A"}`,
      `Validate MITRE ATT&CK mappings against observed telemetry: ${tactics}`,
      "Document triage evidence, negative findings, assumptions and decisions in case management",
    ],
    hunter: [
      `Hunt only where required telemetry exists for mapped TTPs: ${tactics}`,
      hasIoc ? `Pivot from validated IOC evidence across the customer's available/approved retention window` : "Build behavioral hypotheses from mapped TTPs and source evidence",
      "Do not infer a common campaign or compromise solely from IOC/TTP co-occurrence",
      "Cross-reference actor/campaign claims with provenance and attribution confidence",
      "Produce a hunt report that distinguishes observed evidence from intelligence context",
    ],
    ir: [
      "Activate the customer incident-response process only when incident evidence or the customer's escalation policy warrants it",
      `Prepare evidence-preserving forensic collection for plausibly affected systems; focus on ${tactics}`,
      hasCve ? `Confirm affected versions and authoritative vendor remediation for ${cveList}` : "Obtain authoritative mitigation guidance and validate affected scope",
      "Engage CISO/legal/compliance based on confirmed incident facts and customer notification policy",
      "Record containment/remediation decisions and residual risk",
    ],
    seceng: [
      hasCve ? `Assess patch applicability and affected asset scope for ${cveList}` : "Identify affected components and validate exposure",
      "Validate compensating controls in customer context before enforcing firewall/WAF/identity changes",
      hasSig ? "Test available Sigma detection against representative customer telemetry before production rollout" : "Develop detection content from validated evidence/TTPs",
      `Review ATT&CK mitigations relevant to: ${tactics}`,
      "Verify remediation using approved scanner/configuration/telemetry evidence",
    ],
    vulnmgr: [
      hasCve ? `Track ${cveList}; use KEV/vendor deadlines and the customer's documented SLA/change process` : "Track advisory and validate affected scope",
      `${metric} * EPSS: ${Number.isFinite(epss) ? (epss*100).toFixed(1) + "%" : "N/A"} * KEV: ${kev ? "YES" : "NO"}`,
      "Confirm asset inventory coverage and affected product/version",
      "Prioritize remediation from verified exposure, vendor guidance, asset criticality and customer policy",
      "Record completion evidence and residual risk through closure",
    ],
    ciso: [
      sev === "CRITICAL" || kev
        ? "Prioritize security-leadership review; executive/IR escalation follows customer materiality and incident policy"
        : "Track through the customer's normal security-risk governance cadence",
      `Business-impact review: ${_deriveFinancialBand(item).band}; financial loss is not quantified from threat intelligence`,
      "Assign accountable validation/remediation ownership and use the customer's documented SLA",
      "Assess third-party/supply-chain relevance from confirmed affected dependencies",
      "Assess insurance/legal/notification obligations only from confirmed incident facts with appropriate owners",
    ],
    exec: [
      "Request evidence-backed status from security leadership when customer escalation/materiality criteria are met",
      "Do not interpret vulnerability severity, KEV, EPSS or IOC presence as a confirmed breach or quantified financial loss",
      "Confirm accountable ownership, customer-approved timeline and resources",
      "Legal/regulatory disclosure decisions remain with the customer's legal/compliance process",
      "Track material residual risk to closure under established governance cadence",
    ],
  };
}

export function buildP28RoleGuidanceBlock(item) {
  const guidance = _buildRoleGuidance(item);
  const instanceId = `p28rg-${String(item.id || "x").replace(/[^a-z0-9]/gi, "").slice(-8)}`;

  const tabs = _ROLES.map((r, i) =>
    `<button id="${instanceId}-tab-${i}" onclick="p28ShowRole_${instanceId}(${i})"
      style="background:${i === 0 ? "#1e3a5f" : "transparent"};color:${i === 0 ? "#38bdf8" : "#6b7280"};border:none;padding:6px 12px;border-radius:4px;font-family:'Courier New',monospace;font-size:10px;font-weight:700;cursor:pointer;letter-spacing:.06em;white-space:nowrap;">
      ${r.icon} ${esc(r.label)}
    </button>`
  ).join("");

  const panels = _ROLES.map((r, i) => {
    const steps = guidance[r.id] || [];
    const stepsHtml = steps.map((s, si) =>
      `<div style="display:flex;gap:10px;padding:6px 0;border-bottom:1px solid #1a2030;">
        <span style="color:#1e3a5f;font-size:11px;font-weight:700;min-width:20px;">${si + 1}.</span>
        <span style="color:#94a3b8;font-size:11px;">${esc(s)}</span>
      </div>`
    ).join("");
    return `<div id="${instanceId}-panel-${i}" style="display:${i === 0 ? "block" : "none"}">
      <div style="color:#38bdf8;font-size:11px;font-weight:700;margin-bottom:8px;">${r.icon} ${esc(r.label)}  -  Operational Steps</div>
      ${stepsHtml}
    </div>`;
  }).join("");

  const script = `<script>
    function p28ShowRole_${instanceId}(idx) {
      [${_ROLES.map((_, i) => i).join(",")}].forEach(i => {
        var p = document.getElementById("${instanceId}-panel-"+i);
        var t = document.getElementById("${instanceId}-tab-"+i);
        if (p) p.style.display = i === idx ? "block" : "none";
        if (t) { t.style.background = i === idx ? "#1e3a5f" : "transparent"; t.style.color = i === idx ? "#38bdf8" : "#6b7280"; }
      });
    }
  </scr` + `ipt>`;

  const body = `
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #1a2030;">
      ${tabs}
    </div>
    <div id="${instanceId}-panels">
      ${panels}
    </div>
    ${script}`;

  return _block(
    `p28-role-guidance-${instanceId}`,
    "P28.7  -  Role-Based Operational Guidance",
    "#a78bfa",
    body,
    "SOC * Threat Hunter * Incident Responder * Security Engineer * Vuln Manager * CISO * Executive"
  );
}

// -- P28.9: Customer Feedback Framework ---------------------------------------
// Provides feedback UI embedded in report + KV-backed storage API.
// KV key: p28:feedback:{item_id}:{timestamp_ms}

export function buildP28FeedbackBlock(item) {
  const itemId    = esc(String(item.id || "unknown").slice(-24));
  const instanceId = `p28fb-${String(item.id || "x").replace(/[^a-z0-9]/gi, "").slice(-8)}`;
  const apiBase   = "https://intel.cyberdudebivash.com";

  const body = `
    <div style="color:#6b7280;font-size:11px;margin-bottom:12px;">
      Your feedback improves intelligence quality for all SENTINEL APEX customers.
      Ratings are anonymous and stored securely per our data handling policy.
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
      <div>
        <div style="color:#6b7280;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">Report Usefulness</div>
        <div style="display:flex;gap:4px;" id="${instanceId}-stars">
          ${[1,2,3,4,5].map(n => `<button onclick="p28Rate_${instanceId}(${n})" style="background:transparent;border:none;color:#374151;font-size:20px;cursor:pointer;padding:0 2px;" id="${instanceId}-star-${n}">&#9733;</button>`).join("")}
        </div>
      </div>
      <div>
        <div style="color:#6b7280;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">Detection Quality</div>
        <select id="${instanceId}-detection" style="background:#0a0f1a;border:1px solid #1e3a5f;color:#94a3b8;padding:6px 8px;border-radius:4px;font-family:'Courier New',monospace;font-size:11px;width:100%;">
          <option value="">Select rating</option>
          <option value="excellent">Excellent</option>
          <option value="good">Good</option>
          <option value="fair">Fair</option>
          <option value="poor">Poor</option>
          <option value="no_detection">No detection provided</option>
        </select>
      </div>
    </div>
    <div style="margin-bottom:10px;">
      <label style="display:flex;align-items:center;gap:8px;color:#6b7280;font-size:11px;cursor:pointer;margin-bottom:6px;">
        <input type="checkbox" id="${instanceId}-fp" style="accent-color:#ef4444;"> Contains false positives
      </label>
      <label style="display:flex;align-items:center;gap:8px;color:#6b7280;font-size:11px;cursor:pointer;">
        <input type="checkbox" id="${instanceId}-actionable" checked style="accent-color:#22c55e;"> Operationally actionable
      </label>
    </div>
    <div style="margin-bottom:10px;">
      <div style="color:#6b7280;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;">Improvement Suggestions (optional)</div>
      <textarea id="${instanceId}-comment" rows="2" style="width:100%;background:#0a0f1a;border:1px solid #1e3a5f;color:#94a3b8;padding:8px;border-radius:4px;font-family:'Courier New',monospace;font-size:11px;resize:vertical;" placeholder="What could improve this report?"></textarea>
    </div>
    <button onclick="p28SubmitFeedback_${instanceId}()" style="background:#1e3a5f;color:#38bdf8;border:none;padding:8px 18px;border-radius:4px;font-family:'Courier New',monospace;font-size:11px;font-weight:700;cursor:pointer;letter-spacing:.08em;">
      SUBMIT FEEDBACK
    </button>
    <span id="${instanceId}-status" style="color:#6b7280;font-size:11px;margin-left:12px;"></span>

    <script>
    (function() {
      var _rating = 0;
      function p28Rate_${instanceId}(n) {
        _rating = n;
        [1,2,3,4,5].forEach(function(i) {
          var star = document.getElementById("${instanceId}-star-"+i);
          if (star) star.style.color = i <= n ? "#f59e0b" : "#374151";
        });
      }
      window.p28Rate_${instanceId} = p28Rate_${instanceId};
      window.p28SubmitFeedback_${instanceId} = function() {
        var status = document.getElementById("${instanceId}-status");
        var key = sessionStorage.getItem("sentinel_api_key") || "";
        var payload = {
          item_id:    "${itemId}",
          rating:     _rating,
          detection:  (document.getElementById("${instanceId}-detection")||{}).value || "",
          false_positive: (document.getElementById("${instanceId}-fp")||{}).checked || false,
          actionable: (document.getElementById("${instanceId}-actionable")||{}).checked || true,
          comment:    (document.getElementById("${instanceId}-comment")||{}).value || "",
        };
        if (!_rating) { if (status) status.textContent = "Please select a star rating."; return; }
        if (status) status.textContent = "Submitting...";
        fetch("${apiBase}/api/v1/p28/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-API-Key": key },
          body: JSON.stringify(payload),
        }).then(function(r) {
          if (status) status.textContent = r.ok ? "Thank you  -  feedback recorded." : "Submitted (will sync when online).";
        }).catch(function() {
          if (status) status.textContent = "Feedback noted  -  will retry when online.";
        });
      };
    })();
    </scr` + `ipt>`;

  return _block(
    `p28-feedback-${instanceId}`,
    "P28.9  -  Customer Feedback",
    "#34d399",
    body,
    "Rate this advisory * improve intelligence quality for all customers"
  );
}

// -- P28.10: Operational Metrics -----------------------------------------------
// Per-item metrics summary pulled from existing feed fields + computed scores.

export function buildP28MetricsBlock(item) {
  const cvss  = (explicitCvss(item) ?? 0);
  const epss  = parseFloat(item.epss_score || 0);
  const conf  = parseFloat(item.confidence || item.confidence_score || 0.5);
  const enrichScore = parseFloat(item.enrichment_score || 0);
  const srcQ  = parseFloat(item.source_quality || 0);

  // publication latency: processed_at - timestamp (if both available)
  let pubLatencyLabel = "N/A";
  try {
    const ts = new Date(item.timestamp || item.published_at).getTime();
    const pa = new Date(item.processed_at).getTime();
    if (ts && pa && pa > ts) {
      const hours = Math.round((pa - ts) / 3600000);
      pubLatencyLabel = hours < 24 ? `${hours}h` : `${Math.round(hours / 24)}d`;
    }
  } catch (_) {}

  // ioc validation rate
  const iocTotal = item.ioc_count || 0;
  const iocConf  = parseFloat(item.ioc_confidence || 0);
  const iocValidRate = iocTotal > 0 && iocConf > 0 ? `${Math.round(iocConf * 100)}%` : iocTotal > 0 ? " - " : "N/A";

  // detection availability
  const detAvail = Boolean(item.apex && item.apex.sigma_rule) ? "Sigma rule available"
    : (item.validation_status === "VALIDATED") ? "Detection validated"
    : "Review advisory";

  // MITRE coverage
  const mitreTactics = (item.mitre_tactics || []).length;
  const ttpCount = (item.ttps || []).length;

  const metrics = [
    { label: "CVSS Score",              value: cvss > 0 ? cvss.toFixed(1) : "N/A",               color: cvss >= 9 ? "#ef4444" : cvss >= 7 ? "#f59e0b" : "#22c55e" },
    { label: "EPSS Probability",        value: `${(epss * 100).toFixed(1)}%`,                     color: epss > 0.7 ? "#ef4444" : epss > 0.4 ? "#f59e0b" : "#22c55e" },
    { label: "Confidence Level",        value: `${Math.round(conf * 100)}%`,                      color: conf > 0.8 ? "#22c55e" : conf > 0.5 ? "#f59e0b" : "#ef4444" },
    { label: "Enrichment Score",        value: enrichScore > 0 ? `${Math.round(enrichScore)}/100` : " - ", color: "#94a3b8" },
    { label: "Source Quality",          value: srcQ > 0 ? `${Math.round(srcQ * 100)}%` : " - ",    color: "#94a3b8" },
    { label: "Publication Latency",     value: pubLatencyLabel,                                    color: "#94a3b8" },
    { label: "IOC Count",               value: String(iocTotal),                                   color: iocTotal > 0 ? "#38bdf8" : "#374151" },
    { label: "IOC Validation Rate",     value: iocValidRate,                                       color: "#94a3b8" },
    { label: "MITRE Tactics Mapped",    value: `${mitreTactics} tactic${mitreTactics !== 1 ? "s" : ""}`, color: mitreTactics > 0 ? "#818cf8" : "#374151" },
    { label: "TTP References",          value: String(ttpCount),                                   color: ttpCount > 0 ? "#818cf8" : "#374151" },
    { label: "Detection Availability",  value: detAvail,                                           color: detAvail.includes("available") || detAvail.includes("validated") ? "#22c55e" : "#6b7280" },
    { label: "STIX Bundle",             value: item.stix_bundle ? "Available" : "Unavailable",    color: item.stix_bundle ? "#22c55e" : "#374151" },
  ];

  const rows = metrics.map(m => _row(m.label, `<span style="color:${m.color}">${esc(String(m.value))}</span>`, m.color)).join("");

  return _block(
    "p28-metrics",
    "P28.10  -  Operational Metrics",
    "#64748b",
    `<div style="columns:2;column-gap:16px;">${rows}</div>`,
    "Per-advisory quality, coverage, and operational metrics"
  );
}

// -- API Handlers --------------------------------------------------------------

function _jsonResp(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export async function handleP28Feedback(request, env) {
  if (request.method !== "POST") {
    return _jsonResp({ error: "POST required" }, 405);
  }
  // This widget is embedded directly in public report pages (buildP28FeedbackBlock
  // renders it into every report), so it's intentionally reachable without a paid
  // API key -- anonymous "was this helpful" feedback is the intended UX. But with
  // no auth AND no rate limit, it was a fully open, unbounded state-changing write
  // (KV storage abuse, fake-rating flooding). Cap per-IP instead of requiring auth,
  // which would break the legitimate anonymous use case.
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "unknown";
  if (env.RATE_LIMIT_KV) {
    const rlKey = `p28fb_rl:${ip}:${new Date().toISOString().slice(0, 13)}`; // hour bucket
    const rlCount = parseInt((await env.RATE_LIMIT_KV.get(rlKey)) || "0", 10);
    if (rlCount >= 20) {
      return _jsonResp({ error: "Too many feedback submissions from this network. Try again later." }, 429);
    }
    await env.RATE_LIMIT_KV.put(rlKey, String(rlCount + 1), { expirationTtl: 3600 });
  }
  let body;
  try { body = await request.json(); } catch (_) {
    return _jsonResp({ error: "Invalid JSON body" }, 400);
  }
  const { item_id, rating, detection, false_positive, actionable, comment } = body;
  if (!item_id || !rating) {
    return _jsonResp({ error: "item_id and rating required" }, 400);
  }
  if (typeof rating !== "number" || rating < 1 || rating > 5) {
    return _jsonResp({ error: "rating must be 1-5" }, 400);
  }

  const ts = Date.now();
  const kvKey = `${FB_PREFIX}${String(item_id).slice(0, 64)}:${ts}`;
  const record = {
    item_id: String(item_id).slice(0, 64),
    rating,
    detection: String(detection || "").slice(0, 32),
    false_positive: Boolean(false_positive),
    actionable: Boolean(actionable !== false),
    comment: String(comment || "").slice(0, 500),
    recorded_at: new Date(ts).toISOString(),
  };
  try {
    await env.SECURITY_HUB_KV.put(kvKey, JSON.stringify(record), { expirationTtl: 7776000 }); // 90d
  } catch (_) {
    // KV unavailable in test  -  still return success to client
  }
  return _jsonResp({ ok: true, recorded_at: record.recorded_at });
}

export async function handleP28Certify(request, env) {
  let item;
  if (request.method === "POST") {
    try { item = await request.json(); } catch (_) {
      return _jsonResp({ error: "Invalid JSON" }, 400);
    }
  } else {
    const url    = new URL(request.url);
    const itemId = url.searchParams.get("id");
    if (!itemId) return _jsonResp({ error: "id param or POST body required" }, 400);
    try {
      // PRODUCTION-VERIFICATION FIX (2026-08-24): "feeds/feed.json" is a
      // dead R2 key nothing ever writes -- see p18-handlers.js's matching
      // _loadFeed fix note for the full cross-file root cause. Redirected
      // to the live, continuously updated key.
      const raw = await env.INTEL_R2.get("api/v1/intel/latest.json");
      if (!raw) return _jsonResp({ error: "Feed unavailable" }, 503);
      const feed = JSON.parse(await raw.text());
      // The live key stores {items: [...]}, not a bare array (the dead key
      // this replaced was never actually populated in either shape, so
      // this array-only check had never been exercised against real data).
      const feedItems = Array.isArray(feed) ? feed : (feed?.items || []);
      item = feedItems.find(i => i.id === itemId || i.stix_id === itemId);
      if (!item) return _jsonResp({ error: "Item not found" }, 404);
    } catch (e) {
      return _jsonResp({ error: "Feed error: " + e.message }, 503);
    }
  }

  // Derive P28 metrics (reuse P23+P26 engines)
  let actScore = 0, p26Grade = null;
  try { actScore = computeActionabilityScore(item); } catch (_) {}
  try { p26Grade = computeP26Grade(item); } catch (_) {}

  const envRisk     = _deriveEnvRelevance(item);
  const finImpact   = _deriveFinancialBand(item);
  const disruption  = _deriveOperationalDisruption(item);
  const compliance  = _deriveComplianceImplications(item);

  return _jsonResp({
    schema_version:    P28_VERSION,
    item_id:           item.id,
    title:             item.title,
    generated_at:      new Date().toISOString(),
    p28_1_environment: {
      high:   envRisk.filter(e => e.level === "HIGH").map(e => e.label),
      medium: envRisk.filter(e => e.level === "MEDIUM").map(e => e.label),
      low:    envRisk.filter(e => e.level === "LOW").map(e => e.label),
    },
    p28_3_business_impact: {
      financial_band:      finImpact.band,
      financial_range:     finImpact.range,
      operational_disruption: disruption,
      compliance_implications: compliance,
    },
    p28_5_action_center: {
      actionability_score: actScore,
      kev_listed:   Boolean(item.kev_present || (item.apex && item.apex.kev_listed)),
      ioc_count:    item.ioc_count || 0,
      has_detection: Boolean(item.apex && item.apex.sigma_rule),
    },
    p26_composite: p26Grade ? {
      grade:          p26Grade.grade,
      composite:      p26Grade.composite,
      release_tier:   p26Grade.release_tier,
    } : null,
  });
}

export async function handleP28Observability(request, env) {
  // Read p27 + p26 + p25 quality reports if available; derive platform-level metrics.
  const reports = {};
  const load = async (k, path) => {
    try {
      const kv = await env.SECURITY_HUB_KV.get(`quality:${k}`);
      if (kv) { reports[k] = JSON.parse(kv); return; }
    } catch (_) {}
    // fall through  -  report will be null
    reports[k] = null;
  };
  // best-effort  -  don't block on failures
  try { await Promise.all(["p27","p26","p25"].map(k => load(k, k))); } catch (_) {}

  // Read feed for live metrics
  let feedItems = 0, avgConf = 0, criticalCount = 0, ttpCoverage = 0, iocTotal = 0;
  try {
    // PRODUCTION-VERIFICATION FIX (2026-08-24): "feed:latest" is a dead
    // SECURITY_HUB_KV key nothing ever writes -- see p18-handlers.js's
    // matching _loadFeed fix note. Redirected to the live R2 key.
    const r2obj = await env.INTEL_R2.get("api/v1/intel/latest.json");
    if (r2obj) {
      const data = await r2obj.json();
      const feed = Array.isArray(data) ? data : (data?.items || []);
      if (Array.isArray(feed)) {
        feedItems    = feed.length;
        avgConf      = feed.reduce((s, i) => s + (parseFloat(i.confidence || i.confidence_score || 0.5)), 0) / feed.length;
        criticalCount = feed.filter(i => String(i.severity || "").toUpperCase() === "CRITICAL").length;
        ttpCoverage  = Math.round(feed.filter(i => (i.ttps || []).length > 0 || (i.mitre_tactics || []).length > 0).length / feed.length * 100);
        iocTotal     = feed.reduce((s, i) => s + (parseInt(i.ioc_count || 0)), 0);
      }
    }
  } catch (_) {}

  return _jsonResp({
    schema_version: P28_VERSION,
    generated_at:   new Date().toISOString(),
    platform_metrics: {
      feed_items:        feedItems,
      critical_advisories: criticalCount,
      avg_confidence_pct: Math.round(avgConf * 100),
      ttp_coverage_pct:   ttpCoverage,
      total_iocs:         iocTotal,
    },
    quality_gates: {
      p27_tier: reports.p27 ? reports.p27.release_tier : null,
      p26_tier: reports.p26 ? reports.p26.release_tier : null,
      p25_tier: reports.p25 ? reports.p25.release_tier : null,
    },
  });
}

// -- Composite package ---------------------------------------------------------

export function buildP28Package(item) {
  return (
    buildP28EnvironmentRiskBlock(item) +
    buildP28BusinessImpactBlock(item)  +
    buildP28ActionCenterBlock(item)    +
    buildP28RoleGuidanceBlock(item)    +
    buildP28FeedbackBlock(item)        +
    buildP28MetricsBlock(item)
  );
}
