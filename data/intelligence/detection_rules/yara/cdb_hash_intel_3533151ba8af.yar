rule CDB_SENTINEL_Hash_Intel_3533151ba8af
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-19"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "68e76627798d62555d5287f4488a32c7" ascii nocase

    condition:
        filesize < 100MB and any of them
}