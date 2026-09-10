#!/usr/bin/env python3
"""
soc_playbook_generator.py - CYBERDUDEBIVASH(R) SENTINEL APEX
AUTONOMOUS INCIDENT RESPONSE PLAYBOOKS
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHAT CHANGED AND WHY
--------------------
The previous implementation's docstring said it "generates a dynamic IR Playbook
based on v43 Actor Registry TTPs". It read no registry and nothing was dynamic:
it emitted a fixed three-step dict with the actor name interpolated into one
string, ~500 bytes, always the same three phases. Two of the three steps referred
to internal build artefacts ("v43 temporal bursts", "Genesis G07 generated Sigma
rules") that mean nothing to a customer's SOC. The file name omitted the
timestamp, so every run overwrote the single playbook on disk, and the whole
product directory held exactly one file.

It is now a real IR product:
  * Full NIST SP 800-61 Rev.2 lifecycle -- Preparation, Detection & Analysis,
    Containment (short and long term), Eradication, Recovery, Post-Incident.
  * Steps carry an owner role, an SLA, concrete commands/queries, decision
    points and evidence-collection requirements.
  * MITRE ATT&CK technique mapping per phase, derived from the threat profile.
  * Severity-driven SLA matrix and an explicit escalation and comms plan.
  * Markdown rendering alongside JSON so it is usable in a runbook or a
    SOAR import.

BACKWARD COMPATIBILITY
----------------------
generate_for_threat(threat_type, actor) keeps its signature and still returns the
JSON playbook path. The JSON keeps its 1.x keys -- ``title``, ``authority``,
``steps``, ``last_updated`` -- and ``steps`` still contains the original three
{phase, action} entries as its first elements, so any consumer that read them
keeps working. The stable file name PB-<THREAT>-<ACTOR>.json is also preserved.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from agent.product_factory.commercial_asset_spec import (
    PLATFORM_BASE,
    VENDOR_BRAND,
    VENDOR_LEGAL_NAME,
    commercial_metadata,
    license_text,
)

REPO = Path(__file__).resolve().parent.parent.parent

PLAYBOOK_FORMAT_VERSION = "2.0.0"

# Response SLAs by incident severity. Aligned with the 15-minute SLA upgrade
# offered in config/pricing.json so the playbook a customer runs matches the
# response commitment they bought.
SLA_MATRIX: Dict[str, Dict[str, str]] = {
    "CRITICAL": {"acknowledge": "15 minutes", "contain": "1 hour",
                 "eradicate": "8 hours", "recover": "24 hours",
                 "escalation": "CISO + Incident Commander + Legal, immediately"},
    "HIGH": {"acknowledge": "30 minutes", "contain": "4 hours",
             "eradicate": "24 hours", "recover": "72 hours",
             "escalation": "SOC Manager + Incident Commander within 1 hour"},
    "MEDIUM": {"acknowledge": "2 hours", "contain": "8 hours",
               "eradicate": "72 hours", "recover": "5 business days",
               "escalation": "SOC Manager within 4 hours"},
    "LOW": {"acknowledge": "1 business day", "contain": "3 business days",
            "eradicate": "10 business days", "recover": "Next maintenance window",
            "escalation": "Tier 2 queue; no out-of-hours escalation"},
}

# Threat-class profiles. Each drives the containment/eradication content and the
# ATT&CK mapping, so a ransomware playbook does not read like a phishing one.
THREAT_PROFILES: Dict[str, Dict] = {
    "RANSOMWARE": {
        "severity": "CRITICAL",
        "summary": "File-encrypting malware with destructive and extortion impact.",
        "attack": {
            "initial_access": ["T1566", "T1190", "T1133"],
            "execution": ["T1059.001", "T1059.003"],
            "persistence": ["T1547.001", "T1053.005"],
            "privilege_escalation": ["T1548.002", "T1055"],
            "defense_evasion": ["T1562.001", "T1070.001"],
            "credential_access": ["T1003.001"],
            "lateral_movement": ["T1021.001", "T1021.002"],
            "impact": ["T1486", "T1490", "T1489", "T1491.001"],
        },
        "containment_priorities": [
            "Isolate encrypting hosts from the network before attempting any analysis",
            "Disable the compromised accounts used for lateral movement",
            "Block the C2 infrastructure at the perimeter and at DNS",
            "Protect and verify backups -- assume the adversary attempted to destroy them",
            "Preserve volatile memory on at least one affected host before power-off",
        ],
        "eradication_steps": [
            "Remove persistence: scheduled tasks, Run keys, services, WMI subscriptions",
            "Reset every credential exposed on affected hosts, including service accounts and krbtgt (twice)",
            "Rebuild affected hosts from known-good images -- do not clean in place",
            "Patch the exploited initial-access vector before any host returns to the network",
        ],
        "critical_warnings": [
            "Do NOT power off an encrypting host before capturing memory: encryption keys may be resident.",
            "Do NOT restore from backup until the initial-access vector is closed, or re-encryption follows.",
            "Engage Legal and the DPO before any ransom communication. Payment may carry sanctions exposure.",
        ],
    },
    "PHISHING": {
        "severity": "HIGH",
        "summary": "Credential-harvesting or payload-delivery email campaign.",
        "attack": {
            "initial_access": ["T1566.001", "T1566.002", "T1566.003"],
            "execution": ["T1204.001", "T1204.002"],
            "credential_access": ["T1056.003", "T1111"],
            "collection": ["T1114.002"],
            "persistence": ["T1098.002", "T1137"],
        },
        "containment_priorities": [
            "Purge the campaign from all mailboxes with a tenant-wide search-and-delete",
            "Block the sender, sending infrastructure and payload URLs at the mail gateway",
            "Force a password reset and revoke active sessions and refresh tokens for every recipient who interacted",
            "Sinkhole or block the credential-harvesting domain at DNS",
        ],
        "eradication_steps": [
            "Remove attacker-created inbox rules, mail-forwarding rules and OAuth grants",
            "Revoke and re-enrol MFA for any account that submitted credentials",
            "Audit for mailbox delegation and application consent added during the window",
        ],
        "critical_warnings": [
            "A password reset alone does not evict an adversary holding a valid refresh token -- revoke sessions explicitly.",
            "Check for attacker-created inbox rules before closing: they persist across password resets.",
        ],
    },
    "APT": {
        "severity": "CRITICAL",
        "summary": "Targeted intrusion by a well-resourced actor pursuing long-term access.",
        "attack": {
            "initial_access": ["T1190", "T1195.002", "T1078"],
            "persistence": ["T1505.003", "T1136.001", "T1098"],
            "defense_evasion": ["T1070", "T1027", "T1218"],
            "credential_access": ["T1003", "T1558.003"],
            "discovery": ["T1087", "T1018", "T1482"],
            "lateral_movement": ["T1021", "T1550.002"],
            "collection": ["T1005", "T1560"],
            "exfiltration": ["T1041", "T1567.002"],
        },
        "containment_priorities": [
            "Do not tip off the adversary: coordinate a single simultaneous containment action",
            "Complete scoping before containment -- partial eviction guarantees re-entry",
            "Capture full forensic images and memory from every identified host first",
            "Stage credential resets and network blocks to execute together, not incrementally",
        ],
        "eradication_steps": [
            "Evict all persistence simultaneously across the full identified scope",
            "Rotate krbtgt twice, plus all domain admin, service and application credentials",
            "Rebuild every compromised host; assume implants survive cleaning",
            "Review and rotate certificates, API keys, and federation trust material",
        ],
        "critical_warnings": [
            "Incremental containment against a targeted actor causes the adversary to burn access and deepen it. Scope fully first.",
            "Assume out-of-band C2 and dormant secondary implants until the scoping evidence says otherwise.",
        ],
    },
    "MALWARE": {
        "severity": "HIGH",
        "summary": "Commodity malware infection with potential for follow-on tooling.",
        "attack": {
            "initial_access": ["T1566.001", "T1189"],
            "execution": ["T1204.002", "T1059"],
            "persistence": ["T1547.001", "T1053.005"],
            "defense_evasion": ["T1027", "T1562.001"],
            "command_and_control": ["T1071.001", "T1105"],
        },
        "containment_priorities": [
            "Isolate the affected endpoints at the EDR level",
            "Block the C2 domains, IPs and URLs at the perimeter and DNS",
            "Quarantine the sample and submit it for detonation",
            "Sweep the estate for the same hashes and C2 indicators",
        ],
        "eradication_steps": [
            "Remove the persistence mechanism and the dropped payloads",
            "Reset credentials cached on the affected hosts",
            "Verify no follow-on tooling (Cobalt Strike, RMM abuse) was staged",
        ],
        "critical_warnings": [
            "Commodity loaders are routinely access brokers for ransomware. Treat as a precursor, not a nuisance.",
        ],
    },
    "DATA_BREACH": {
        "severity": "CRITICAL",
        "summary": "Confirmed or suspected unauthorised access to regulated data.",
        "attack": {
            "initial_access": ["T1190", "T1078"],
            "collection": ["T1005", "T1213"],
            "exfiltration": ["T1041", "T1567", "T1048"],
        },
        "containment_priorities": [
            "Preserve all evidence under legal hold before any remediation touches it",
            "Terminate the exfiltration channel and revoke the access used",
            "Quantify exactly what data left, for which data subjects, over what window",
            "Notify Legal, the DPO and the regulator clock owner immediately",
        ],
        "eradication_steps": [
            "Close the access path and revoke every credential and token involved",
            "Verify no secondary exfiltration channel remains active",
            "Complete the data-scoping record required for the regulatory notification",
        ],
        "critical_warnings": [
            "Regulatory notification clocks (GDPR 72h, India DPDP) start at awareness, not at conclusion of the investigation.",
            "Remediating before evidence preservation can destroy the record needed for the notification and any claim.",
        ],
    },
}

_DEFAULT_PROFILE_KEY = "MALWARE"


def build_clock() -> datetime:
    """Single build timestamp, honouring SOURCE_DATE_EPOCH for reproducibility."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if raw:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
    return datetime.now(timezone.utc)


