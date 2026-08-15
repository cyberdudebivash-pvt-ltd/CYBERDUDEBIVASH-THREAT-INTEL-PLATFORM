rule CDB_SENTINEL_Hash_Intel_3bda11d046b7
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-15"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "32d387ed9b13e49d41563f07aa049be2" ascii nocase

    condition:
        filesize < 100MB and any of them
}