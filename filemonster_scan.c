// filemonster_scan.c
// FileMonster Core v0.3
//
// Purpose:
//   Create a portable master JSON ledger + per-file sidecars.
//   Future modules append separate JSON blocks and register them in module_index.jsonl.
//
// Build:
//   gcc -O3 -march=native -Wall -Wextra -o filemonster_scan filemonster_scan.c -lcrypto
//
// Run:
//   ./filemonster_scan /path/to/dataset -o /path/to/filemonster_master.json --sidecars --write-xattr
//
// Output:
//   filemonster_master.json
//   filemonster_module_index.jsonl
//   image.png.fm.json
//
// Install dependency if needed:
//   sudo pacman -S openssl

#define _XOPEN_SOURCE 700
#define _DEFAULT_SOURCE

#include <errno.h>
#include <ftw.h>
#include <limits.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#ifdef __linux__
#include <sys/xattr.h>
#endif

#define BUF_SIZE 262144
#define HASH_HEX_LEN 65
#define ID_LEN 48
#define PATH_BUF 8192
#define PARTIAL_CHUNK 65536

static char g_root[PATH_BUF] = {0};
static char g_master_path[PATH_BUF] = {0};
static char g_module_index_path[PATH_BUF] = {0};

static FILE *g_master_tmp = NULL;
static int g_first_record = 1;
static int g_sidecars = 0;
static int g_write_xattr = 0;
static int g_include_hidden = 0;

static uint64_t g_seen = 0;
static uint64_t g_written = 0;
static uint64_t g_skipped = 0;

static void json_escape(FILE *out, const char *s) {
    fputc('"', out);
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        switch (c) {
            case '"': fputs("\\\"", out); break;
            case '\\': fputs("\\\\", out); break;
            case '\b': fputs("\\b", out); break;
            case '\f': fputs("\\f", out); break;
            case '\n': fputs("\\n", out); break;
            case '\r': fputs("\\r", out); break;
            case '\t': fputs("\\t", out); break;
            default:
                if (c < 0x20) fprintf(out, "\\u%04x", c);
                else fputc(c, out);
        }
    }
    fputc('"', out);
}

static void utc_now(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm tm_utc;
    gmtime_r(&now, &tm_utc);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm_utc);
}

static void utc_from_time(time_t t, char *buf, size_t len) {
    struct tm tm_utc;
    gmtime_r(&t, &tm_utc);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm_utc);
}

static int is_supported_file(const char *path) {
    const char *dot = strrchr(path, '.');
    if (!dot) return 0;

    return !strcasecmp(dot, ".png")  ||
           !strcasecmp(dot, ".jpg")  ||
           !strcasecmp(dot, ".jpeg") ||
           !strcasecmp(dot, ".webp") ||
           !strcasecmp(dot, ".bmp")  ||
           !strcasecmp(dot, ".tif")  ||
           !strcasecmp(dot, ".tiff") ||
           !strcasecmp(dot, ".pdf");
}

static const char *media_type(const char *path) {
    const char *dot = strrchr(path, '.');
    if (!dot) return "unknown";

    if (!strcasecmp(dot, ".pdf")) return "document";
    return "image";
}

static const char *format_from_ext(const char *path) {
    const char *dot = strrchr(path, '.');
    if (!dot) return "unknown";

    if (!strcasecmp(dot, ".jpg") || !strcasecmp(dot, ".jpeg")) return "jpeg";
    if (!strcasecmp(dot, ".png")) return "png";
    if (!strcasecmp(dot, ".webp")) return "webp";
    if (!strcasecmp(dot, ".bmp")) return "bmp";
    if (!strcasecmp(dot, ".tif") || !strcasecmp(dot, ".tiff")) return "tiff";
    if (!strcasecmp(dot, ".pdf")) return "pdf";
    return "unknown";
}

static int is_hidden_path(const char *path) {
    const char *p = path;

    if (path[0] == '.') return 1;

    while ((p = strchr(p, '/')) != NULL) {
        p++;
        if (*p == '.' && p[1] != '\0') return 1;
    }

    return 0;
}

static int skip_generated(const char *path) {
    const char *base = strrchr(path, '/');
    base = base ? base + 1 : path;

    if (strstr(base, ".fm.json")) return 1;
    if (strstr(base, ".fm.modules")) return 1;
    if (!strncmp(base, "filemonster_", 12)) return 1;
    if (!strncmp(base, "paddle_ocr", 10)) return 1;

    return 0;
}

