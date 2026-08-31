# integrations/

Two different things live in this directory -- read this before adding to
either.

## Customer-facing pull connectors (`splunk/`, `elastic/`, `misp/`, `opencti/`)

Scripts and config a SOC team runs **against their own SIEM/SOAR/TIP**,
pulling from this platform's real, live, tier-gated public API using their
own API key: `GET /api/siem/splunk`, `GET /api/siem/sentinel`,
`GET /api/siem/qradar`, `GET /api/misp/export` (all
`workers/intel-gateway/src/enterprise-endpoints.js`, ENTERPRISE-gated), and
`GET /taxii/` (`workers/intel-gateway/src/index.js` + `taxii.js`,
PRO/ENTERPRISE-gated). Every one of these calls a real, already-deployed
endpoint -- none of them is a second implementation of feed logic that
already lives in the Worker.

## Legacy top-level scripts (`*.py` directly in this directory)

`splunk_hec_connector.py`, `qradar_leef_connector.py`,
`ms_sentinel_connector.py`, `detection_engine.py`, `actor_matrix.py`,
`remediation_engine.py` are pre-existing and **not part of this addition**.
They are a different design (this platform pushing outbound to a
customer's SIEM via HEC/syslog, reading a local `data/apex_v2_manifest.json`
snapshot) from the pull-based connectors above, and as of this writing are
not wired into any CI workflow or invoked by anything else in the repo --
`detection_engine.py`/`actor_matrix.py` in particular are stale forks of
the real, actively-used versions at `agent/integrations/detection_engine.py`
and `agent/integrations/actor_matrix.py` (imported by
`agent/sentinel_blogger.py`, wired into `.github/workflows/sentinel-blogger.yml`).
Left in place per this repo's deprecate-don't-delete policy; do not build
new work on top of them without first re-verifying that status.
