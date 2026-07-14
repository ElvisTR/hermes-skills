// doviz.com live-price starter — Node.js (npm i ws)
//
// Two steps, exactly how the site works:
//   1. Scrape the page HTML once to learn the catalog (every data-socket-key).
//   2. Open the WebSocket, join a room with those keys, print live ticks.
//
// Run: node starter.js            (streams a few sample FX + gold keys)
//      node starter.js --all      (discovers full catalog from HTML, streams it)

const WebSocket = require("ws");

const SITES = {
  fx:   "https://kur.doviz.com/",
  gold: "https://altin.doviz.com/",
};

// --- Step 1: discover the full catalog from the page HTML ------------------
// Collect every unique data-socket-key. No parser dependency: a regex over the
// rendered HTML is enough because each price cell carries the attribute.
async function discoverKeys(url) {
  const html = await (await fetch(url)).text();
  const keys = new Set();
  for (const m of html.matchAll(/data-socket-key="([^"]+)"/g)) keys.add(m[1]);
  return [...keys].filter(Boolean);
}

// --- Step 2: subscribe over the WebSocket ----------------------------------
function stream(keys) {
  const nick = "webkullanici_" + ((Math.random() * 1000) | 0);
  const room = "info@" + keys.join(",") + "/" + nick;

  // The subprotocol "nokta-chat-json" is REQUIRED (second arg).
  const ws = new WebSocket("wss://socket.doviz.com", "nokta-chat-json");

  ws.on("open", () => {
    ws.send(JSON.stringify({
      action: "auth",
      data: { username: "", password: "", joinTo: room },
    }));
    console.error(`joined ${keys.length} keys: ${keys.join(", ")}`);
  });

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString()); } catch { return; }
    if (msg.a !== "m") return;               // ignore ack / other events
    const m = msg.m;                         // one item's tick
    const kind = m.t === "G" ? "GOLD" : "FX ";
    const when = new Date(m.ts * 1000).toLocaleTimeString(); // ts is SECONDS
    // Compute on the numeric fields, not the TR-locale strings.
    console.log(
      `${kind} ${m.k.padEnd(18)} bid=${m.bid}  ask=${m.ask}  ` +
      `last=${m.sn}  hi=${m.hn}  lo=${m.ln}  chg=${m.cn}%  @${when}`
    );
  });

  ws.on("error", (e) => console.error("ws error:", e.message));
  ws.on("close", () => console.error("socket closed"));
}

// --- main ------------------------------------------------------------------
(async () => {
  let keys;
  if (process.argv.includes("--all")) {
    const [fx, gold] = await Promise.all([
      discoverKeys(SITES.fx),
      discoverKeys(SITES.gold),
    ]);
    keys = [...new Set([...fx, ...gold])];
  } else {
    // A few examples — swap in any keys from the catalog.
    keys = ["USD", "EUR", "GBP", "gram-altin", "gram-has-altin", "ons"];
  }
  stream(keys);
})();
