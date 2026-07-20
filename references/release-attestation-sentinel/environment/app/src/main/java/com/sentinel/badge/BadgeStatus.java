package com.sentinel.badge;

/** The verdict recorded for a single release badge. */
public enum BadgeStatus {
    BADGE_UNREADABLE("badge_unreadable"),
    KEY_UNTRUSTED("key_untrusted"),
    SIGNATURE_INVALID("signature_invalid"),
    KEY_REVOKED("key_revoked"),
    TAG_UNKNOWN("tag_unknown"),
    BRANCH_CONFLICT("branch_conflict"),
    ACCEPTED("accepted");

    private final String wireName;

    BadgeStatus(String wireName) {
        this.wireName = wireName;
    }

    public String wireName() {
        return wireName;
    }
}
