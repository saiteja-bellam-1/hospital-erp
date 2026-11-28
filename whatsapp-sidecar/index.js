// KT HEALTH ERP — WhatsApp Web sidecar. Bound to localhost, token-protected.
// Holds one linked-device session per slot (primary, secondary, ...) so the
// ERP can fail over to another number when one is down.
// Env: WA_PORT, WA_HOST, WA_TOKEN, WA_AUTH_DIR, WA_SLOTS (default "primary,secondary")
import http from 'node:http';
import fs from 'node:fs';
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';

const API_VERSION = 2;
const PORT = Number(process.env.WA_PORT || 9100);
const HOST = process.env.WA_HOST || '127.0.0.1';
const TOKEN = process.env.WA_TOKEN || '';
const AUTH_DIR = process.env.WA_AUTH_DIR || './auth';
const SLOTS = (process.env.WA_SLOTS || 'primary,secondary').split(',').map((s) => s.trim()).filter(Boolean);
const PRIMARY = SLOTS[0];
if (!TOKEN) { console.error('WA_TOKEN is required'); process.exit(1); }

const logger = pino({ level: 'warn' });
let shuttingDown = false;

// The primary keeps the original auth folder so existing links survive.
const authDirFor = (slot) => (slot === PRIMARY ? AUTH_DIR : `${AUTH_DIR}-${slot}`);
const hasCreds = (slot) => fs.existsSync(`${authDirFor(slot)}/creds.json`);

// slot -> { sock, state: off|connecting|qr|connected|loggedout, qr, phone, gen }
const sessions = Object.fromEntries(SLOTS.map((s) => [s, { sock: null, state: 'off', qr: null, phone: null, gen: 0 }]));

async function start(slot) {
  const s = sessions[slot];
  const gen = ++s.gen; // ignore events from sockets replaced since
  s.state = 'connecting';
  const { state: auth, saveCreds } = await useMultiFileAuthState(authDirFor(slot));
  const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));
  const sock = makeWASocket({ auth, version, logger, printQRInTerminal: false, markOnlineOnConnect: false });
  s.sock = sock;
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async (u) => {
    if (gen !== s.gen) return;
    if (u.qr) { s.qr = await QRCode.toDataURL(u.qr, { margin: 1, width: 280 }); s.state = 'qr'; }
    if (u.connection === 'open') {
      s.state = 'connected'; s.qr = null;
      s.phone = (sock.user?.id || '').split(':')[0].split('@')[0] || null;
    } else if (u.connection === 'close') {
      const code = u.lastDisconnect?.error?.output?.statusCode;
      s.phone = null;
      if (shuttingDown || s.state === 'off') return;
      if (code === DisconnectReason.loggedOut) {
        await wipe(slot);
        // Primary always offers a fresh QR; other slots wait until asked.
        if (slot === PRIMARY) setTimeout(() => start(slot).catch(console.error), 500);
        else { s.state = 'off'; s.qr = null; }
      } else {
        s.state = 'connecting';
        setTimeout(() => { if (gen === s.gen) start(slot).catch(console.error); }, 2000);
      }
    }
  });
}

async function wipe(slot) {
  const s = sessions[slot];
  s.qr = null; s.phone = null;
  await fs.promises.rm(authDirFor(slot), { recursive: true, force: true });
}

async function stopSlot(slot) {
  const s = sessions[slot];
  s.gen += 1; // drop pending reconnects
  s.state = 'off';
  try { s.sock?.end(undefined); } catch { /* already closed */ }
  s.sock = null; s.qr = null; s.phone = null;
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', (c) => { size += c.length; if (size > 25 * 1024 * 1024) { reject(new Error('too large')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString() || '{}')); } catch (e) { reject(e); } });
    req.on('error', reject);
  });
}
const reply = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
const fail = (code, message) => Object.assign(new Error(message), { code });
const slotOf = (body) => {
  const slot = body?.slot || PRIMARY;
  if (!sessions[slot]) throw fail(422, `Unknown WhatsApp slot "${slot}"`);
  return slot;
};
const view = (slot) => {
  const s = sessions[slot];
  return { slot, state: s.state, qr: s.qr, phone: s.phone };
};

