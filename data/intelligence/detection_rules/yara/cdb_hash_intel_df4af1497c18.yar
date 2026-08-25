rule CDB_SENTINEL_Hash_Intel_df4af1497c18
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects files referencing known malicious hashes"
        date = "2026-08-25"
        severity = "critical"
        reference = "https://intel.cyberdudebivash.com"

    strings:
        $h_0 = "877ee6f8d6e79dbedc6b0c6dc444b884" ascii nocase
        $h_1 = "97520631505570654589330161242746" ascii nocase
        $h_2 = "87969680078065820214840649414941" ascii nocase
        $h_3 = "57a9a03e3cc5c5a0fea56cfe8c2eec0d" ascii nocase

    condition:
        filesize < 100MB and any of them
}