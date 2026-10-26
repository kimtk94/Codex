const { OAuth2Client, GoogleAuth } = require('google-auth-library');
const SPREADSHEET_ID = '1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const RANGES = {
  unanswered: "'Unanswered Emails'!A1:P151",
  priority: "'Email Action Priority'!A1:P151",
  leads: "'Lead Action Priority'!A1:P151",
  health: "'Automation Health'!A1:H51"
};
function configuredOwners() {
  const allowed = (process.env.ALLOWED_OWNER_EMAILS || '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
  return new Set(allowed);
}
module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store, private');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method !== 'GET') return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const audience = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const serviceJSON = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  const allowed = configuredOwners();
  if (!audience || !serviceJSON || !allowed.size) return res.status(503).json({error:'NOT_CONFIGURED'});
  const bearer = /^Bearer (.+)$/.exec(req.headers.authorization || '');
  if (!bearer) return res.status(401).json({error:'SIGN_IN_REQUIRED'});
  try {
    const oauth = new OAuth2Client(audience);
    const ticket = await oauth.verifyIdToken({idToken:bearer[1],audience});
    const payload = ticket.getPayload();
    if (!payload.email_verified || !allowed.has(String(payload.email).toLowerCase()))
      return res.status(403).json({error:'OWNER_ACCESS_DENIED'});
    const creds = JSON.parse(serviceJSON);
    const google = new GoogleAuth({credentials:creds,scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const client = await google.getClient();
    const output = {};
    for (const [name, range] of Object.entries(RANGES)) {
      const url = 'https://sheets.googleapis.com/v4/spreadsheets/' + SPREADSHEET_ID + '/values/' + encodeURIComponent(range);
      const response = await client.request({url});
      const rows = response.data.values || [];
      output[name] = {count: Math.max(0, rows.slice(1).filter(row => row.some(cell => String(cell).trim())).length)};
    }
    return res.status(200).json({owner:'kim-taehoon',updatedAt:new Date().toISOString(),data:output});
  } catch(err) {
    if (/token|jwt|audience|signature|expired/i.test(String(err.message))) return res.status(401).json({error:'INVALID_SIGN_IN'});
    return res.status(502).json({error:'SHEETS_READ_FAILED'});
  }
};
