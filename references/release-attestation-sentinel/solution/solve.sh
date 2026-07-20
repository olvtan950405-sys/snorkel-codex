#!/usr/bin/env bash
set -euo pipefail

cd "${APP_DIR:-/app}"

# The native extractor is rewritten to size the payload buffer from the total length of every
# attestation chunk, to validate each chunk CRC, to keep every access inside the PNG buffer, and to
# return the collected length rather than treating the payload as a C string.  The Java worker is
# completed so that the signature is checked over the canonical statement bytes, the trust, rotation,
# exception, tag and branch rules from the incident-room archive are applied in precedence order, and
# the snapshot is emitted as canonical JSON with a digest over the badge array.

cat > native/attest.c <<'EOF_ATTEST_C'
#include "attest.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static const unsigned char PNG_MAGIC[8] = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};

static const unsigned char CHUNK_ATTESTATION[4] = {'a', 't', 'S', 't'};
static const unsigned char CHUNK_END[4] = {'I', 'E', 'N', 'D'};

static const uint32_t CRC_POLYNOMIAL = 0xEDB88320u;

static uint32_t crc32_update(uint32_t crc, const unsigned char *bytes, size_t length)
{
    crc ^= 0xFFFFFFFFu;
    for (size_t index = 0; index < length; index++) {
        crc ^= bytes[index];
        for (int bit = 0; bit < 8; bit++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (CRC_POLYNOMIAL & mask);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

static uint32_t read_be32(const unsigned char *bytes)
{
    return ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16) | ((uint32_t)bytes[2] << 8) |
           (uint32_t)bytes[3];
}

/*
 * Walk the PNG chunk stream, applying "visit" to each atSt chunk's data.  Returns 0 when every
 * chunk is well formed and its CRC matches, and non-zero on any malformed chunk.
 */
static int walk_chunks(const unsigned char *png, size_t png_len,
                       void (*visit)(const unsigned char *, size_t, void *), void *context)
{
    size_t offset = 8;
    while (offset + 8 <= png_len) {
        size_t length = read_be32(png + offset);
        const unsigned char *type = png + offset + 4;

        /* length + type + data + crc must all lie inside the buffer. */
        if (length > png_len || offset + 12 > png_len || length > png_len - offset - 12) {
            return 1;
        }

        const unsigned char *data = png + offset + 8;
        uint32_t stored_crc = read_be32(data + length);

        /* The chunk CRC covers the type field followed by the chunk data. */
        unsigned char *joined = malloc((size_t)4 + length);
        if (joined == NULL) {
            return 1;
        }
        memcpy(joined, type, 4);
        if (length > 0) {
            memcpy(joined + 4, data, length);
        }
        uint32_t computed = crc32_update(0u, joined, (size_t)4 + length);
        free(joined);
        if (computed != stored_crc) {
            return 1;
        }

        if (memcmp(type, CHUNK_ATTESTATION, 4) == 0 && visit != NULL) {
            visit(data, length, context);
        }
        if (memcmp(type, CHUNK_END, 4) == 0) {
            break;
        }
        offset += length + 12;
    }
    return 0;
}

struct sizing {
    size_t total;
    int seen;
};

static void accumulate(const unsigned char *data, size_t length, void *context)
{
    (void)data;
    struct sizing *sizing = context;
    sizing->total += length;
    sizing->seen = 1;
}

struct copying {
    unsigned char *buffer;
    size_t offset;
};

static void copy_into(const unsigned char *data, size_t length, void *context)
{
    struct copying *copying = context;
    if (length > 0) {
        memcpy(copying->buffer + copying->offset, data, length);
    }
    copying->offset += length;
}

int attest_extract(const unsigned char *png, size_t png_len, unsigned char **out, size_t *out_len)
{
    *out = NULL;
    *out_len = 0;

    if (png == NULL || png_len < 8 || memcmp(png, PNG_MAGIC, 8) != 0) {
        return 1;
    }

    struct sizing sizing = {0, 0};
    if (walk_chunks(png, png_len, accumulate, &sizing) != 0) {
        return 1;
    }
    if (!sizing.seen) {
        return 1;
    }

    unsigned char *buffer = malloc(sizing.total == 0 ? 1 : sizing.total);
    if (buffer == NULL) {
        return 1;
    }

    struct copying copying = {buffer, 0};
    if (walk_chunks(png, png_len, copy_into, &copying) != 0) {
        free(buffer);
        return 1;
    }

    *out = buffer;
    *out_len = copying.offset;
    return 0;
}
EOF_ATTEST_C

cat > src/main/java/com/sentinel/json/CanonicalJson.java <<'EOF_CANONICAL'
package com.sentinel.json;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** Serializes a value tree to the canonical byte form used for signing and for the snapshot. */
public final class CanonicalJson {

    private CanonicalJson() {
    }

    /** Serializes {@code value} with object keys sorted by Unicode code point and no whitespace. */
    public static String encode(Object value) {
        StringBuilder builder = new StringBuilder();
        write(builder, value);
        return builder.toString();
    }

    private static void write(StringBuilder builder, Object value) {
        if (value == null) {
            builder.append("null");
        } else if (value instanceof String string) {
            writeString(builder, string);
        } else if (value instanceof Boolean flag) {
            builder.append(flag ? "true" : "false");
        } else if (value instanceof Integer || value instanceof Long) {
            builder.append(value.toString());
        } else if (value instanceof Map<?, ?> map) {
            writeObject(builder, map);
        } else if (value instanceof List<?> list) {
            writeArray(builder, list);
        } else {
            throw new IllegalArgumentException("cannot serialize " + value.getClass());
        }
    }

    private static void writeObject(StringBuilder builder, Map<?, ?> map) {
        TreeMap<String, Object> sorted = new TreeMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            sorted.put(entry.getKey().toString(), entry.getValue());
        }
        builder.append('{');
        boolean first = true;
        for (Map.Entry<String, Object> entry : sorted.entrySet()) {
            if (!first) {
                builder.append(',');
            }
            first = false;
            writeString(builder, entry.getKey());
            builder.append(':');
            write(builder, entry.getValue());
        }
        builder.append('}');
    }

    private static void writeArray(StringBuilder builder, List<?> list) {
        builder.append('[');
        for (int index = 0; index < list.size(); index++) {
            if (index > 0) {
                builder.append(',');
            }
            write(builder, list.get(index));
        }
        builder.append(']');
    }

    private static void writeString(StringBuilder builder, String value) {
        builder.append('"');
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> builder.append("\\\"");
                case '\\' -> builder.append("\\\\");
                case '\b' -> builder.append("\\b");
                case '\f' -> builder.append("\\f");
                case '\n' -> builder.append("\\n");
                case '\r' -> builder.append("\\r");
                case '\t' -> builder.append("\\t");
                default -> {
                    if (character < 0x20) {
                        builder.append(String.format("\\u%04x", (int) character));
                    } else {
                        builder.append(character);
                    }
                }
            }
        }
        builder.append('"');
    }
}
EOF_CANONICAL

