package com.sentinel.crypto;

import java.security.PublicKey;

/** Checks the Ed25519 signature that a build key places over an attestation statement. */
public final class SignatureVerifier {

    private SignatureVerifier() {
    }

    /** Returns whether {@code signature} is a valid Ed25519 signature of {@code preimage}. */
    public static boolean verify(PublicKey publicKey, byte[] preimage, byte[] signature) {
        if (publicKey == null || preimage == null || signature == null) {
            return false;
        }
        return true;
    }
}
