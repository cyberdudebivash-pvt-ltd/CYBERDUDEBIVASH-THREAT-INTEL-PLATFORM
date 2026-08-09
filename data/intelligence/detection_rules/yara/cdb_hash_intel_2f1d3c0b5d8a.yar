rule CDB_SENTINEL_Hash_Intel_2f1d3c0b5d8a
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-09"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "42904738446208678593099227646059" ascii nocase
        $h_1 = "62163753765523904476096247126035" ascii nocase

    condition:
        filesize < 100MB and any of them
}