static const char *relative_path(const char *path) {
    size_t n = strlen(g_root);

    if (n > 0 && !strncmp(path, g_root, n)) {
        const char *r = path + n;
        if (*r == '/') r++;
        return *r ? r : ".";
    }

    return path;
}

static void make_sidecar_path(const char *path, char *out, size_t out_len) {
    snprintf(out, out_len, "%s.fm.json", path);
}

static void make_modules_dir_rel(const char *rel_path, char *out, size_t out_len) {
    snprintf(out, out_len, "%s.fm.modules", rel_path);
}

static void make_id(const char *prefix, const char *hash_hex, char *out, size_t out_len) {
    snprintf(out, out_len, "%s:%.24s", prefix, hash_hex);
}

static int sha256_file(const char *path, char out_hex[HASH_HEX_LEN]) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;

    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx) {
        fclose(f);
        return -1;
    }

    EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);

    unsigned char *buf = malloc(BUF_SIZE);
    if (!buf) {
        EVP_MD_CTX_free(ctx);
        fclose(f);
        return -1;
    }

    size_t n;
    while ((n = fread(buf, 1, BUF_SIZE, f)) > 0) {
        EVP_DigestUpdate(ctx, buf, n);
    }

    int bad = ferror(f);

    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;

    EVP_DigestFinal_ex(ctx, hash, &hash_len);

    free(buf);
    EVP_MD_CTX_free(ctx);
    fclose(f);

    if (bad) return -1;

    for (unsigned int i = 0; i < hash_len; i++) {
        sprintf(out_hex + (i * 2), "%02x", hash[i]);
    }

    out_hex[64] = '\0';
    return 0;
}

static int sha256_partial(const char *path, off_t offset, size_t max_len, char out_hex[HASH_HEX_LEN]) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;

    if (fseeko(f, offset, SEEK_SET) != 0) {
        fclose(f);
        return -1;
    }

    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx) {
        fclose(f);
        return -1;
    }

    EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);

    unsigned char buf[BUF_SIZE];
    size_t remaining = max_len;

    while (remaining > 0) {
        size_t want = remaining < BUF_SIZE ? remaining : BUF_SIZE;
        size_t n = fread(buf, 1, want, f);
        if (n == 0) break;
        EVP_DigestUpdate(ctx, buf, n);
        remaining -= n;
    }

    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;

    EVP_DigestFinal_ex(ctx, hash, &hash_len);

    EVP_MD_CTX_free(ctx);
    fclose(f);

    for (unsigned int i = 0; i < hash_len; i++) {
        sprintf(out_hex + (i * 2), "%02x", hash[i]);
    }

    out_hex[64] = '\0';
    return 0;
}

static void sha256_string3(const char *a, const char *b, const char *c, char out_hex[HASH_HEX_LEN]) {
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);
    EVP_DigestUpdate(ctx, a, strlen(a));
    EVP_DigestUpdate(ctx, b, strlen(b));
    EVP_DigestUpdate(ctx, c, strlen(c));

    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;

    EVP_DigestFinal_ex(ctx, hash, &hash_len);
    EVP_MD_CTX_free(ctx);

    for (unsigned int i = 0; i < hash_len; i++) {
        sprintf(out_hex + (i * 2), "%02x", hash[i]);
    }

    out_hex[64] = '\0';
}

static int read_png_dims(FILE *f, int *w, int *h) {
    unsigned char sig[24];

    if (fseek(f, 0, SEEK_SET) != 0) return -1;
    if (fread(sig, 1, 24, f) != 24) return -1;

    unsigned char pngsig[8] = {137,80,78,71,13,10,26,10};
    if (memcmp(sig, pngsig, 8) != 0) return -1;
    if (memcmp(sig + 12, "IHDR", 4) != 0) return -1;

    *w = (sig[16] << 24) | (sig[17] << 16) | (sig[18] << 8) | sig[19];
    *h = (sig[20] << 24) | (sig[21] << 16) | (sig[22] << 8) | sig[23];

    return 0;
}

