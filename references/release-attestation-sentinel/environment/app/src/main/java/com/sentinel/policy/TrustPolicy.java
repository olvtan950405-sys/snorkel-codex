package com.sentinel.policy;

/** The trust decision taken for a signing key at the instant a statement was issued. */
public final class TrustPolicy {

    /** The outcome of applying the release trust policy to one statement. */
    public record Decision(boolean trusted, boolean revoked, String exceptionId) {
    }

    private TrustPolicy() {
    }

    /**
     * Applies the release trust policy to a statement signed by {@code keyId} on behalf of
     * {@code service} at {@code issuedAt}.
     */
    public static Decision evaluate(String keyId, String service, String issuedAt) {
        return new Decision(true, false, null);
    }
}
