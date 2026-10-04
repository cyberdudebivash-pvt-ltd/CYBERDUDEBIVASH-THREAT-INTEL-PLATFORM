# Customer-page production audit — 2026-10-04

Scope: 162 shipped non-report HTML pages, 2,063 same-site route references, 24 meta-refresh pages, and 140 executable inline scripts. Static deployment-route and redirect-cycle checks pass; inline syntax checks pass. This is not full production certification.

Confirmed defects remediated: legacy threat graph fabricated outage data and randomized ATT&CK attribution; deployment guide advertised unmeasured uptime/regional availability; analyst dashboard manufactured CVSS components, rules, recommendations and STIX, and failed to clear the actual feed on outage.

Next verification: exact-head CI, deployed pages, authorized API-key journeys, payments without charge, keyboard/mobile interaction, security review of remaining rendered API data, external links, and report-source/archived-report coverage. No claim of zero regression or global availability is established by structural checks.

The deployment inventory excludes internal/quarantined pages and report archives, as production build rules do. Dynamic API/auth/report routes and external websites are outside the static-file resolver. No external credentials or customer data were used.

| Page | Static routes | Inline syntax checks | Behavioral/content review |
|---|---|---:|---|
| `404.html` | Pass | 0 | Behavioral/content review pending |
| `PAYMENT-GATEWAY.html` | Pass | 1 | Behavioral/content review pending |
| `about.html` | Pass | 0 | Behavioral/content review pending |
| `admin.html` | Pass | 1 | Behavioral/content review pending |
| `advisories.html` | Pass | 0 | Behavioral/content review pending |
| `ai-runtime-defense.html` | Pass | 1 | Behavioral/content review pending |
| `ai-security-ops-hub.html` | Pass | 1 | Behavioral/content review pending |
| `ai-threat-tracker.html` | Pass | 1 | Behavioral/content review pending |
| `alternative-to-mandiant.html` | Pass | 0 | Behavioral/content review pending |
| `alternative-to-recorded-future.html` | Pass | 0 | Behavioral/content review pending |
| `api-docs.html` | Pass | 1 | Behavioral/content review pending |
| `api-key-manager.html` | Pass | 1 | Behavioral/content review pending |
| `api-management-center.html` | Pass | 1 | Behavioral/content review pending |
| `api-reference-card.html` | Pass | 2 | Behavioral/content review pending |
| `billing-center.html` | Pass | 1 | Behavioral/content review pending |
| `billing.html` | Pass | 1 | Behavioral/content review pending |
| `capability-directory.html` | Pass | 1 | Behavioral/content review pending |
| `case-studies.html` | Pass | 0 | Behavioral/content review pending |
| `compare.html` | Pass | 0 | Behavioral/content review pending |
| `compliance.html` | Pass | 0 | Behavioral/content review pending |
| `contact-enterprise.html` | Pass | 1 | Behavioral/content review pending |
| `customer-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `customer-intake.html` | Pass | 1 | Behavioral/content review pending |
| `customer-portal.html` | Pass | 1 | Behavioral/content review pending |
| `customer-success-stories.html` | Pass | 0 | Behavioral/content review pending |
| `customer-success.html` | Pass | 1 | Behavioral/content review pending |
| `customer-value-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `cve.html` | Pass | 1 | Behavioral/content review pending |
| `cves.html` | Pass | 1 | Behavioral/content review pending |
| `cyber-kits.html` | Pass | 1 | Behavioral/content review pending |
| `cyber-watchdog.html` | Pass | 1 | Behavioral/content review pending |
| `daily-operations-center.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard.html` | Pass | 2 | Behavioral/content review pending |
| `demo-intelligence-center.html` | Pass | 1 | Behavioral/content review pending |
| `demo.html` | Pass | 1 | Behavioral/content review pending |
| `dependency-platform.html` | Pass | 1 | Behavioral/content review pending |
| `developer-portal.html` | Pass | 1 | Behavioral/content review pending |
| `editorial-policy.html` | Pass | 0 | Behavioral/content review pending |
| `enterprise-action-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-assurance-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-compliance.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-cyber-intelligence-os.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-demo.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-excellence-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-governance-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-hardening-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-homepage.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-intelligence-health-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-knowledge-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-knowledge-graph.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-onboarding.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-operations.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-pricing.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-procurement-pack.html` | Pass | 0 | Behavioral/content review pending |
| `enterprise-quality-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-security-pack.html` | Pass | 0 | Behavioral/content review pending |
| `enterprise-source-fabric-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-trust-center.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-trust-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `enterprise-use-cases.html` | Pass | 0 | Behavioral/content review pending |
| `enterprise.html` | Pass | 1 | Behavioral/content review pending |
| `eula.html` | Pass | 0 | Behavioral/content review pending |
| `evidence-threat-map.html` | Pass | 1 | Behavioral/content review pending |
| `executive-briefing.html` | Pass | 1 | Behavioral/content review pending |
| `executive-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `executive-reporting-center.html` | Pass | 1 | Behavioral/content review pending |
| `get-api-key.html` | Pass | 2 | Behavioral/content review pending |
| `global-deployment.html` | Pass | 0 | Defects remediated; CI/live verification pending |
| `graph-ops-center.html` | Pass | 1 | Behavioral/content review pending |
| `index.html` | Pass | 21 | Behavioral/content review pending |
| `integration-catalog.html` | Pass | 0 | Behavioral/content review pending |
| `intelligence-archive.html` | Pass | 1 | Behavioral/content review pending |
| `iocs.html` | Pass | 1 | Behavioral/content review pending |
| `kev.html` | Pass | 1 | Behavioral/content review pending |
| `lead-capture.html` | Pass | 1 | Failed-delivery confirmation remediated; live verification pending |
| `lead-pipeline.html` | Pass | 1 | Behavioral/content review pending |
| `login.html` | Pass | 1 | Behavioral/content review pending |
| `lookup.html` | Pass | 1 | Behavioral/content review pending |
| `malware-intel-hub.html` | Pass | 1 | Behavioral/content review pending |
| `methodology.html` | Pass | 0 | Behavioral/content review pending |
| `mssp-customer-center.html` | Pass | 1 | Behavioral/content review pending |
| `mssp-lead-tracker.html` | Pass | 0 | Behavioral/content review pending |
| `mssp-onboarding-kit.html` | Pass | 0 | Behavioral/content review pending |
| `mssp-partner-onboarding.html` | Pass | 0 | Behavioral/content review pending |
| `mssp-partner-portal.html` | Pass | 1 | Behavioral/content review pending |
| `mssp-tenant-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `mssp-training-center.html` | Pass | 0 | Behavioral/content review pending |
| `mssp.html` | Pass | 1 | Behavioral/content review pending |
| `my-exposure-center.html` | Pass | 1 | Behavioral/content review pending |
| `observability.html` | Pass | 1 | Behavioral/content review pending |
| `onboarding.html` | Pass | 1 | Behavioral/content review pending |
| `partner.html` | Pass | 0 | Behavioral/content review pending |
| `payment-confirmation.html` | Pass | 1 | Behavioral/content review pending |
| `payment-status-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `payment-submission.html` | Pass | 1 | Behavioral/content review pending |
| `platform-capabilities.html` | Pass | 0 | Behavioral/content review pending |
| `pricing.html` | Pass | 1 | Behavioral/content review pending |
| `privacy.html` | Pass | 0 | Behavioral/content review pending |
| `ransomware.html` | Pass | 1 | Behavioral/content review pending |
| `reference-architecture.html` | Pass | 0 | Behavioral/content review pending |
| `referral.html` | Pass | 1 | Behavioral/content review pending |
| `revenue-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `roi-calculator.html` | Pass | 1 | Behavioral/content review pending |
| `security-compliance.html` | Pass | 0 | Behavioral/content review pending |
| `security-questionnaire-pack.html` | Pass | 0 | Behavioral/content review pending |
| `sentinel-onboarding.html` | Pass | 1 | Behavioral/content review pending |
| `services.html` | Pass | 1 | Behavioral/content review pending |
| `sla-overview.html` | Pass | 0 | Behavioral/content review pending |
| `sla.html` | Pass | 0 | Behavioral/content review pending |
| `soc-integrations.html` | Pass | 1 | Behavioral/content review pending |
| `soc-operations-center.html` | Pass | 1 | Behavioral/content review pending |
| `soc-workspace.html` | Pass | 1 | Behavioral/content review pending |
| `status.html` | Pass | 1 | Behavioral/content review pending |
| `store.html` | Pass | 1 | Behavioral/content review pending |
| `subscription-management.html` | Pass | 1 | Behavioral/content review pending |
| `support-center.html` | Pass | 1 | Behavioral/content review pending |
| `telemetry-embedding.html` | Pass | 1 | Behavioral/content review pending |
| `telemetry-visibility-ops.html` | Pass | 1 | Behavioral/content review pending |
| `terms.html` | Pass | 0 | Behavioral/content review pending |
| `testimonials.html` | Pass | 0 | Behavioral/content review pending |
| `threat-actors.html` | Pass | 1 | Behavioral/content review pending |
| `threat-intel-certification-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `threats.html` | Pass | 1 | Behavioral/content review pending |
| `trial-center.html` | Pass | 1 | Behavioral/content review pending |
| `trust-center.html` | Pass | 0 | Behavioral/content review pending |
| `unified-ops-hub.html` | Pass | 1 | Behavioral/content review pending |
| `upgrade.html` | Pass | 1 | Behavioral/content review pending |
| `user-test-kit.html` | Pass | 1 | Behavioral/content review pending |
| `value-center.html` | Pass | 1 | Behavioral/content review pending |
| `vendor-assessment-pack.html` | Pass | 0 | Behavioral/content review pending |
| `vulnerabilities.html` | Pass | 1 | Behavioral/content review pending |
| `weekly-brief.html` | Pass | 0 | Behavioral/content review pending |
| `welcome.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/agents_control_panel.html` | Pass | 0 | Behavioral/content review pending |
| `dashboard/analyst_dashboard.html` | Pass | 2 | Defects remediated; CI/live verification pending |
| `dashboard/enterprise-command-center.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/enterprise_dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/enterprise_dashboard_v2.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/mission-control-dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/orchestration_hub.html` | Pass | 2 | Behavioral/content review pending |
| `dashboard/revenue_dashboard.html` | Pass | 2 | Behavioral/content review pending |
| `dashboard/social_distribution.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/source_fabric_dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `dashboard/threat_graph_dashboard.html` | Pass | 1 | Defects remediated; CI/live verification pending |
| `dashboard/web3_dashboard.html` | Pass | 1 | Behavioral/content review pending |
| `api/index.html` | Pass | 1 | Behavioral/content review pending |
| `customer/api-keys.html` | Pass | 1 | Behavioral/content review pending |
| `blog/2026/04/abb-edgenius-management-portal.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/11th-may-threat-intelligence-report.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/cve-2025-68670-discovering-an-rce-vulnerability-in-xrdp.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/hackers-use-fake-deepseek-tui-github-repositories-to-deliver-malware.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/hackers-use-plugx-like-dll-sideloading-chain-in-fake-claude-malware-campaign.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/hackers-use-weaponized-jpeg-file-to-deploy-trojanized-screenconnect-malware.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/hitachi-energy-pcm600.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/ivanti-epmm-cve-2026-6973-rce-under-active-exploitation-grants-admin-level-acces.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/new-cpanel-vulnerabilities-could-allow-file-access-and-remote-code-execution.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/oceanlotus-suspected-of-using-pypi-to-deliver-zichatbot-malware.html` | Pass | 0 | Behavioral/content review pending |
| `blog/2026/05/official-jdownloader-site-served-malware-to-windows-and-linux-users-between-may-.html` | Pass | 0 | Behavioral/content review pending |
| `blog/index.html` | Pass | 0 | Behavioral/content review pending |
| `docs/faq.html` | Pass | 1 | Behavioral/content review pending |
| `docs/index.html` | Pass | 0 | Behavioral/content review pending |
| `docs/quickstart.html` | Pass | 1 | Behavioral/content review pending |

Continuation 2026-10-05: corrected homepage asset cache-version drift and synchronized the pipeline AI Brain template with the shipped block. PRO lead capture now confirms only HTTP-successful delivery, preserves inputs on failure, prevents duplicate pending submissions and removes unsupported response-time/advisory-count claims. Delivery and timeout behavior have executable negative controls; live form submissions were not sent.
