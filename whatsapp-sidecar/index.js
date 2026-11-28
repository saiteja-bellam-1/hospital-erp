// KT HEALTH ERP — WhatsApp Web sidecar. Bound to localhost, token-protected.
// Env: WA_PORT, WA_HOST, WA_TOKEN, WA_AUTH_DIR
import http from 'node:http';
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';

const PORT = Number(process.env.WA_PORT || 9100);
const HOST = process.env.WA_HOST || '127.0.0.1';
const TOKEN = process.env.WA_TOKEN || '';
const AUTH_DIR = process.env.WA_AUTH_DIR || './auth';
if (!TOKEN) { console.error('WA_TOKEN is required'); process.exit(1); }

const logger = pino({ level: 'warn' });
let sock = null;
let state = 'connecting'; // connecting | qr | connected | loggedout
let qrDataUrl = null;
let phone = null;
let stopping = false;

async function start() {
  const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));
  sock = makeWASocket({ auth, version, logger, printQRInTerminal: false, markOnlineOnConnect: false });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async (u) => {
    if (u.qr) { qrDataUrl = await QRCode.toDataURL(u.qr, { margin: 1, width: 280 }); state = 'qr'; }
    if (u.connection === 'open') {
      state = 'connected'; qrDataUrl = null;
      phone = (sock.user?.id || '').split(':')[0].split('@')[0] || null;
    } else if (u.connection === 'close') {
      const code = u.lastDisconnect?.error?.output?.statusCode;
      phone = null;
      if (stopping) return;
      if (code === DisconnectReason.loggedOut) {
        state = 'loggedout'; qrDataUrl = null;
        await wipeAuthAndRestart();
      } else {
        state = 'connecting';
        setTimeout(() => start().catch(console.error), 2000);
      }
    }
  });
}

async function wipeAuthAndRestart() {
  const fs = await import('node:fs/promises');
  await fs.rm(AUTH_DIR, { recursive: true, force: true });
  state = 'connecting';
  setTimeout(() => start().catch(console.error), 500); // fresh QR
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

async function handleSend(body) {
  if (state !== 'connected') throw Object.assign(new Error('WhatsApp is not linked. Scan the QR in Admin → WhatsApp.'), { code: 409 });
  const digits = String(body.phone || '').replace(/\D/g, '');
  if (digits.length < 8) throw Object.assign(new Error('Invalid phone'), { code: 422 });
  const [hit] = (await sock.onWhatsApp(digits)) || [];
  if (!hit?.exists) throw Object.assign(new Error('This number is not on WhatsApp'), { code: 422 });
  const jid = hit.jid;
  if (body.file_base64) {
    const buf = Buffer.from(body.file_base64, 'base64');
    const mt = body.mimetype || 'application/pdf';
    const msg = mt.startsWith('image/')
      ? { image: buf, caption: body.text || undefined, mimetype: mt }
      : { document: buf, mimetype: mt, fileName: body.filename || 'document.pdf', caption: body.text || undefined };
    await sock.sendMessage(jid, msg);
  } else {
    await sock.sendMessage(jid, { text: String(body.text || '') });
  }
}

const server = http.createServer(async (req, res) => {
  if (req.headers['x-token'] !== TOKEN) return reply(res, 401, { error: 'unauthorized' });
  try {
    if (req.method === 'GET' && req.url === '/status') return reply(res, 200, { state, qr: qrDataUrl, phone });
    if (req.method === 'POST' && req.url === '/send') { await handleSend(await readJson(req)); return reply(res, 200, { ok: true }); }
    if (req.method === 'POST' && req.url === '/logout') {
      try { await sock?.logout(); } catch { /* already closed */ }
      return reply(res, 200, { ok: true });
    }
    reply(res, 404, { error: 'not found' });
  } catch (e) {
    reply(res, e.code && Number.isInteger(e.code) ? e.code : 500, { error: e.message || 'failed' });
  }
});
server.listen(PORT, HOST, () => console.log(`whatsapp sidecar on ${HOST}:${PORT}`));
start().catch((e) => { console.error(e); process.exit(1); });
process.on('SIGTERM', () => { stopping = true; server.close(); process.exit(0); });
