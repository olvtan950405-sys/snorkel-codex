package com.sentinel.json;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Serializes JSON values to the byte form used for signing and for the snapshot file. */
public final class CanonicalJson {

    private CanonicalJson() {
    }

    /** Serializes {@code element} with its object keys ordered. */
    public static String encode(JsonElement element) {
        if (!element.isJsonObject()) {
            return element.toString();
        }

        JsonObject object = element.getAsJsonObject();
        List<String> names = new ArrayList<>(object.keySet());
        Collections.sort(names);

        StringBuilder builder = new StringBuilder("{");
        for (int index = 0; index < names.size(); index++) {
            if (index > 0) {
                builder.append(',');
            }
            String name = names.get(index);
            builder.append('"').append(name).append('"').append(':');
            builder.append(object.get(name).toString());
        }
        return builder.append('}').toString();
    }
}
