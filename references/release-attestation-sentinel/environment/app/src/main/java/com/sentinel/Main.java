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
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** The ReleaseSentinel worker entry point. */
public final class Main {

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

        List<BadgeResult> results = new ArrayList<>();
        try (var badges = Files.list(badgeDirectory)) {
            List<Path> files = badges
                    .filter(path -> path.getFileName().toString().endsWith(".png"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .toList();
            for (Path badge : files) {
                results.add(evaluate(badge, keyring, repository));
            }
        }

        JsonObject snapshot = new JsonObject();
        snapshot.add("badges", encodeBadges(results));

        Files.createDirectories(outputPath.toAbsolutePath().getParent());
        Files.writeString(outputPath, CanonicalJson.encode(snapshot), StandardCharsets.UTF_8);
        return 0;
    }

    private static BadgeResult evaluate(Path badge, Keyring keyring, GitRepository repository)
            throws IOException {
        String name = badge.getFileName().toString();
        byte[] payload = NativeBadgeReader.extractPayload(Files.readAllBytes(badge));
        if (payload == null) {
            return BadgeResult.unreadable(name);
        }

        JsonObject attestation;
        try {
            attestation = JsonParser.parseString(new String(payload, StandardCharsets.UTF_8)).getAsJsonObject();
        } catch (RuntimeException malformed) {
            return BadgeResult.unreadable(name);
        }

        JsonObject statement = attestation.getAsJsonObject("statement");
        String keyId = statement.get("key_id").getAsString();
        String service = statement.get("service").getAsString();
        String releaseTag = statement.get("release_tag").getAsString();
        String releaseBranch = statement.get("release_branch").getAsString();
        String issuedAt = statement.get("issued_at").getAsString();

        BadgeResult result = new BadgeResult(
                name, service, keyId, releaseTag, releaseBranch, null, BadgeStatus.ACCEPTED);

        if (!keyring.contains(keyId)) {
            return result.withStatus(BadgeStatus.KEY_UNTRUSTED);
        }

        byte[] signature = Base64.getDecoder().decode(attestation.get("signature").getAsString());
        byte[] preimage = CanonicalJson.encode(statement).getBytes(StandardCharsets.UTF_8);
        if (!SignatureVerifier.verify(keyring.publicKey(keyId), preimage, signature)) {
            return result.withStatus(BadgeStatus.SIGNATURE_INVALID);
        }

        TrustPolicy.Decision decision = TrustPolicy.evaluate(keyId, service, issuedAt);
        if (decision.revoked()) {
            return result.withStatus(BadgeStatus.KEY_REVOKED);
        }

        if (!repository.hasTag(releaseTag)) {
            return result.withStatus(BadgeStatus.TAG_UNKNOWN);
        }

        return result.withException(decision.exceptionId());
    }

    private static JsonElement encodeBadges(List<BadgeResult> results) {
        var array = new com.google.gson.JsonArray();
        for (BadgeResult result : results) {
            JsonObject entry = new JsonObject();
            entry.addProperty("badge", result.badge());
            entry.addProperty("service", result.service());
            entry.addProperty("key_id", result.keyId());
            entry.addProperty("release_tag", result.releaseTag());
            entry.addProperty("release_branch", result.releaseBranch());
            entry.addProperty("exception_id", result.exceptionId());
            entry.addProperty("status", result.status().wireName());
            array.add(entry);
        }
        return array;
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
