import jwt, {JwtPayload} from "jsonwebtoken";

export type RefundPrincipal = { subject: string; merchant: string };

export function verifyRefundToken(token: string, key: string): RefundPrincipal {
  const p = jwt.verify(token, key, {
    algorithms: ["HS256"], issuer: "payments-api", audience: "refunds", clockTolerance: 0,
  }) as JwtPayload;
  if (typeof p.sub !== "string" || !p.sub || typeof p.merchant !== "string" || !p.merchant ||
      typeof p.scope !== "string" || !p.scope.split(/\s+/).includes("refund:write") ||
      !Number.isInteger(p.iat) || !Number.isInteger(p.exp)) throw new Error("invalid claims");
  return {subject: p.sub, merchant: p.merchant};
}
