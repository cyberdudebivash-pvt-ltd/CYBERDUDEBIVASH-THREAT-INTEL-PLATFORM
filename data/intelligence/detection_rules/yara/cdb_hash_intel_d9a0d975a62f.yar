rule CDB_SENTINEL_Hash_Intel_d9a0d975a62f
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-19"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "db3c8730ae37ad3e8a7ff1b0d0940669" ascii nocase
        $h_1 = "68e76627798d62555d5287f4488a32c7" ascii nocase

    condition:
        filesize < 100MB and any of them
}