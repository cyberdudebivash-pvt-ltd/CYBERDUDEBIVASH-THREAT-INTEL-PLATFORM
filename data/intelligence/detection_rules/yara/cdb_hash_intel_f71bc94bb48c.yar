rule CDB_SENTINEL_Hash_Intel_f71bc94bb48c
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-14"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "45766572797468696e67206973206e6f742077686174206974207365656d730a" ascii nocase
        $h_1 = "99382535900423182128231632453729" ascii nocase

    condition:
        filesize < 100MB and any of them
}