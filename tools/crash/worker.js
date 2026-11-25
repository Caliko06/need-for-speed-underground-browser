// nfsu.cc/crash: crash beacon (rn-crash-1) and anonymous funnel beacon (rn-funnel-1) -> private R2 bucket nfsu-crash.
// Anonymous: no IP and no headers are kept; only the country Cloudflare gives. Deploy: tools/crash/deploy.sh.
export default {
  async fetch(req, env) {
    if (req.method !== 'POST') return new Response(null, { status: 405 });
    const body = await req.text();
    if (body.length > 32768) return new Response(null, { status: 413 });
    let j;
    try { j = JSON.parse(body); } catch { return new Response(null, { status: 400 }); }
    if (!j || (j.format !== 'rn-crash-1' && j.format !== 'rn-funnel-1')) return new Response(null, { status: 400 });
    const d = new Date().toISOString();
    const key = `${d.slice(0, 10)}/${d.slice(11, 19).replace(/:/g, '')}-${crypto.randomUUID().slice(0, 8)}.json`;
    if (j.format === 'rn-funnel-1') {
      if (body.length > 1024) return new Response(null, { status: 413 });
      const out = {
        format: 'rn-funnel-1', v: String(j.v || '').slice(0, 20), sid: String(j.sid || '').slice(0, 40),
        t: Number(j.t) || 0, tr: Number(j.tr) || 0, framed: !!j.framed,
        ev: j.ev === 'run' ? 'run' : 'stop',
        tier: String(j.tier || '').slice(0, 16), coarse: !!j.coarse, os: String(j.os || '').slice(0, 16),
        load_ms: Number(j.load_ms) || 0, ab_ms: Number(j.ab_ms) || 0, wasm_ms: Number(j.wasm_ms) || 0,
        warm: !!j.warm, reason: String(j.reason || '').slice(0, 120), country: req.cf?.country || '',
      };
      await env.CRASH.put(`funnel/${key}`, JSON.stringify(out) + '\n');
      return new Response(null, { status: 204 });
    }
    j.country = req.cf?.country || '';
    await env.CRASH.put(key, JSON.stringify(j) + '\n');
    return new Response(null, { status: 204 });
  },
};
