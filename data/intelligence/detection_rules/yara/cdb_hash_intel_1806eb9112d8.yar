rule CDB_SENTINEL_Hash_Intel_1806eb9112d8
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-21"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "4d55fb8ca3ab4f4bb6795606a458b59a" ascii nocase
        $h_1 = "48576964081632940175880915860332" ascii nocase
        $h_2 = "ce79fb40ba385ac6b2f6112eac4a5546" ascii nocase
        $h_3 = "c0e5df1c967a0801b4a2b562d53341a7" ascii nocase

    condition:
        filesize < 100MB and any of them
}