/*
 * bootchart-common.h - shared data structures
 */
#ifndef BOOTCHART_COMMON_H
#define BOOTCHART_COMMON_H

/* get the right versions of various key functions */
#define _XOPEN_SOURCE 800
#define _FILE_OFFSET_BITS 64
#define _LARGEFILE64_SOURCE
#define _BSD_SOURCE
#define _ATFILE_SOURCE
#define _GNU_SOURCE

#include <sys/mount.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/select.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/wait.h>

#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <dirent.h>
#include <limits.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ctype.h>
#include <alloca.h>
#include <pthread.h>

#include "macro.h"

/* Magic path we mount our tmpfs on, inside which we do everything */
#define TMPFS_PATH PKGLIBDIR "/tmpfs"
#define PROC_PATH  PKGLIBDIR "/tmpfs/proc"
/* where we lurk to get move mounted into the live system */
#define MOVE_DEV_PATH "/dev/." PROGRAM_PREFIX "bootchart" PROGRAM_SUFFIX

/* helpers */
#undef	MAX
#undef	MIN
#define MAX(a, b)  (((a) > (b)) ? (a) : (b))
#define MIN(a, b)  (((a) < (b)) ? (a) : (b))

/* ---------------- collector.c  ---------------- */

/* it is nice to be able to parse the remote process' arguments too */
typedef struct {
	unsigned int   console_debug : 1;
	unsigned int   probe_running : 1;
	unsigned int   relative_time : 1;
	char          *dump_path;
	long	       usleep_time;
	int            hz;
} Arguments;

void arguments_set_defaults (Arguments *args);
void arguments_parse        (Arguments *args, int argc, char **argv);
void arguments_free         (Arguments *args);

/* ---------------- output.c  ---------------- */

/* Max ~ 128Mb of space for logging, should be enough */
#define CHUNK_SIZE (128 * 1024)
#define STACK_MAP_MAGIC "really-unique-stack-pointer-for-xp-detection-goodness"

typedef struct {
	char          dest_stream[60];
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

BufferFile *buffer_file_new            (StackMap *sm, const char *output_fname);
void        buffer_file_dump           (BufferFile *file, int input_fd);
void        buffer_file_append         (BufferFile *file, const char *str, size_t len);
void        buffer_file_dump_frame_with_timestamp
                                       (BufferFile *file, int input_fd,
					const char *uptime, size_t uptimelen);

int         buffers_extract_and_dump   (const char *output_path,
					Arguments  *remote_args);
int         dump_dmsg                  (const char *output_path);
int         dump_header                (const char *output_path);
int         bootchart_find_running_pid (Arguments *opt_args);

/* ---------------- tasks.c  ---------------- */

/*
 * a big bit-field, one bit per pid.
 */
typedef struct {
	int  len;
	unsigned char *pids;
} PidMap;

typedef enum {
	PID_SCAN_EVENT_EXEC,    /* signal dump of cmdline */
	PID_SCAN_EVENT_CREATED  /* signal process creation - not reliable */
} PidScanEventType;

typedef struct {
	PidScanEventType type;
	pid_t pid;
	union {
		pid_t ppid;
	} u;
} PidScanEvent;

typedef void (*PidScanEventFn) (const PidScanEvent *event, void *user_data);

typedef struct _PidScanner PidScanner;
struct _PidScanner {
	PidMap          map;
	PidScanEventFn  event_fn;
	void           *user_data;

	int    (*free)         (PidScanner *scanner);  
	void   (*restart)      (PidScanner *scanner);  
	pid_t  (*next)         (PidScanner *scanner);
	pid_t  (*get_cur_pid)  (PidScanner *scanner);
	pid_t  (*get_cur_ppid) (PidScanner *scanner);

	void   (*get_tasks_start) (PidScanner *scanner);
	pid_t  (*get_tasks_next)  (PidScanner *scanner);
	void   (*get_tasks_stop)  (PidScanner *scanner);
};

PidScanner *pid_scanner_new_netlink     (PidScanEventFn event_cb,
					 void	     *user_data);
PidScanner *pid_scanner_new_proc	(const char *proc_path,
					 PidScanEventFn event_cb,
					 void	     *user_data);
#define	    pid_scanner_free(s)         (s)->free(s)

#define	    pid_scanner_restart(s)      (s)->restart(s)
#define	    pid_scanner_next(s)         (s)->next(s)
#define	    pid_scanner_get_cur_pid(s)  (s)->get_cur_pid(s)
#define	    pid_scanner_get_cur_ppid(s) (s)->get_cur_ppid(s)

#define	    pid_scanner_get_tasks_start(s)  (s)->get_tasks_start(s)
#define	    pid_scanner_get_tasks_next(s)   (s)->get_tasks_next(s)
#define	    pid_scanner_get_tasks_stop(s)   (s)->get_tasks_stop(s)

/* for impl. only */
PidScanner *pid_scanner_alloc           (int            derived_size,
					 PidScanEventFn event_cb,
					 void	       *user_data);
void	    pid_scanner_emit_exec       (PidScanner    *scanner,
					 pid_t          new_pid);
void	    pid_scanner_emit_paternity  (PidScanner    *scanner,
					 pid_t          new_pid,
					 pid_t          parent);

#endif /* BOOTCHART_COMMON_H */
