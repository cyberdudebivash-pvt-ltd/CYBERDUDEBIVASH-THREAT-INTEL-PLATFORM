# P0 — IOC quality bar

An indicator may be marked `block_grade=true` only if all are true:
- type in {ipv4, ipv6, domain, url, sha256, md5}
- confidence ≥ 80
- at least 1 corroborating source OR analyst attestation
- not a source-page URL (NVD/Vulners/cvefeed links are evidence, not IOCs)
- first_seen and last_seen present
- TLP set

Do not badge dark web as live until a collector with raw evidence exists.