static int read_jpeg_dims(FILE *f, int *w, int *h) {
    if (fseek(f, 0, SEEK_SET) != 0) return -1;

    int c1 = fgetc(f);
    int c2 = fgetc(f);

    if (c1 != 0xFF || c2 != 0xD8) return -1;

    while (!feof(f)) {
        int marker_prefix;

        do {
            marker_prefix = fgetc(f);
        } while (marker_prefix != 0xFF && !feof(f));

        int marker;

        do {
            marker = fgetc(f);
        } while (marker == 0xFF && !feof(f));

        if (marker == EOF) break;
        if (marker == 0xD9 || marker == 0xDA) break;

        unsigned char lenbuf[2];
        if (fread(lenbuf, 1, 2, f) != 2) return -1;

        int seglen = (lenbuf[0] << 8) | lenbuf[1];
        if (seglen < 2) return -1;

        int is_sof =
            (marker >= 0xC0 && marker <= 0xC3) ||
            (marker >= 0xC5 && marker <= 0xC7) ||
            (marker >= 0xC9 && marker <= 0xCB) ||
            (marker >= 0xCD && marker <= 0xCF);

        if (is_sof) {
            unsigned char data[5];
            if (fread(data, 1, 5, f) != 5) return -1;

            *h = (data[1] << 8) | data[2];
            *w = (data[3] << 8) | data[4];

            return 0;
        }

        if (fseek(f, seglen - 2, SEEK_CUR) != 0) return -1;
    }

    return -1;
}

static void read_image_dims(const char *path, int *w, int *h) {
    *w = 0;
    *h = 0;

    const char *fmt = format_from_ext(path);
    FILE *f = fopen(path, "rb");
    if (!f) return;

    if (!strcmp(fmt, "png")) read_png_dims(f, w, h);
    else if (!strcmp(fmt, "jpeg")) read_jpeg_dims(f, w, h);

    fclose(f);
}

static void write_xattrs(const char *path, const char *fm_id, const char *ff_id, const char *sha256_hex) {
    if (!g_write_xattr) return;

#ifdef __linux__
    char marker[256];
    snprintf(marker, sizeof(marker), "%s|%s|S:0.3", fm_id, ff_id);

    setxattr(path, "user.fm.marker", marker, strlen(marker), 0);
    setxattr(path, "user.fm.sentinel", fm_id, strlen(fm_id), 0);
    setxattr(path, "user.fm.forensic", ff_id, strlen(ff_id), 0);
    setxattr(path, "user.fm.sha256", sha256_hex, strlen(sha256_hex), 0);
#else
    (void)path;
    (void)fm_id;
    (void)ff_id;
    (void)sha256_hex;
#endif
}

