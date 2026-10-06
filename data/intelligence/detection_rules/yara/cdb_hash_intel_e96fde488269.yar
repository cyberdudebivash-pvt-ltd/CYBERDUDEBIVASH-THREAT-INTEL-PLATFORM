rule CDB_SENTINEL_Hash_Intel_e96fde488269
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-13"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "99382535900423182128231632453729" ascii nocase

    condition:
        filesize < 100MB and any of them
}