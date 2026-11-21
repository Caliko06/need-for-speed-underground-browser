// nfsu.cc/crash: the page's crash beacon (web/boot.js crashSend) -> private R2 bucket nfsu-crash, one JSON line per report.
// Anonymous: no IP and no headers are kept; only the country Cloudflare gives, to see where phones fail. Deploy: tools/crash/deploy.sh.
export default {
  async fetch(req, env) {
    if (req.method !== 'POST') return new Response(null, { status: 405 });
    const body = await req.text();
    if (body.length > 32768) return new Response(null, { status: 413 });
    let j;
    try { j = JSON.parse(body); } catch { return new Response(null, { status: 400 }); }
    if (!j || j.format !== 'rn-crash-1') return new Response(null, { status: 400 });
    j.country = req.cf?.country || '';
    const d = new Date().toISOString();
    await env.CRASH.put(`${d.slice(0, 10)}/${d.slice(11, 19).replace(/:/g, '')}-${crypto.randomUUID().slice(0, 8)}.json`, JSON.stringify(j) + '\n');
    return new Response(null, { status: 204 });
  },
};
