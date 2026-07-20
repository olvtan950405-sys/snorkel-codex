package com.sentinel.badge;

/** The evaluated outcome for one badge file. */
public record BadgeResult(
        String badge,
        String service,
        String keyId,
        String releaseTag,
        String releaseBranch,
        String exceptionId,
        BadgeStatus status) {

    public static BadgeResult unreadable(String badge) {
        return new BadgeResult(badge, null, null, null, null, null, BadgeStatus.BADGE_UNREADABLE);
    }

    public BadgeResult withStatus(BadgeStatus newStatus) {
        return new BadgeResult(badge, service, keyId, releaseTag, releaseBranch, exceptionId, newStatus);
    }

    public BadgeResult withBranch(String branch) {
        return new BadgeResult(badge, service, keyId, releaseTag, branch, exceptionId, status);
    }

    public BadgeResult withException(String id) {
        return new BadgeResult(badge, service, keyId, releaseTag, releaseBranch, id, status);
    }
}
