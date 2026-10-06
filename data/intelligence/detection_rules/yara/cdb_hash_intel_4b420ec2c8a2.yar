rule CDB_SENTINEL_Hash_Intel_4b420ec2c8a2
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-20"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "48576964081632940175880915860332" ascii nocase

    condition:
        filesize < 100MB and any of them
}