static void write_sidecar(
    const char *path,
    const char *rel,
    const struct stat *st,
    const char *fm_id,
    const char *ff_id,
    const char *sha256_hex,
    const char *head_hex,
    const char *mid_hex,
    const char *tail_hex,
    int width,
    int height
) {
    if (!g_sidecars) return;

    char sidecar_path[PATH_BUF];
    char sidecar_rel[PATH_BUF];
    char modules_dir_rel[PATH_BUF];
    char now[32], modified[32];

    make_sidecar_path(path, sidecar_path, sizeof(sidecar_path));
    make_sidecar_path(rel, sidecar_rel, sizeof(sidecar_rel));
    make_modules_dir_rel(rel, modules_dir_rel, sizeof(modules_dir_rel));

    utc_now(now, sizeof(now));
    utc_from_time(st->st_mtime, modified, sizeof(modified));

    FILE *f = fopen(sidecar_path, "w");
    if (!f) {
        fprintf(stderr, "WARN: cannot write sidecar: %s\n", sidecar_path);
        return;
    }

    fprintf(f, "{\n");
    fprintf(f, "  \"schema\": {\"name\": \"FMIAF\", \"version\": \"0.3.0\"},\n");
    fprintf(f, "  \"record_type\": \"file_sidecar\",\n");

    fprintf(f, "  \"identity\": {\n");
    fprintf(f, "    \"fm_id\": "); json_escape(f, fm_id); fprintf(f, ",\n");
    fprintf(f, "    \"ff_id\": "); json_escape(f, ff_id); fprintf(f, ",\n");
    fprintf(f, "    \"marker\": "); 
    char marker[256];
    snprintf(marker, sizeof(marker), "%s|%s|S:0.3", fm_id, ff_id);
    json_escape(f, marker);
    fprintf(f, "\n  },\n");

    fprintf(f, "  \"media\": {\n");
    fprintf(f, "    \"path\": "); json_escape(f, rel); fprintf(f, ",\n");
    fprintf(f, "    \"absolute_path_at_scan\": "); json_escape(f, path); fprintf(f, ",\n");
    fprintf(f, "    \"media_type\": "); json_escape(f, media_type(path)); fprintf(f, ",\n");
    fprintf(f, "    \"format\": "); json_escape(f, format_from_ext(path)); fprintf(f, ",\n");
    fprintf(f, "    \"size_bytes\": %lld,\n", (long long)st->st_size);
    fprintf(f, "    \"width\": %d,\n", width);
    fprintf(f, "    \"height\": %d,\n", height);
    fprintf(f, "    \"sha256\": "); json_escape(f, sha256_hex); fprintf(f, ",\n");
    fprintf(f, "    \"modified_utc\": "); json_escape(f, modified); fprintf(f, "\n");
    fprintf(f, "  },\n");

    fprintf(f, "  \"forensic\": {\n");
    fprintf(f, "    \"partial_hash_head_64k\": "); json_escape(f, head_hex); fprintf(f, ",\n");
    fprintf(f, "    \"partial_hash_middle_64k\": "); json_escape(f, mid_hex); fprintf(f, ",\n");
    fprintf(f, "    \"partial_hash_tail_64k\": "); json_escape(f, tail_hex); fprintf(f, "\n");
    fprintf(f, "  },\n");

    fprintf(f, "  \"annotations\": {\n");
    fprintf(f, "    \"whole_image\": {\"labels\": [], \"text_pairs\": [], \"caption\": null, \"notes\": null},\n");
    fprintf(f, "    \"regions\": []\n");
    fprintf(f, "  },\n");

    fprintf(f, "  \"relationships\": [],\n");

    fprintf(f, "  \"module_registry\": {\n");
    fprintf(f, "    \"module_output_directory\": "); json_escape(f, modules_dir_rel); fprintf(f, ",\n");
    fprintf(f, "    \"module_outputs\": []\n");
    fprintf(f, "  },\n");

    fprintf(f, "  \"research\": {\"review_required\": false, \"export_allowed\": true, \"notes\": null},\n");
    fprintf(f, "  \"provenance\": {\"tool_name\": \"filemonster_scan\", \"tool_version\": \"0.3.0\", \"created_utc\": ");
    json_escape(f, now);
    fprintf(f, "},\n");
    fprintf(f, "  \"extensions\": {}\n");
    fprintf(f, "}\n");

    fclose(f);
}

static void write_master_record(
    const char *path,
    const char *rel,
    const struct stat *st,
    const char *fm_id,
    const char *ff_id,
    const char *sha256_hex,
    int width,
    int height
) {
    char sidecar_rel[PATH_BUF];
    char modules_dir_rel[PATH_BUF];

    make_sidecar_path(rel, sidecar_rel, sizeof(sidecar_rel));
    make_modules_dir_rel(rel, modules_dir_rel, sizeof(modules_dir_rel));

    if (!g_first_record) fprintf(g_master_tmp, ",\n");
    g_first_record = 0;

    fprintf(g_master_tmp, "    {\n");
    fprintf(g_master_tmp, "      \"fm_id\": "); json_escape(g_master_tmp, fm_id); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"ff_id\": "); json_escape(g_master_tmp, ff_id); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"path\": "); json_escape(g_master_tmp, rel); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"sidecar\": "); json_escape(g_master_tmp, sidecar_rel); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"module_output_directory\": "); json_escape(g_master_tmp, modules_dir_rel); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"module_outputs\": [],\n");
    fprintf(g_master_tmp, "      \"media_type\": "); json_escape(g_master_tmp, media_type(path)); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"format\": "); json_escape(g_master_tmp, format_from_ext(path)); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "      \"size_bytes\": %lld,\n", (long long)st->st_size);
    fprintf(g_master_tmp, "      \"width\": %d,\n", width);
    fprintf(g_master_tmp, "      \"height\": %d,\n", height);
    fprintf(g_master_tmp, "      \"sha256\": "); json_escape(g_master_tmp, sha256_hex); fprintf(g_master_tmp, "\n");
    fprintf(g_master_tmp, "    }");
}

