package com.sentinel.repo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** The release repository that a badge's tag and branch are reconciled against. */
public final class GitRepository {

    private final Path root;

    public GitRepository(Path root) {
        this.root = root;
    }

    /** Runs a git command in the repository and returns its trimmed standard output lines. */
    public List<String> git(String... arguments) throws IOException {
        List<String> command = new ArrayList<>();
        command.add("git");
        command.add("-C");
        command.add(root.toString());
        command.addAll(List.of(arguments));

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(false);
        Process process = builder.start();

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

    /** Returns whether the repository carries a tag with the given name. */
    public boolean hasTag(String tag) throws IOException {
        return !git("tag", "--list", tag).isEmpty();
    }

    /** Returns the changelog text of the repository. */
    public String changelog() throws IOException {
        Path changelog = root.resolve("CHANGELOG.md");
        if (!Files.isRegularFile(changelog)) {
            return "";
        }
        return Files.readString(changelog, StandardCharsets.UTF_8);
    }
}
