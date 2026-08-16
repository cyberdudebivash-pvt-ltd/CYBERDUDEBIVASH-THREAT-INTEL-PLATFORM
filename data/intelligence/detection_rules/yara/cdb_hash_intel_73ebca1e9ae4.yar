rule CDB_SENTINEL_Hash_Intel_73ebca1e9ae4
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-16"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "a33e7aeaeb96e4dc027fb154fdd87955" ascii nocase
        $h_1 = "a3810e1a6d61e1b21e34472b4bf7178c" ascii nocase
        $h_2 = "1205b8cc5805ae3c3c9ab53d54ff4a85" ascii nocase

    condition:
        filesize < 100MB and any of them
}