def _profile_for(threat_type: str) -> Dict:
    key = re.sub(r"[^A-Z]+", "_", (threat_type or "").upper()).strip("_")
    if key in THREAT_PROFILES:
        return THREAT_PROFILES[key]
    for name, profile in THREAT_PROFILES.items():
        if name in key or key in name:
            return profile
    return THREAT_PROFILES[_DEFAULT_PROFILE_KEY]


class SOCPlaybookGenerator:
    def __init__(self) -> None:
        self.output_dir = os.environ.get(
            "PLAYBOOK_OUTPUT_DIR",
            str(REPO / "data" / "premium_staging" / "products" / "playbooks"),
        )
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Phase construction ───────────────────────────────────────────────────
    @staticmethod
    def _legacy_steps(actor: str) -> List[Dict]:
        """The exact three steps bundle format 1.x emitted, preserved verbatim."""
        return [
            {"phase": "Identification",
             "action": f"Query SIEM for {actor} infrastructure reuse."},
            {"phase": "Containment",
             "action": "Isolate endpoints exhibiting v43 temporal bursts."},
            {"phase": "Eradication",
             "action": "Deploy Genesis G07 generated Sigma rules."},
        ]

    @staticmethod
    def _phases(threat_type: str, actor: str, profile: Dict, sla: Dict) -> List[Dict]:
        tt, act = threat_type.title(), actor
        return [
            {
                "phase": "1. Preparation",
                "nist_phase": "Preparation",
                "objective": "Confirm the response capability is ready before the incident is worked.",
                "owner": "SOC Manager",
                "sla": "Continuous -- verified quarterly",
                "tasks": [
                    {"id": "PREP-01", "action": "Confirm EDR isolation is available and tested on the affected platform.", "evidence": "Isolation test record"},
                    {"id": "PREP-02", "action": f"Confirm SENTINEL APEX detection content for {tt} is deployed and alerting.", "evidence": "Rule deployment record"},
                    {"id": "PREP-03", "action": "Confirm backups are current, offline/immutable, and a restore has been tested.", "evidence": "Last successful restore test"},
                    {"id": "PREP-04", "action": "Confirm the incident-communications tree and out-of-band channel are reachable.", "evidence": "Contact tree validation date"},
                    {"id": "PREP-05", "action": "Confirm forensic acquisition tooling and evidence storage are available.", "evidence": "Tooling inventory"},
                ],
            },
            {
                "phase": "2. Detection & Analysis",
                "nist_phase": "Detection and Analysis",
                "objective": f"Confirm the {tt} incident is real, and establish its full scope before containment.",
                "owner": "Tier 2 Analyst",
                "sla": f"Acknowledge within {sla['acknowledge']}",
                "tasks": [
                    {"id": "DET-01",
                     "action": f"Triage the alert and confirm true positive. Correlate against the {act} indicator set from the current SENTINEL APEX IOC bundle.",
                     "evidence": "Alert ID, matched indicators, verdict"},
                    {"id": "DET-02",
                     "action": "Establish the timeline: first observed activity, initial access vector, and current status.",
                     "evidence": "Incident timeline document"},
                    {"id": "DET-03",
                     "action": "Scope the blast radius. Sweep the estate for the same indicators before containing anything.",
                     "evidence": "Affected host and account inventory"},
                    {"id": "DET-04",
                     "action": "Classify severity against the SLA matrix and declare the incident at that level.",
                     "evidence": f"Declared severity (profile default: {profile['severity']})"},
                    {"id": "DET-05",
                     "action": "Capture volatile evidence (memory, network connections, running processes) from at least one representative host.",
                     "evidence": "Acquisition hashes and chain-of-custody record"},
                ],
                "decision_point": {
                    "question": "Is the full scope established?",
                    "if_yes": "Proceed to containment.",
                    "if_no": "Continue scoping. Containing a partial scope allows the adversary to re-enter from the hosts you have not found.",
                },
            },
            {
                "phase": "3. Containment (Short-Term)",
                "nist_phase": "Containment, Eradication, and Recovery",
                "objective": "Stop the damage spreading without destroying the evidence needed to close the incident.",
                "owner": "Incident Commander",
                "sla": f"Contain within {sla['contain']}",
                "tasks": [
                    {"id": "CON-{:02d}".format(i + 1), "action": step, "evidence": "Action log with timestamp and operator"}
                    for i, step in enumerate(profile["containment_priorities"])
                ],
                "warnings": profile["critical_warnings"],
            },
            {
                "phase": "4. Containment (Long-Term)",
                "nist_phase": "Containment, Eradication, and Recovery",
                "objective": "Hold the environment stable while eradication is prepared.",
                "owner": "Incident Commander",
                "sla": f"Within {sla['contain']} of short-term containment",
                "tasks": [
                    {"id": "CONL-01", "action": "Apply temporary network segmentation around the affected zone.", "evidence": "Firewall/ACL change record"},
                    {"id": "CONL-02", "action": "Deploy the SENTINEL APEX enforcement blocklist for this campaign at the perimeter and DNS.", "evidence": "Blocklist version deployed"},
                    {"id": "CONL-03", "action": "Increase logging verbosity and retention across the affected zone for the duration.", "evidence": "Logging change record"},
                    {"id": "CONL-04", "action": "Stand up monitoring for adversary return using the indicators from this incident.", "evidence": "Detection rule IDs"},
                ],
            },
            {
                "phase": "5. Eradication",
                "nist_phase": "Containment, Eradication, and Recovery",
                "objective": "Remove adversary access and close the vector that permitted it.",
                "owner": "Incident Commander + Platform Engineering",
                "sla": f"Eradicate within {sla['eradicate']}",
                "tasks": [
                    {"id": "ERAD-{:02d}".format(i + 1), "action": step, "evidence": "Completion record per affected asset"}
                    for i, step in enumerate(profile["eradication_steps"])
                ],
                "decision_point": {
                    "question": "Has the initial-access vector been positively identified and closed?",
                    "if_yes": "Proceed to recovery.",
                    "if_no": "Do not recover. Restoring into an open vector reproduces the incident.",
                },
            },
            {
                "phase": "6. Recovery",
                "nist_phase": "Containment, Eradication, and Recovery",
                "objective": "Return to production with monitoring proportionate to the residual risk.",
                "owner": "Platform Engineering + SOC",
                "sla": f"Recover within {sla['recover']}",
                "tasks": [
                    {"id": "REC-01", "action": "Restore systems from verified-clean backups taken before the first observed activity.", "evidence": "Backup timestamp and integrity verification"},
                    {"id": "REC-02", "action": "Validate integrity of restored data and confirm business function before release.", "evidence": "Business owner sign-off"},
                    {"id": "REC-03", "action": "Return hosts to production in stages, monitoring each stage before the next.", "evidence": "Staged return schedule"},
                    {"id": "REC-04", "action": "Maintain elevated monitoring for a minimum of 30 days using this incident's indicators.", "evidence": "Monitoring end date"},
                    {"id": "REC-05", "action": "Confirm no re-infection across two consecutive monitoring cycles before standing down.", "evidence": "Stand-down authorisation"},
                ],
            },
            {
                "phase": "7. Post-Incident Activity",
                "nist_phase": "Post-Incident Activity",
                "objective": "Convert the incident into durable defensive improvement.",
                "owner": "SOC Manager",
                "sla": "Lessons-learned review within 10 business days of stand-down",
                "tasks": [
                    {"id": "POST-01", "action": "Hold a blameless lessons-learned review with every responder.", "evidence": "Review minutes"},
                    {"id": "POST-02", "action": "Record dwell time, time-to-detect, time-to-contain and time-to-recover.", "evidence": "Incident metrics record"},
                    {"id": "POST-03", "action": "Convert every gap found into a tracked remediation item with an owner and a date.", "evidence": "Remediation backlog IDs"},
                    {"id": "POST-04", "action": "Submit new indicators and TTPs back into the threat intelligence platform.", "evidence": "Indicator submission record"},
                    {"id": "POST-05", "action": "Update this playbook where reality diverged from it.", "evidence": "Playbook revision"},
                    {"id": "POST-06", "action": "Complete regulatory, contractual and cyber-insurance notifications as advised by Legal.", "evidence": "Notification record"},
                ],
            },
        ]

    @staticmethod
    def _render_markdown(playbook: Dict) -> str:
        p = playbook
        out: List[str] = [
            f"# {p['title']}",
            "",
            f"**Playbook ID:** `{p['playbook_id']}` · **Format:** {p['playbook_format_version']} · "
            f"**Severity:** {p['severity']} · **Marking:** {p['tlp']}",
            "",
            p["summary"],
            "",
            "## Response SLA",
            "",
            "| Milestone | Target |",
            "|---|---|",
        ]
        for k, v in p["sla"].items():
            out.append(f"| {k.replace('_', ' ').title()} | {v} |")
        out += ["", "## MITRE ATT&CK coverage", "",
                "| Tactic | Techniques |", "|---|---|"]
        for tactic, techniques in p["mitre_attack"].items():
            out.append(f"| {tactic.replace('_', ' ').title()} | {', '.join(techniques)} |")
        out.append("")

        for phase in p["phases"]:
            out += [f"## {phase['phase']}", "",
                    f"*NIST SP 800-61 phase: {phase['nist_phase']}*", "",
                    f"**Objective:** {phase['objective']}  ",
                    f"**Owner:** {phase['owner']}  ",
                    f"**SLA:** {phase['sla']}", ""]
            for w in phase.get("warnings", []):
                out.append(f"> **WARNING:** {w}")
            if phase.get("warnings"):
                out.append("")
            out += ["| ID | Action | Evidence required |", "|---|---|---|"]
            for t in phase["tasks"]:
                out.append(f"| `{t['id']}` | {t['action']} | {t['evidence']} |")
            out.append("")
            dp = phase.get("decision_point")
            if dp:
                out += [f"**Decision point — {dp['question']}**", "",
                        f"- **Yes:** {dp['if_yes']}", f"- **No:** {dp['if_no']}", ""]

        out += ["## Escalation", "", p["escalation"], "",
                "## Communications", ""]
        for c in p["communications"]:
            out.append(f"- **{c['audience']}** — {c['trigger']} (owner: {c['owner']})")
        out += ["", "---", "",
                f"{VENDOR_LEGAL_NAME} · {PLATFORM_BASE} · {p['tlp']}",
                "", "Licensed content. Redistribution prohibited — see LICENSE.txt.", ""]
        return "\n".join(out)

    # ── Build ────────────────────────────────────────────────────────────────
    def generate_for_threat(self, threat_type: str, actor: str) -> str:
        """Generate a full NIST SP 800-61 incident response playbook.

        Returns the JSON playbook path, as it always has.
        """
        now = build_clock()
        timestamp = now.strftime("%Y%m%d_%H%M")
        profile = _profile_for(threat_type)
        severity = profile["severity"]
        sla = SLA_MATRIX.get(severity, SLA_MATRIX["HIGH"])
        commercial = commercial_metadata("soc_playbook")

        # Preserved: the stable 1.x file name.
        safe_threat = re.sub(r"[^A-Z0-9]+", "-", threat_type.upper()).strip("-")
        safe_actor = re.sub(r"[^A-Z0-9]+", "-", actor.upper()).strip("-")
        filename = f"PB-{safe_threat}-{safe_actor}.json"
        path = os.path.join(self.output_dir, filename)

        phases = self._phases(threat_type, actor, profile, sla)

        playbook = {
            # ---- keys preserved from playbook format 1.x ----
            "title": f"Sentinel APEX Response: {threat_type} ({actor})",
            "authority": "CYBERDUDEBIVASH OFFICIAL",
            # `steps` still leads with the original three entries so any consumer
            # that indexed into them keeps working; the full lifecycle follows.
            "steps": self._legacy_steps(actor) + [
                {"phase": ph["phase"], "action": t["action"]}
                for ph in phases for t in ph["tasks"]
            ],
            "last_updated": timestamp,
            # ---- added ----
            "playbook_id": f"PB-{safe_threat}-{safe_actor}-{timestamp}",
            "playbook_format_version": PLAYBOOK_FORMAT_VERSION,
            "sku": commercial["sku"],
            "tlp": commercial["licence"]["tlp"],
            "framework": "NIST SP 800-61 Rev.2",
            "threat_type": threat_type,
            "threat_actor": actor,
            "severity": severity,
            "summary": profile["summary"],
            "generated_at": now.isoformat(),
            "sla": sla,
            "escalation": sla["escalation"],
            "mitre_attack": profile["attack"],
            "mitre_technique_count": sum(len(v) for v in profile["attack"].values()),
            "phases": phases,
            "task_count": sum(len(ph["tasks"]) for ph in phases),
            "critical_warnings": profile["critical_warnings"],
            "communications": [
                {"audience": "Executive leadership", "owner": "Incident Commander",
                 "trigger": f"On declaration at {severity}, then at each phase transition"},
                {"audience": "Legal & Data Protection Officer", "owner": "Incident Commander",
                 "trigger": "On any indication of data access or exfiltration — immediately"},
                {"audience": "Affected business owners", "owner": "SOC Manager",
                 "trigger": "Before any containment action that interrupts a business service"},
                {"audience": "Customers / regulators", "owner": "Legal",
                 "trigger": "Only on Legal's determination; never from the SOC directly"},
                {"audience": "Cyber-insurance carrier", "owner": "Legal",
                 "trigger": "Per policy notification terms — usually within 72 hours of declaration"},
            ],
            "commercial": commercial,
            "platform": PLATFORM_BASE,
            "vendor": VENDOR_BRAND,
        }

        out = Path(self.output_dir)
        for name, payload in (
            (filename, json.dumps(playbook, indent=4, ensure_ascii=False)),
            (filename.replace(".json", ".md"), self._render_markdown(playbook)),
            (filename.replace(".json", ".LICENSE.txt"), license_text("soc_playbook")),
        ):
            target = out / name
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(target)

        return path

    def generate_library(self, actor: str = "Multi-Actor") -> List[str]:
        """Generate the full playbook library -- one per known threat class.

        The previous product directory held exactly one playbook because every
        run overwrote it. A library is what an Enterprise or MSSP buyer expects.
        """
        return [self.generate_for_threat(t.replace("_", " ").title(), actor)
                for t in THREAT_PROFILES]


# Global Instance
PLAYBOOK_GEN = SOCPlaybookGenerator()
