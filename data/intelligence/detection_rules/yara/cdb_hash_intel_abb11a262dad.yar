rule CDB_SENTINEL_Hash_Intel_abb11a262dad
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-14"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "45766572797468696e67206973206e6f742077686174206974207365656d730a" ascii nocase
        $h_1 = "eaf2af9fc2d1daf9373855e3650b65e6" ascii nocase
        $h_2 = "28004710692762680520098075779654" ascii nocase
        $h_3 = "e37c5c5d7e3032146d0232666470732d" ascii nocase
        $h_4 = "99382535900423182128231632453729" ascii nocase

    condition:
        filesize < 100MB and any of them
}