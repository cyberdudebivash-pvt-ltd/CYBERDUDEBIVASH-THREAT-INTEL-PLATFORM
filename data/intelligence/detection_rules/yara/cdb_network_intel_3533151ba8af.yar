rule CDB_SENTINEL_Network_Intel_3533151ba8af
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-19"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "3533151ba8af"
        ioc_count = 24

    strings:
        $ip_0 = "169.254.169.254" ascii wide nocase
        $ip_1 = "6.6.6.6" ascii wide nocase
        $dom_2 = "roblox.com" ascii wide nocase
        $dom_3 = "post-manifacture-desanpliation.com" ascii wide nocase
        $dom_4 = "guz-nik.wranh.info" ascii wide nocase
        $dom_5 = "www.rbx4kb.blogspot.com" ascii wide nocase
        $dom_6 = "shopee-id2775.blogspot.com" ascii wide nocase
        $dom_7 = "www.shopee-id2775.blogspot.com" ascii wide nocase
        $dom_8 = "jeliffin.s3.eu-central-3.ionoscloud.com" ascii wide nocase
        $dom_9 = "0bf1eaed1f65f5df07365b728b3bb2a18d89.net" ascii wide nocase
        $dom_10 = "amankhan02007.github.io" ascii wide nocase
        $dom_11 = "rlaonchambry.top" ascii wide nocase
        $dom_12 = "chasejackpot.xyz" ascii wide nocase
        $dom_13 = "the-pro-1391.github.io" ascii wide nocase
        $dom_14 = "ww547.scotiabano.com" ascii wide nocase
        $dom_15 = "siddharthgaikwad-git.github.io" ascii wide nocase
        $dom_16 = "sagarsrivastava5201-code.github.io" ascii wide nocase
        $dom_17 = "varda27.github.io" ascii wide nocase
        $dom_18 = "aidenpiearce.github.io" ascii wide nocase
        $dom_19 = "f005.backblazeb2.com" ascii wide nocase
        $dom_20 = "document-share.exceptionalsonepc.com" ascii wide nocase
        $dom_21 = "socket.io" ascii wide nocase
        $dom_22 = "ssf-int.com" ascii wide nocase
        $dom_23 = "nyklawfirm.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}