cat > src/main/java/com/sentinel/crypto/SignatureVerifier.java <<'EOF_VERIFIER'
package com.sentinel.crypto;

import java.security.PublicKey;
import java.security.Signature;

/** Checks the Ed25519 signature that a build key places over an attestation statement. */
public final class SignatureVerifier {

    private SignatureVerifier() {
    }

    /** Returns whether {@code signature} is a valid Ed25519 signature of {@code preimage}. */
    public static boolean verify(PublicKey publicKey, byte[] preimage, byte[] signature) {
        if (publicKey == null || preimage == null || signature == null || signature.length != 64) {
            return false;
        }
        try {
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(publicKey);
            verifier.update(preimage);
            return verifier.verify(signature);
        } catch (java.security.GeneralSecurityException error) {
            return false;
        }
    }
}
EOF_VERIFIER

cat > src/main/java/com/sentinel/policy/TrustPolicy.java <<'EOF_POLICY'
package com.sentinel.policy;

import java.time.Instant;
import java.util.Set;

/**
 * The release trust policy reconstructed from the incident-room archive.
 *
 * <p>Only {@code k-build-2026a}, {@code k-build-2025b} and {@code k-legacy-2024} may sign a release
 * badge.  {@code k-legacy-2024} was revoked at the moment its exposure was confirmed; statements it
 * signed strictly before that instant remain trusted, and payments-api holds a time-boxed exception.
 * {@code k-build-2025b} was retired at the rotation cutover.
 */
public final class TrustPolicy {

