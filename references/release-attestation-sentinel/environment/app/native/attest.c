#include "attest.h"

#include <stdlib.h>
#include <string.h>

static const unsigned char PNG_MAGIC[8] = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};

static const unsigned char CHUNK_ATTESTATION[4] = {'a', 't', 'S', 't'};
static const unsigned char CHUNK_END[4] = {'I', 'E', 'N', 'D'};

static size_t read_be32(const unsigned char *bytes)
{
    return ((size_t)bytes[0] << 24) | ((size_t)bytes[1] << 16) | ((size_t)bytes[2] << 8) |
           (size_t)bytes[3];
}

int attest_extract(const unsigned char *png, size_t png_len, unsigned char **out, size_t *out_len)
{
    unsigned char *payload = NULL;
    size_t collected = 0;
    size_t offset = 8;

    *out = NULL;
    *out_len = 0;

    if (png == NULL || png_len < 8 || memcmp(png, PNG_MAGIC, 8) != 0) {
        return 1;
    }

    while (offset + 8 <= png_len) {
        size_t length = read_be32(png + offset);
        const unsigned char *type = png + offset + 4;
        const unsigned char *data = png + offset + 8;

        if (memcmp(type, CHUNK_ATTESTATION, 4) == 0) {
            if (payload == NULL) {
                payload = malloc(length);
                if (payload == NULL) {
                    return 1;
                }
            }
            memcpy(payload + collected, data, length);
            collected += length;
        }

        if (memcmp(type, CHUNK_END, 4) == 0) {
            break;
        }

        offset += length + 12;
    }

    if (payload == NULL) {
        return 1;
    }

    *out = payload;
    *out_len = strlen((const char *)payload);
    return 0;
}
