package com.sentinel.keys;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

/** The published Ed25519 public keys that release badges may be signed with. */
public final class Keyring {

    private final Map<String, PublicKey> keys;

    private Keyring(Map<String, PublicKey> keys) {
        this.keys = keys;
    }

    public static Keyring load(Path path) throws IOException {
        String text = Files.readString(path, StandardCharsets.UTF_8);
        JsonObject root = JsonParser.parseString(text).getAsJsonObject();
        JsonArray entries = root.getAsJsonArray("keys");

        Map<String, PublicKey> loaded = new LinkedHashMap<>();
        for (JsonElement entry : entries) {
            JsonObject key = entry.getAsJsonObject();
            String keyId = key.get("key_id").getAsString();
            byte[] der = Base64.getDecoder().decode(key.get("public_key").getAsString());
            loaded.put(keyId, decode(der));
        }
        return new Keyring(loaded);
    }

    private static PublicKey decode(byte[] der) throws IOException {
        try {
            return KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(der));
        } catch (java.security.GeneralSecurityException error) {
            throw new IOException("keyring contains an unusable public key", error);
        }
    }

    public boolean contains(String keyId) {
        return keys.containsKey(keyId);
    }

    public PublicKey publicKey(String keyId) {
        return keys.get(keyId);
    }
}
