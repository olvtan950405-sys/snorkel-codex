package com.sentinel.badge;

/** Reads the attestation payload embedded in a release badge PNG via the native extractor. */
public final class NativeBadgeReader {

    static {
        System.loadLibrary("attest");
    }

    private NativeBadgeReader() {
    }

    private static native byte[] extract(byte[] png);

    /**
     * Returns the attestation payload carried by the badge, or {@code null} when the badge does not
     * carry a readable payload.
     */
    public static byte[] extractPayload(byte[] png) {
        return extract(png);
    }
}
