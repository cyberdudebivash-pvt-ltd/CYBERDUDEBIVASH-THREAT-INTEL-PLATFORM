"""Additive AI-intel adapter. Does not write the platform threat database."""

INTEL_SCHEMA = "sentinel-apex.intel.v1"


def empty_state():
    return {"cursor": 0, "records": {}}


def _copy_state(state):
    return {"cursor": state["cursor"], "records": dict(state["records"])}


def apply_master_page(state, page):
    if not isinstance(page, dict):
        return {"state": state, "applied": 0, "removed": 0, "error": "page is not an object"}
    if page.get("schema") not in (None, INTEL_SCHEMA):
        return {"state": state, "applied": 0, "removed": 0, "error": "schema mismatch"}
    if page.get("tlp") not in (None, "CLEAR"):
        return {"state": state, "applied": 0, "removed": 0, "error": "restricted distribution"}
    nxt = page.get("next_cursor")
    if not isinstance(nxt, int) or isinstance(nxt, bool) or nxt < state["cursor"]:
        return {"state": state, "applied": 0, "removed": 0, "error": "cursor is missing or moved backwards"}
    records = page.get("records")
    if not isinstance(records, list):
        return {"state": state, "applied": 0, "removed": 0, "error": "records must be an array"}
    next_state = _copy_state(state)
    applied = 0
    for raw in records:
        if not isinstance(raw, dict):
            return {"state": state, "applied": 0, "removed": 0, "error": "invalid record"}
        if not all(isinstance(raw.get(key), str) and raw.get(key) for key in ("id", "primary_source_id", "canonical_source_url")):
            return {"state": state, "applied": 0, "removed": 0, "error": "record missing identity or canonical source"}
        if raw.get("tlp") not in (None, "CLEAR"):
            return {"state": state, "applied": 0, "removed": 0, "error": "restricted distribution"}
        evidence = None
        if raw.get("evidence") is not None:
            if not isinstance(raw["evidence"], list):
                return {"state": state, "applied": 0, "removed": 0, "error": "evidence must be an array"}
            evidence = []
            for item in raw["evidence"]:
                if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("source_id", "url", "claim")):
                    return {"state": state, "applied": 0, "removed": 0, "error": "evidence missing source_id"}
                source_id = "unresolved" if item["source_id"] == "unattributed" else item["source_id"]
                evidence.append({"source_id": source_id, "url": item["url"], "claim": item["claim"]})
        corroborating = []
        for item in evidence or []:
            if item["source_id"] not in ("unresolved", "unattributed") and item["source_id"] not in corroborating:
                corroborating.append(item["source_id"])
        stored = {
            "id": raw["id"],
            "primary_source_id": raw["primary_source_id"],
            "canonical_source_url": raw["canonical_source_url"],
            "title": raw["title"] if isinstance(raw.get("title"), str) else None,
            "source_published_at": raw["source_published_at"] if isinstance(raw.get("source_published_at"), str) else None,
            "verification_state": raw["verification_state"] if isinstance(raw.get("verification_state"), str) else None,
            "cvss_score": raw["cvss_score"] if isinstance(raw.get("cvss_score"), (int, float)) and not isinstance(raw.get("cvss_score"), bool) else None,
            "kev_status": raw["kev_status"] if isinstance(raw.get("kev_status"), bool) else None,
            "evidence": evidence,
            "corroborating_source_ids": corroborating,
        }
        if next_state["records"].get(stored["id"]) != stored:
            applied += 1
        next_state["records"][stored["id"]] = stored
    removed = 0
    events = page.get("events")
    if events is not None:
        if not isinstance(events, list):
            return {"state": state, "applied": 0, "removed": 0, "error": "events must be an array"}
        for event in events:
            if not isinstance(event, dict):
                return {"state": state, "applied": 0, "removed": 0, "error": "invalid event"}
            record_id = event.get("record_id")
            if event.get("visible") is False and isinstance(record_id, str) and record_id in next_state["records"]:
                del next_state["records"][record_id]
                removed += 1
    next_state["cursor"] = nxt
    return {"state": next_state, "applied": applied, "removed": removed, "error": None}