static void process_file(const char *path, const struct stat *st) {
    char sha256_hex[HASH_HEX_LEN];
    char head_hex[HASH_HEX_LEN];
    char mid_hex[HASH_HEX_LEN];
    char tail_hex[HASH_HEX_LEN];
    char forensic_seed[HASH_HEX_LEN];
    char fm_id[ID_LEN];
    char ff_id[ID_LEN];

    if (sha256_file(path, sha256_hex) != 0) {
        fprintf(stderr, "WARN: cannot hash %s\n", path);
        return;
    }

    off_t size = st->st_size;
    off_t mid = size > PARTIAL_CHUNK ? size / 2 : 0;
    off_t tail = size > PARTIAL_CHUNK ? size - PARTIAL_CHUNK : 0;

    sha256_partial(path, 0, PARTIAL_CHUNK, head_hex);
    sha256_partial(path, mid, PARTIAL_CHUNK, mid_hex);
    sha256_partial(path, tail, PARTIAL_CHUNK, tail_hex);

    sha256_string3(head_hex, mid_hex, tail_hex, forensic_seed);

    make_id("FM1", sha256_hex, fm_id, sizeof(fm_id));
    make_id("FF1", forensic_seed, ff_id, sizeof(ff_id));

    int width = 0;
    int height = 0;

    if (!strcmp(media_type(path), "image")) {
        read_image_dims(path, &width, &height);
    }

    const char *rel = relative_path(path);

    write_xattrs(path, fm_id, ff_id, sha256_hex);
    write_sidecar(path, rel, st, fm_id, ff_id, sha256_hex, head_hex, mid_hex, tail_hex, width, height);
    write_master_record(path, rel, st, fm_id, ff_id, sha256_hex, width, height);

    g_written++;
}

static int scan_cb(const char *fpath, const struct stat *sb, int typeflag, struct FTW *ftwbuf) {
    (void)ftwbuf;

    if (typeflag != FTW_F) return 0;

    if (!g_include_hidden && is_hidden_path(fpath)) {
        g_skipped++;
        return 0;
    }

    if (skip_generated(fpath)) {
        g_skipped++;
        return 0;
    }

    if (!is_supported_file(fpath)) {
        g_skipped++;
        return 0;
    }

    g_seen++;
    process_file(fpath, sb);

    if (g_seen % 250 == 0) {
        fprintf(stderr, "Scanned %llu files...\n", (unsigned long long)g_seen);
    }

    return 0;
}

static void master_begin(void) {
    char now[32];
    utc_now(now, sizeof(now));

    fprintf(g_master_tmp, "{\n");
    fprintf(g_master_tmp, "  \"schema\": {\"name\": \"FMIAF\", \"version\": \"0.3.0\"},\n");
    fprintf(g_master_tmp, "  \"record_type\": \"master_ledger\",\n");
    fprintf(g_master_tmp, "  \"created_utc\": "); json_escape(g_master_tmp, now); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "  \"root_path_at_scan\": "); json_escape(g_master_tmp, g_root); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "  \"module_index\": "); json_escape(g_master_tmp, "filemonster_module_index.jsonl"); fprintf(g_master_tmp, ",\n");
    fprintf(g_master_tmp, "  \"design\": {\n");
    fprintf(g_master_tmp, "    \"master_role\": \"portable ledger pointing to sidecars and module JSON blocks\",\n");
    fprintf(g_master_tmp, "    \"sidecar_role\": \"per-file passport and annotation socket\",\n");
    fprintf(g_master_tmp, "    \"module_role\": \"separate appendable JSON outputs registered by relative path\"\n");
    fprintf(g_master_tmp, "  },\n");
    fprintf(g_master_tmp, "  \"files\": [\n");
}

static void master_end(void) {
    fprintf(g_master_tmp, "\n  ],\n");
    fprintf(g_master_tmp, "  \"summary\": {\n");
    fprintf(g_master_tmp, "    \"files_seen\": %llu,\n", (unsigned long long)g_seen);
    fprintf(g_master_tmp, "    \"files_written\": %llu,\n", (unsigned long long)g_written);
    fprintf(g_master_tmp, "    \"files_skipped\": %llu\n", (unsigned long long)g_skipped);
    fprintf(g_master_tmp, "  }\n");
    fprintf(g_master_tmp, "}\n");
}

static void create_empty_module_index(void) {
    FILE *f = fopen(g_module_index_path, "w");
    if (!f) {
        fprintf(stderr, "WARN: cannot create module index: %s\n", g_module_index_path);
        return;
    }

    
    fclose(f);
}