    public static final Set<String> RELEASE_SIGNING_KEYS =
            Set.of("k-build-2026a", "k-build-2025b", "k-legacy-2024");

    private static final Instant LEGACY_REVOCATION = Instant.parse("2026-04-02T17:30:00.000Z");
    private static final Instant LEGACY_EXCEPTION_EXPIRY = Instant.parse("2026-06-30T00:00:00.000Z");
    private static final Instant ROTATION_2025B_CUTOVER = Instant.parse("2026-05-01T00:00:00.000Z");

    private static final String LEGACY_EXCEPTION_SERVICE = "payments-api";
    private static final String LEGACY_EXCEPTION_ID = "EX-14";

    /** The outcome of applying the release trust policy to one statement. */
    public record Decision(boolean revoked, String exceptionId) {

        static Decision accepted() {
            return new Decision(false, null);
        }

        static Decision accepted(String exceptionId) {
            return new Decision(false, exceptionId);
        }

        static Decision denied() {
            return new Decision(true, null);
        }
    }

    private TrustPolicy() {
    }

    /**
     * Applies the trust, revocation, exception and rotation rules to a statement signed by
     * {@code keyId} for {@code service} at {@code issuedAt}.
     */
    public static Decision evaluate(String keyId, String service, Instant issuedAt) {
        if (keyId.equals("k-legacy-2024")) {
            if (issuedAt.isBefore(LEGACY_REVOCATION)) {
                return Decision.accepted();
            }
            if (service.equals(LEGACY_EXCEPTION_SERVICE) && issuedAt.isBefore(LEGACY_EXCEPTION_EXPIRY)) {
                return Decision.accepted(LEGACY_EXCEPTION_ID);
            }
            return Decision.denied();
        }
        if (keyId.equals("k-build-2025b")) {
            if (issuedAt.isBefore(ROTATION_2025B_CUTOVER)) {
                return Decision.accepted();
            }
            return Decision.denied();
        }
        return Decision.accepted();
    }
}
EOF_POLICY

cat > src/main/java/com/sentinel/repo/GitRepository.java <<'EOF_REPO'
package com.sentinel.repo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** The release repository that a badge's tag and branch are reconciled against. */
public final class GitRepository {

    private static final Pattern HEADING =
            Pattern.compile("^##\\s+(\\S+)\\s+\\(([^)]+)\\)\\s*$", Pattern.MULTILINE);

    private final Path root;

    public GitRepository(Path root) {
        this.root = root;
    }

    private List<String> git(String... arguments) throws IOException {
        List<String> command = new ArrayList<>();
        command.add("git");
        command.add("-C");
        command.add(root.toString());
        command.addAll(List.of(arguments));

        Process process = new ProcessBuilder(command).start();
        List<String> lines = new ArrayList<>();
        try (var reader = process.inputReader(StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                String trimmed = line.trim();
                if (!trimmed.isEmpty()) {
                    lines.add(trimmed);
                }
            }
        }
        try {
            if (process.waitFor() != 0) {
                return List.of();
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("git was interrupted", interrupted);
        }
        return lines;
    }

    /** Returns every tag the repository carries. */
    public Set<String> tags() throws IOException {
        return new TreeSet<>(git("tag", "--list"));
    }

    /** Returns the branch each changelog heading names its tag was cut from. */
    public Map<String, String> changelogBranches() throws IOException {
        Path changelog = root.resolve("CHANGELOG.md");
        if (!Files.isRegularFile(changelog)) {
            return Map.of();
        }
        Map<String, String> branches = new HashMap<>();
        Matcher matcher = HEADING.matcher(Files.readString(changelog, StandardCharsets.UTF_8));
        while (matcher.find()) {
            branches.putIfAbsent(matcher.group(1), matcher.group(2));
        }
        return branches;
    }
}
EOF_REPO

cat > src/main/java/com/sentinel/Main.java <<'EOF_MAIN'
package com.sentinel;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sentinel.badge.BadgeResult;
import com.sentinel.badge.BadgeStatus;
import com.sentinel.badge.NativeBadgeReader;
import com.sentinel.crypto.SignatureVerifier;
import com.sentinel.json.CanonicalJson;
import com.sentinel.keys.Keyring;
import com.sentinel.policy.TrustPolicy;
import com.sentinel.repo.GitRepository;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** The ReleaseSentinel worker entry point. */
public final class Main {

