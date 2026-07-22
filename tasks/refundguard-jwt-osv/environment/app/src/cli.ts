#!/usr/bin/env node
import express from "express";
import {verifyRefundToken} from "./auth.js";
import {analyze} from "./analyze.js";

function flag(name: string): string {
  const i = process.argv.indexOf(name);
  if (i < 0 || !process.argv[i + 1]) throw new Error(`missing ${name}`);
  return process.argv[i + 1];
}

async function main() {
  if (process.argv[2] === "analyze") {
    await analyze(flag("--ledger"), flag("--lockfile"), flag("--database"), flag("--report"));
    return;
  }
  if (process.argv[2] === "serve") {
    const key = process.env.REFUND_JWT_KEY;
    if (!key) throw new Error("REFUND_JWT_KEY is required");
    const app = express(); app.use(express.json());
    app.post("/refunds", (req, res) => {
      const m = /^Bearer (.+)$/.exec(String(req.headers.authorization ?? ""));
      try {
        if (!m) throw new Error("missing token");
        const p = verifyRefundToken(m[1], key);
        res.status(202).json({accepted: true, subject: p.subject, merchant: p.merchant});
      } catch { res.status(401).json({error: "unauthorized"}); }
    });
    app.listen(Number(process.env.PORT ?? "3000"), "127.0.0.1");
    return;
  }
  throw new Error("usage: refundguard serve|analyze");
}
main().catch(e => { console.error(e.message); process.exit(1); });