static void set_root(const char *input, const struct stat *st) {
    char resolved[PATH_BUF];

    if (!realpath(input, resolved)) {
        strncpy(g_root, input, sizeof(g_root) - 1);
        return;
    }

    if (S_ISDIR(st->st_mode)) {
        strncpy(g_root, resolved, sizeof(g_root) - 1);
    } else {
        strncpy(g_root, resolved, sizeof(g_root) - 1);
        char *slash = strrchr(g_root, '/');
        if (slash) *slash = '\0';
    }
}

static void set_module_index_path(const char *master_path) {
    strncpy(g_master_path, master_path, sizeof(g_master_path) - 1);
    strncpy(g_module_index_path, master_path, sizeof(g_module_index_path) - 1);

    char *slash = strrchr(g_module_index_path, '/');
    if (slash) {
        slash++;
        *slash = '\0';
        strncat(g_module_index_path, "filemonster_module_index.jsonl", sizeof(g_module_index_path) - strlen(g_module_index_path) - 1);
    } else {
        strncpy(g_module_index_path, "filemonster_module_index.jsonl", sizeof(g_module_index_path) - 1);
    }
}

static void usage(const char *argv0) {
    fprintf(stderr,
        "FileMonster Core v0.3\n"
        "Usage:\n"
        "  %s INPUT -o filemonster_master.json [--sidecars] [--write-xattr] [--include-hidden]\n\n"
        "Examples:\n"
        "  %s /home/papa/paddle_script_test_directory -o /home/papa/filemonster_master.json --sidecars --write-xattr\n"
        "  %s one.png -o /home/papa/one_master.json --sidecars\n\n"
        "Default skips: hidden files, *.fm.json, *.fm.modules, filemonster_*, paddle_ocr*\n",
        argv0, argv0, argv0);
}

int main(int argc, char **argv) {
    const char *input = NULL;
    const char *output = NULL;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-o") || !strcmp(argv[i], "--output")) {
            if (i + 1 >= argc) {
                usage(argv[0]);
                return 2;
            }
            output = argv[++i];
        } else if (!strcmp(argv[i], "--sidecars")) {
            g_sidecars = 1;
        } else if (!strcmp(argv[i], "--write-xattr")) {
            g_write_xattr = 1;
        } else if (!strcmp(argv[i], "--include-hidden")) {
            g_include_hidden = 1;
        } else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            usage(argv[0]);
            return 0;
        } else if (!input) {
            input = argv[i];
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (!input || !output) {
        usage(argv[0]);
        return 2;
    }

    struct stat st;
    if (stat(input, &st) != 0) {
        fprintf(stderr, "ERROR: cannot stat input %s: %s\n", input, strerror(errno));
        return 1;
    }

    set_root(input, &st);
    set_module_index_path(output);

    g_master_tmp = fopen(output, "w");
    if (!g_master_tmp) {
        fprintf(stderr, "ERROR: cannot open output %s: %s\n", output, strerror(errno));
        return 1;
    }

    create_empty_module_index();
    master_begin();

    if (S_ISREG(st.st_mode)) {
        if (!is_supported_file(input)) {
            fprintf(stderr, "ERROR: unsupported file: %s\n", input);
            fclose(g_master_tmp);
            return 1;
        }

        g_seen++;
        process_file(input, &st);

    } else if (S_ISDIR(st.st_mode)) {
        if (nftw(input, scan_cb, 64, FTW_PHYS) != 0) {
            fprintf(stderr, "ERROR: scan failed: %s\n", strerror(errno));
            fclose(g_master_tmp);
            return 1;
        }

    } else {
        fprintf(stderr, "ERROR: input is not file or directory: %s\n", input);
        fclose(g_master_tmp);
        return 1;
    }

    master_end();
    fclose(g_master_tmp);

    fprintf(stderr, "Done.\n");
    fprintf(stderr, "Files seen:    %llu\n", (unsigned long long)g_seen);
    fprintf(stderr, "Files written: %llu\n", (unsigned long long)g_written);
    fprintf(stderr, "Files skipped: %llu\n", (unsigned long long)g_skipped);
    fprintf(stderr, "Master JSON:   %s\n", output);
    fprintf(stderr, "Module index:  %s\n", g_module_index_path);

    if (g_sidecars) fprintf(stderr, "Sidecars:      enabled\n");
    if (g_write_xattr) fprintf(stderr, "xattrs:        enabled\n");

    return 0;
}
