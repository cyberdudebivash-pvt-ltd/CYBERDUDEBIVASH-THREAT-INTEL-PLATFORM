rule CDB_SENTINEL_Hash_Intel_000aae8e5977
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-24"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "57a9a03e3cc5c5a0fea56cfe8c2eec0d" ascii nocase

    condition:
        filesize < 100MB and any of them
}