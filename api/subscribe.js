// api/subscribe.js
// Vercel serverless function to safely update subscribers.json in GitHub repo
export default async function handler(req, res) {
  // CORS preflight
  if (req.method === "OPTIONS") {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  const { email, action = "subscribe" } = req.body || {};
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ message: "Invalid email" });
  }

  const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
  const OWNER = process.env.REPO_OWNER;
  const REPO = process.env.REPO_NAME;
  const PATH = process.env.SUBSCRIBERS_PATH || "subscribers.json";

  if (!GITHUB_TOKEN || !OWNER || !REPO) {
    return res.status(500).json({ message: "Server misconfigured (missing env vars)" });
  }

  const ghHeaders = {
    Authorization: `token ${GITHUB_TOKEN}`,
    Accept: "application/vnd.github.v3+json",
    "Content-Type": "application/json"
  };

  const getUrl = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${PATH}`;

  async function getFileJson() {
    const r = await fetch(getUrl, { headers: ghHeaders });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`GET failed ${r.status}: ${text}`);
    }
    return r.json();
  }

  async function putFile(contentBase64, sha) {
    const body = {
      message: `${action} ${email}`,
      content: contentBase64,
      sha
    };
    return fetch(getUrl, {
      method: "PUT",
      headers: ghHeaders,
      body: JSON.stringify(body)
    });
  }

  try {
    let attempts = 0;
    const maxAttempts = 4;
    while (attempts < maxAttempts) {
      attempts++;

      // 1) fetch current file
      const fileJson = await getFileJson();
      const sha = fileJson.sha;
      const rawBase64 = fileJson.content || "";
      const decoded = rawBase64 ? Buffer.from(rawBase64, "base64").toString("utf8") : "";
      let subsObj;
      try {
        subsObj = JSON.parse(decoded || '{"emails": []}');
      } catch {
        subsObj = { emails: [] };
      }

      // 2) modify subscriber set
      const set = new Set((subsObj.emails || []).map(e => e.toLowerCase()));
      if (action === "subscribe") set.add(email.toLowerCase());
      else if (action === "unsubscribe") set.delete(email.toLowerCase());
      else return res.status(400).json({ message: "Invalid action" });

      const newObj = { emails: Array.from(set) };
      const newContentBase64 = Buffer.from(JSON.stringify(newObj, null, 2), "utf8").toString("base64");

      // 3) attempt to PUT
      const putRes = await putFile(newContentBase64, sha);

      if (putRes.ok) {
        res.setHeader("Access-Control-Allow-Origin", "*");
        return res.status(200).json({ message: `Successfully ${action}d ${email}` });
      }

      // handle common conflict and retry
      if (putRes.status === 422) {
        // Conflict - someone else updated file concurrently; retry after tiny delay
        await new Promise((r) => setTimeout(r, 300 + Math.floor(Math.random() * 300)));
        continue;
      }

      // other error: return details
      const txt = await putRes.text();
      return res.status(502).json({ message: "Failed to update subscribers.json", detail: txt });
    }

    return res.status(500).json({ message: "Failed to update after multiple attempts (retry limit)" });
  } catch (err) {
    return res.status(500).json({ message: "Server error", detail: String(err) });
  }
}