    private static final Pattern INSTANT =
            Pattern.compile("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z$");

    private static final Pattern ARTIFACT_DIGEST = Pattern.compile("^sha256:[0-9a-f]{64}$");

    private static final List<String> STATUS_ORDER = List.of(
            "accepted",
            "badge_unreadable",
            "branch_conflict",
            "key_revoked",
            "key_untrusted",
            "signature_invalid",
            "tag_unknown");

    private static final List<String> STATEMENT_FIELDS = List.of(
            "artifact_digest", "issued_at", "key_id", "release_branch", "release_tag", "service");

    private Main() {
    }

    public static void main(String[] args) {
        try {
            System.exit(run(args));
        } catch (Exception error) {
            System.err.println(error.getMessage());
            System.exit(1);
        }
    }

    private static int run(String[] args) throws IOException {
        if (args.length == 0 || !args[0].equals("snapshot")) {
            System.err.println("usage: sentinel snapshot --badges <dir> --repo <dir> --keyring <file> --out <file>");
            return 1;
        }

        Map<String, String> options = parseOptions(args);
        Path badgeDirectory = requirePath(options, "badges");
        Path repositoryRoot = requirePath(options, "repo");
        Path keyringPath = requirePath(options, "keyring");
        Path outputPath = Path.of(require(options, "out"));

        Keyring keyring = Keyring.load(keyringPath);
        GitRepository repository = new GitRepository(repositoryRoot);
        Set<String> tags = repository.tags();
        Map<String, String> changelogBranches = repository.changelogBranches();

        List<BadgeResult> results = new ArrayList<>();
        try (var badges = Files.list(badgeDirectory)) {
            List<Path> files = badges
                    .filter(path -> path.getFileName().toString().endsWith(".png"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .toList();
            for (Path badge : files) {
                results.add(evaluate(badge, keyring, tags, changelogBranches));
            }
        }

        List<Object> badgeElements = new ArrayList<>();
        Map<String, Integer> counts = new HashMap<>();
        for (String status : STATUS_ORDER) {
            counts.put(status, 0);
        }
        for (BadgeResult result : results) {
            badgeElements.add(encode(result));
            counts.merge(result.status().wireName(), 1, Integer::sum);
        }

        String badgeDigest = sha256Hex(CanonicalJson.encode(badgeElements).getBytes(StandardCharsets.UTF_8));

        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("badges", badgeElements);
        snapshot.put("counts", counts);
        snapshot.put("digest", badgeDigest);

        Path parent = outputPath.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(outputPath, CanonicalJson.encode(snapshot) + "\n", StandardCharsets.UTF_8);
        return 0;
    }

    private static BadgeResult evaluate(
            Path badge, Keyring keyring, Set<String> tags, Map<String, String> changelogBranches)
            throws IOException {
        String name = badge.getFileName().toString();
        byte[] payload = NativeBadgeReader.extractPayload(Files.readAllBytes(badge));
        if (payload == null) {
            return BadgeResult.unreadable(name);
        }

        JsonObject attestation = parseAttestation(payload);
        if (attestation == null) {
            return BadgeResult.unreadable(name);
        }
        JsonObject statement = attestation.getAsJsonObject("statement");

        String keyId = statement.get("key_id").getAsString();
        String service = statement.get("service").getAsString();
        String releaseTag = statement.get("release_tag").getAsString();
        String claimedBranch = statement.get("release_branch").getAsString();
        Instant issuedAt = Instant.parse(statement.get("issued_at").getAsString());

        BadgeResult base = new BadgeResult(
                name, service, keyId, releaseTag, claimedBranch, null, BadgeStatus.ACCEPTED);

        if (!keyring.contains(keyId) || !TrustPolicy.RELEASE_SIGNING_KEYS.contains(keyId)) {
            return base.withStatus(BadgeStatus.KEY_UNTRUSTED);
        }

        byte[] signature;
        try {
            signature = Base64.getDecoder().decode(attestation.get("signature").getAsString());
        } catch (IllegalArgumentException malformed) {
            signature = new byte[0];
        }
        byte[] preimage = canonicalStatement(statement).getBytes(StandardCharsets.UTF_8);
        if (!SignatureVerifier.verify(keyring.publicKey(keyId), preimage, signature)) {
            return base.withStatus(BadgeStatus.SIGNATURE_INVALID);
        }

        TrustPolicy.Decision decision = TrustPolicy.evaluate(keyId, service, issuedAt);
        if (decision.revoked()) {
            return base.withStatus(BadgeStatus.KEY_REVOKED);
        }

        if (!tags.contains(releaseTag) || !changelogBranches.containsKey(releaseTag)) {
            return base.withStatus(BadgeStatus.TAG_UNKNOWN);
        }

        String resolvedBranch = changelogBranches.get(releaseTag);
        BadgeResult resolved = base.withBranch(resolvedBranch);
        if (!claimedBranch.equals(resolvedBranch) && !resolvedBranch.startsWith("hotfix/")) {
            return resolved.withStatus(BadgeStatus.BRANCH_CONFLICT);
        }

        return resolved.withException(decision.exceptionId());
    }

    private static JsonObject parseAttestation(byte[] payload) {
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                    .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                    .decode(java.nio.ByteBuffer.wrap(payload))
                    .toString();
        } catch (java.nio.charset.CharacterCodingException invalid) {
            return null;
        }
        JsonObject attestation;
        try {
            JsonElement element = JsonParser.parseString(text);
            if (!element.isJsonObject()) {
                return null;
            }
            attestation = element.getAsJsonObject();
        } catch (RuntimeException malformed) {
            return null;
        }
        if (attestation.size() != 2 || !attestation.has("signature") || !attestation.has("statement")) {
            return null;
        }
        if (!attestation.get("signature").isJsonPrimitive()
                || !attestation.get("signature").getAsJsonPrimitive().isString()) {
            return null;
        }
        if (!attestation.get("statement").isJsonObject()) {
            return null;
        }
        JsonObject statement = attestation.getAsJsonObject("statement");
        if (statement.size() != STATEMENT_FIELDS.size()) {
            return null;
        }
        for (String field : STATEMENT_FIELDS) {
            if (!statement.has(field)
                    || !statement.get(field).isJsonPrimitive()
                    || !statement.get(field).getAsJsonPrimitive().isString()
                    || statement.get(field).getAsString().isEmpty()) {
                return null;
            }
        }
        if (!INSTANT.matcher(statement.get("issued_at").getAsString()).matches()) {
            return null;
        }
        try {
            Instant.parse(statement.get("issued_at").getAsString());
        } catch (DateTimeParseException invalid) {
            return null;
        }
        if (!ARTIFACT_DIGEST.matcher(statement.get("artifact_digest").getAsString()).matches()) {
            return null;
        }
        return attestation;
    }

    private static String canonicalStatement(JsonObject statement) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (String field : STATEMENT_FIELDS) {
            values.put(field, statement.get(field).getAsString());
        }
        return CanonicalJson.encode(values);
    }

