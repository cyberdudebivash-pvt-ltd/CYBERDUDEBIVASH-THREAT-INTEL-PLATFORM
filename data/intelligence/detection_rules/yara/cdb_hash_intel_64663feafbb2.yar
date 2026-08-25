rule CDB_SENTINEL_Hash_Intel_64663feafbb2
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-25"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "40701032093677820273245354551556" ascii nocase
        $h_1 = "30756336284493437113099631096745" ascii nocase
        $h_2 = "42386811862281191092537538121647" ascii nocase
        $h_3 = "877ee6f8d6e79dbedc6b0c6dc444b884" ascii nocase
        $h_4 = "97520631505570654589330161242746" ascii nocase
        $h_5 = "87969680078065820214840649414941" ascii nocase
        $h_6 = "57a9a03e3cc5c5a0fea56cfe8c2eec0d" ascii nocase

    condition:
        filesize < 100MB and any of them
}