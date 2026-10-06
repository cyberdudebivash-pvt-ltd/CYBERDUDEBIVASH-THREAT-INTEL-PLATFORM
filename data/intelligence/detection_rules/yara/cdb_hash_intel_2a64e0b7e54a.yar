rule CDB_SENTINEL_Hash_Intel_2a64e0b7e54a
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-18"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "32b5de7789f0bdaa8a8d9800f9930cde" ascii nocase

    condition:
        filesize < 100MB and any of them
}