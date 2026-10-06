rule CDB_SENTINEL_Hash_Intel_eb833796b8d5
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-17"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "26fe1567f2c5588bb2484acc40040987" ascii nocase

    condition:
        filesize < 100MB and any of them
}