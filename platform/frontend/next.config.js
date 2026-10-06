/** @type {import('next').NextConfig} */
// PRODUCTION-TRUTH FIX (release hardening -- revenue mandate): this app has
// zero API routes, no middleware, no server actions, no dynamic
// cookies()/headers() usage (confirmed via repo-wide search) -- every route
// is prerendered static content (SSG via generateStaticParams). It was
// building successfully but was never actually deployed anywhere (built for
// output:"standalone", a Node server target, with no publish step in any
// CI workflow). Switched to output:"export" -- confirmed a clean build of
// all 112 routes -- so it can be deployed as plain static files rather than
// needing a Node server host that doesn't exist yet.
//
// The headers() function above is a no-op under output:"export" (Next.js
// only applies custom headers via its own server, which static export
// doesn't have -- warns "will not automatically work with output: export"
// at build time). Removed rather than left silently ineffective. Replaced
// with two things: CSP + Referrer-Policy as <meta> tags in the root layout
// (the same working pattern already used by this repo's root index.html,
// since meta tags are the only header-equivalent a plain static host can
// serve), and the full header set in public/_headers -- the standard
// Cloudflare Pages convention -- for when deployed there, since Pages
// serves that file's rules as real HTTP response headers with no gaps.
const nextConfig = {
  output: "export",
  poweredByHeader: false,
};
module.exports = nextConfig;
