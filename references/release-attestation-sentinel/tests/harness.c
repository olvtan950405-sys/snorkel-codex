/*
 * Exercises attest_extract under a memory checker.  Reads a badge PNG from argv[1], extracts the
 * attestation payload and writes it verbatim to stdout.  Exits 0 on a readable payload, 2 when the
 * badge carries no valid payload, and 3 on a usage or I/O error.  Any memory error is surfaced by
 * the checker running this harness, not by the harness itself.
 */
#include "attest.h"

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: harness <badge.png>\n");
        return 3;
    }

    FILE *file = fopen(argv[1], "rb");
    if (file == NULL) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 3;
    }

    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return 3;
    }
    long size = ftell(file);
    if (size < 0) {
        fclose(file);
        return 3;
    }
    rewind(file);

    unsigned char *png = malloc((size_t)size == 0 ? 1 : (size_t)size);
    if (png == NULL) {
        fclose(file);
        return 3;
    }
    if (fread(png, 1, (size_t)size, file) != (size_t)size) {
        free(png);
        fclose(file);
        return 3;
    }
    fclose(file);

    unsigned char *payload = NULL;
    size_t payload_len = 0;
    int status = attest_extract(png, (size_t)size, &payload, &payload_len);
    free(png);

    if (status != 0) {
        free(payload);
        return 2;
    }

    if (payload_len > 0) {
        fwrite(payload, 1, payload_len, stdout);
    }
    free(payload);
    return 0;
}
