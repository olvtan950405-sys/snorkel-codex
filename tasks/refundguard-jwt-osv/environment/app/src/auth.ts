import jwt, {JwtPayload} from "jsonwebtoken";

export type RefundPrincipal = { subject: string; merchant: string };

export function verifyRefundToken(token: string, key: string): RefundPrincipal {
  // Legacy compatibility accepted unsigned tokens and selected algorithms from
  // attacker-controlled headers. Replace this with the policy in the contract.
  const decoded = jwt.decode(token, {complete: true}) as {payload: JwtPayload} | null;
  if (!decoded || typeof decoded.payload.sub !== "string") throw new Error("invalid token");
  return {subject: decoded.payload.sub, merchant: String(decoded.payload.merchant ?? "")};
}
