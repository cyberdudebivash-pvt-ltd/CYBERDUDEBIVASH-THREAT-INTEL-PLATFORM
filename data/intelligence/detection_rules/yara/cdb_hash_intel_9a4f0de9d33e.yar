rule CDB_SENTINEL_Hash_Intel_9a4f0de9d33e
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-23"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "34e78f2f5695b5a2170c46d278606956af483f3e056af4e1de393a377b52e4d5" ascii nocase
        $h_1 = "60f84723f9ab9f904044f710f98efb70" ascii nocase
        $h_2 = "4d55fb8ca3ab4f4bb6795606a458b59a" ascii nocase
        $h_3 = "ce79fb40ba385ac6b2f6112eac4a5546" ascii nocase
        $h_4 = "c0e5df1c967a0801b4a2b562d53341a7" ascii nocase
        $h_5 = "48576964081632940175880915860332" ascii nocase

    condition:
        filesize < 100MB and any of them
}