#ifndef ATTEST_H
#define ATTEST_H

#include <stddef.h>

/*
 * Extract the attestation payload carried by the private ancillary "atSt" chunks of a PNG.
 *
 * The payload is the concatenation, in file order, of the data fields of every "atSt" chunk.
 *
 * On success returns 0, stores a heap buffer owned by the caller in *out and its length in
 * *out_len.  The caller releases the buffer with free().
 *
 * On failure returns a non-zero value, stores NULL in *out and 0 in *out_len.
 */
int attest_extract(const unsigned char *png, size_t png_len, unsigned char **out, size_t *out_len);

#endif /* ATTEST_H */