    private static Map<String, Object> encode(BadgeResult result) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("badge", result.badge());
        entry.put("exception_id", result.exceptionId());
        entry.put("key_id", result.keyId());
        entry.put("release_branch", result.releaseBranch());
        entry.put("release_tag", result.releaseTag());
        entry.put("service", result.service());
        entry.put("status", result.status().wireName());
        return entry;
    }

    private static String sha256Hex(byte[] data) {
        try {
            byte[] digest = java.security.MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder builder = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                builder.append(Character.forDigit((value >> 4) & 0xF, 16));
                builder.append(Character.forDigit(value & 0xF, 16));
            }
            return builder.toString();
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static Map<String, String> parseOptions(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int index = 1; index < args.length; index++) {
            String argument = args[index];
            if (!argument.startsWith("--") || index + 1 >= args.length) {
                throw new IllegalArgumentException("unrecognised argument: " + argument);
            }
            options.put(argument.substring(2), args[++index]);
        }
        return options;
    }

    private static String require(Map<String, String> options, String name) {
        String value = options.get(name);
        if (value == null) {
            throw new IllegalArgumentException("missing required option: --" + name);
        }
        return value;
    }

    private static Path requirePath(Map<String, String> options, String name) {
        Path path = Path.of(require(options, name));
        if (!Files.exists(path)) {
            throw new IllegalArgumentException("path does not exist: " + path);
        }
        return path;
    }
}
EOF_MAIN

export MVN_FLAGS="-o -B -q"
make -C "${APP_DIR:-/app}" clean
make -C "${APP_DIR:-/app}" all