async function handleSend(body) {
  const slot = slotOf(body);
  const s = sessions[slot];
  if (s.state !== 'connected') throw fail(409, `WhatsApp ${slot} number is not linked.`);
  const digits = String(body.phone || '').replace(/\D/g, '');
  if (digits.length < 8) throw fail(422, 'Invalid phone');
  const [hit] = (await s.sock.onWhatsApp(digits)) || [];
  if (!hit?.exists) throw fail(422, 'This number is not on WhatsApp');
  const jid = hit.jid;
  if (body.file_base64) {
    const buf = Buffer.from(body.file_base64, 'base64');
    const mt = body.mimetype || 'application/pdf';
    const msg = mt.startsWith('image/')
      ? { image: buf, caption: body.text || undefined, mimetype: mt }
      : { document: buf, mimetype: mt, fileName: body.filename || 'document.pdf', caption: body.text || undefined };
    await s.sock.sendMessage(jid, msg);
  } else {
    await s.sock.sendMessage(jid, { text: String(body.text || '') });
  }
  return slot;
}

const server = http.createServer(async (req, res) => {
  if (req.headers['x-token'] !== TOKEN) return reply(res, 401, { error: 'unauthorized' });
  try {
    if (req.method === 'GET' && req.url === '/status') {
      // Top-level fields describe the primary (older ERP builds read these).
      return reply(res, 200, {
        ...view(PRIMARY),
        version: API_VERSION,
        slots: SLOTS,
        sessions: Object.fromEntries(SLOTS.map((s) => [s, view(s)])),
      });
    }
    if (req.method === 'POST' && req.url === '/send') {
      const slot = await handleSend(await readJson(req));
      return reply(res, 200, { ok: true, slot });
    }
    if (req.method === 'POST' && req.url === '/start') {
      const slot = slotOf(await readJson(req));
      if (sessions[slot].state === 'off' || sessions[slot].state === 'loggedout') await start(slot);
      return reply(res, 200, view(slot));
    }
    if (req.method === 'POST' && req.url === '/logout') {
      const slot = slotOf(await readJson(req));
      const s = sessions[slot];
      if (slot === PRIMARY) {
        try { await s.sock?.logout(); } catch { /* already closed */ }
      } else {
        // Unlinking a backup number turns that slot off instead of showing a new QR.
        const sock = s.sock;
        await stopSlot(slot);
        try { await sock?.logout(); } catch { /* already closed */ }
        await wipe(slot);
      }
      return reply(res, 200, { ok: true });
    }
    reply(res, 404, { error: 'not found' });
  } catch (e) {
    reply(res, e.code && Number.isInteger(e.code) ? e.code : 500, { error: e.message || 'failed' });
  }
});
server.listen(PORT, HOST, () => console.log(`whatsapp sidecar on ${HOST}:${PORT} slots=${SLOTS.join(',')}`));

// Primary always runs; other slots resume only if they were linked before.
for (const slot of SLOTS) {
  if (slot === PRIMARY || hasCreds(slot)) start(slot).catch((e) => { console.error(slot, e); });
}

// Exit when the ERP backend dies (upgrade, crash, End Task) so node.exe never
// lingers holding files in the install folder or the WhatsApp session.
const PARENT_PID = Number(process.env.WA_PARENT_PID || 0);
if (PARENT_PID) {
  setInterval(() => {
    try { process.kill(PARENT_PID, 0); } catch (e) { if (e.code === 'ESRCH') process.exit(0); }
  }, 5000);
}
process.on('SIGTERM', () => { shuttingDown = true; server.close(); process.exit(0); });
