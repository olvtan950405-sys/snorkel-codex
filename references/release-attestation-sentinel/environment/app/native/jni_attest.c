#include <jni.h>
#include <stdlib.h>

#include "attest.h"

JNIEXPORT jbyteArray JNICALL
Java_com_sentinel_badge_NativeBadgeReader_extract(JNIEnv *env, jclass cls, jbyteArray png)
{
    jsize png_len;
    jbyte *png_bytes;
    unsigned char *payload = NULL;
    size_t payload_len = 0;
    jbyteArray result = NULL;

    (void)cls;

    if (png == NULL) {
        return NULL;
    }

    png_len = (*env)->GetArrayLength(env, png);
    png_bytes = (*env)->GetByteArrayElements(env, png, NULL);
    if (png_bytes == NULL) {
        return NULL;
    }

    if (attest_extract((const unsigned char *)png_bytes, (size_t)png_len, &payload, &payload_len) != 0) {
        (*env)->ReleaseByteArrayElements(env, png, png_bytes, JNI_ABORT);
        return NULL;
    }

    (*env)->ReleaseByteArrayElements(env, png, png_bytes, JNI_ABORT);

    result = (*env)->NewByteArray(env, (jsize)payload_len);
    if (result != NULL) {
        (*env)->SetByteArrayRegion(env, result, 0, (jsize)payload_len, (const jbyte *)payload);
    }
    free(payload);
    return result;
}
