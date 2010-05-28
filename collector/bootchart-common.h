/*
 * bootchart-common.h - shared data structures
 */
#ifndef BOOTCHART_COMMON_H
#define BOOTCHART_COMMON_H

/* get the right versions of various key functions */
#define _XOPEN_SOURCE 600
#define _FILE_OFFSET_BITS 64
#define _LARGEFILE64_SOURCE
#define _BSD_SOURCE

#include <sys/mount.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/select.h>
#include <sys/resource.h>
#include <sys/socket.h>

#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <assert.h>
#include <dirent.h>
#include <limits.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ctype.h>

extern unsigned long hz;

/* Magic path we mount our tmpfs on, inside which we do everything */
#define TMPFS_PATH "/lib/bootchart/tmpfs"
#define PROC_PATH  "/lib/bootchart/tmpfs/proc"
/* where we lurk to get move mounted into the live system */
#define MOVE_DEV_PATH "/dev/.bootchart"

/* helpers */
#undef	MAX
#undef	MIN
#define MAX(a, b)  (((a) > (b)) ? (a) : (b))
#define MIN(a, b)  (((a) < (b)) ? (a) : (b))

/* ptrace transferable buffers */

/* Max ~ 128Mb of space for logging, should be enough */
#define CHUNK_SIZE (128 * 1024)
#define STACK_MAP_MAGIC "really-unique-stack-pointer-for-xp-detection-goodness"

typedef struct {
  char	        dest_stream[60];
  unsigned long length;
  char          data[0];
} Chunk;
#define CHUNK_PAYLOAD (CHUNK_SIZE - sizeof (Chunk))

typedef struct {
  char   magic[sizeof (STACK_MAP_MAGIC)];
  Chunk *chunks[1024];
  int    max_chunk;
} StackMap;
#define STACK_MAP_INIT { STACK_MAP_MAGIC, { 0, }, 0 }

typedef struct {
  StackMap   *sm;
  const char *dest;
  Chunk      *cur;
} BufferFile;

BufferFile *buffer_file_new (StackMap *sm, const char *output_fname);
void buffer_file_dump (BufferFile *file, int input_fd);
void buffer_file_append (BufferFile *file, const char *str, size_t len);
void buffer_file_dump_frame_with_timestamp (BufferFile *file, int input_fd,
					    const char *uptime, size_t uptimelen);
void buffer_file_append (BufferFile *file, const char *str, size_t len);

int  dump_state (const char *output_path);
int  bootchart_find_running_pid (void);

#endif /* BOOTCHART_COMMON_H */
