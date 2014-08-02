/*
 * tasks - code to provide a view of what processes are available
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2, or (at your option)
 *  any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; see the file COPYING.  If not, write to
 *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 * Author: Michael Meeks <michael.meeks@novell.com>
 * Copyright (C) 2010 Novell, Inc.
 */

#include "common.h"

static int
was_known_pid (PidMap *map, pid_t p)
{
	int bit = p & 0x7;
	int offset = p >> 3;
	int was_known;

	if (map->len <= offset) {
		map->len += 512;
		map->pids = realloc (map->pids, map->len);
		memset (map->pids + map->len - 512, 0, 512);
	}

	was_known = map->pids[offset] & (1 << bit);
	map->pids[offset] |= (1 << bit);

	return was_known;
}

typedef struct {
	PidScanner     parent;

	/* fields for /proc polling */
	DIR           *proc;
	struct dirent *cur_ent;
	pid_t	         cur_pid;

	/* fields for /proc/task polling */
	DIR		*proc_task;
} ProcPidScanner;

PidScanner *
pid_scanner_alloc (int derived_size, PidScanEventFn event_fn, void *user_data)
{
	PidScanner *scanner;

	scanner = calloc (1, derived_size);
	scanner->event_fn = event_fn;
	scanner->user_data = user_data;

	return scanner;
}

static int
proc_pid_scanner_free (PidScanner *scanner)
{
	int ret = 0;
	ProcPidScanner *ps = (ProcPidScanner *)scanner;

	if (scanner) {
		if (closedir (ps->proc) < 0)
			{
				perror ("close /proc");
				ret = 1;
			}
		free (scanner);
	}
	return ret;
}

static void
proc_pid_scanner_restart (PidScanner *scanner)
{
	ProcPidScanner *ps = (ProcPidScanner *)scanner;
	rewinddir (ps->proc);
}

static pid_t
proc_pid_scanner_next (PidScanner *scanner)
{
	pid_t pid;
	ProcPidScanner *ps = (ProcPidScanner *)scanner;

	do {
		if (!(ps->cur_ent = readdir (ps->proc)))
			return 0;
	} while (!isdigit (ps->cur_ent->d_name[0]));

	pid = atoi (ps->cur_ent->d_name);
	ps->cur_pid = pid;

	pid_scanner_emit_exec (scanner, pid);

	return pid;
}

static pid_t
proc_pid_scanner_get_cur_pid (PidScanner *scanner)
{
	ProcPidScanner *ps = (ProcPidScanner *)scanner;
	return ps->cur_pid;
}

static pid_t
proc_pid_scanner_get_cur_ppid (PidScanner *scanner)
{
	return 0;
}

static void
proc_pid_scanner_get_tasks_start (PidScanner *scanner)
{
	// use dirfd and 'openat' to accelerate task reading & path concstruction [!]
	int dfd;
	ProcPidScanner *ps = (ProcPidScanner *)scanner;
	char *buffer = alloca (ps->cur_ent->d_reclen + 10);

	strcpy (buffer, ps->cur_ent->d_name);
	strcat (buffer, "/task");

	dfd = openat (dirfd (ps->proc), buffer, O_RDONLY|O_NONBLOCK|O_LARGEFILE|O_DIRECTORY);
	if (dfd < 0) {
		ps->proc_task = NULL;
/*		log ("error: failed to open '%s'\n", buffer); */
	} else
		ps->proc_task = fdopendir (dfd);
}

static void
proc_pid_scanner_get_tasks_stop (PidScanner *scanner)
{
	ProcPidScanner *ps = (ProcPidScanner *)scanner;

	if (ps->proc_task) {
		closedir (ps->proc_task);
		ps->proc_task = NULL;
	}
}

/*
 * Return all tasks that are not the current pid.
 */
static pid_t
proc_pid_scanner_get_tasks_next (PidScanner *scanner)
{
	struct dirent *tent;
	ProcPidScanner *ps = (ProcPidScanner *)scanner;

	if (!ps->proc_task)
		return 0;

	for (;;) {
		pid_t tpid;

		if ((tent = readdir (ps->proc_task)) == NULL)
			return 0;
		if (!isdigit (tent->d_name[0]))
			continue;
		if ((tpid = atoi (tent->d_name)) != ps->cur_pid) {
/*			log ("pid %d has tpid %d\n", ps->cur_pid, tpid); */
			return tpid;
		}
	}
}

PidScanner *
pid_scanner_new_proc (const char *proc_path, PidScanEventFn event_fn, void *user_data)
{
	ProcPidScanner *ps;

	ps = (ProcPidScanner *) pid_scanner_alloc (sizeof (ProcPidScanner),
						   event_fn, user_data);
	ps->proc = opendir (proc_path);
	if (!ps->proc) {
		log ("Failed to open " PROC_PATH ": %s\n", strerror(errno));
		free (ps);
		return NULL;
	}
	ps->cur_ent = NULL;

	/* vtable land-fill */
#define INIT(name) ps->parent.name = proc_pid_scanner_##name
	INIT(free);
	INIT(restart);
	INIT(next);
	INIT(get_cur_pid);
	INIT(get_cur_ppid);
	INIT(get_tasks_start);
	INIT(get_tasks_next);
	INIT(get_tasks_stop);
#undef INIT

	return (PidScanner *)ps;
}

void
pid_scanner_emit_exec (PidScanner *scanner, pid_t new_pid)
{
	PidScanEvent ev = { PID_SCAN_EVENT_EXEC, 0 };

	if (!scanner->event_fn)
		return;
  
	if (was_known_pid (&scanner->map, new_pid))
		return;

	ev.pid = new_pid;
	scanner->event_fn (&ev, scanner->user_data);
}

/*
 *    After extensive testing, processes have been
 * determined to be male:
 */
void
pid_scanner_emit_paternity (PidScanner *scanner,
			    pid_t       new_pid,
			    pid_t       parent)
{
	PidScanEvent ev = { PID_SCAN_EVENT_CREATED, 0 };

	if (!scanner->event_fn)
		return;
  
	ev.pid = new_pid;
	ev.u.ppid = parent;
	scanner->event_fn (&ev, scanner->user_data);
}
