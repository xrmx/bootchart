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

/*
 * a big bit-field, one bit per pid.
 */
typedef struct {
  int  len;
  unsigned char *pids;
} PidMap;

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

struct _PidScanner {
  PidCreatedFn   create_cb;
  PidMap         map;

  /* fields for /proc polling */
  DIR           *proc;
  struct dirent *cur_ent;
  pid_t	         cur_pid;

  /* fields for /proc/task polling */
  DIR		*proc_task;
};

PidScanner *
pid_scanner_new (const char *proc_path, PidCreatedFn create_cb)
{
  DIR *proc;
  PidScanner *scanner;

  proc = opendir (proc_path);
  if (!proc) {
    fprintf (stderr, "Failed to open " PROC_PATH ": %s\n", strerror(errno));
    return NULL;
  }
  scanner = calloc (1, sizeof (PidScanner));
  if (!scanner) {
    closedir (proc);
    return NULL;
  }
  scanner->create_cb = create_cb;
  scanner->proc = proc;
  scanner->cur_ent = NULL;

  return scanner;
}

int
pid_scanner_free (PidScanner *scanner)
{
  int ret = 0;
  if (scanner) {
    if (closedir (scanner->proc) < 0)
      {
	perror ("close /proc");
	ret = 1;
      }
    free (scanner);
  }
  return ret;
}

void
pid_scanner_restart (PidScanner *scanner)
{
  rewinddir (scanner->proc);
}

pid_t
pid_scanner_next (PidScanner *scanner)
{
  pid_t pid;

  do {
    if (!(scanner->cur_ent = readdir (scanner->proc)))
      return 0;
  } while (!isdigit (scanner->cur_ent->d_name[0]));

  pid = atoi (scanner->cur_ent->d_name);
  scanner->cur_pid = pid;

  if (/* scanner->create_cb && */
      !was_known_pid (&scanner->map, pid)) {
    fprintf (stdout, "new pid %d\n", pid);
    if (scanner->create_cb)
      scanner->create_cb (pid, 0);
  }

  return pid;
}

pid_t
pid_scanner_get_cur_pid (PidScanner *scanner)
{
  return scanner->cur_pid;
}

void
pid_scanner_get_tasks_start (PidScanner *scanner)
{
  // use dirfd and 'openat' to accelerate task reading & path concstruction [!]
  int dfd;
  char *buffer = alloca (scanner->cur_ent->d_reclen + 10);

  strcpy (buffer, scanner->cur_ent->d_name);
  strcat (buffer, "/task");

  dfd = openat (dirfd (scanner->proc), buffer, O_RDONLY|O_NONBLOCK|O_LARGEFILE|O_DIRECTORY);
  if (dfd < 0)
    scanner->proc_task = NULL;
  else
    scanner->proc_task = fdopendir (dfd);
}

void
pid_scanner_get_tasks_stop (PidScanner *scanner)
{
  if (scanner->proc_task) {
    closedir (scanner->proc_task);
    scanner->proc_task = NULL;
  }
}

/*
 * Return all tasks that are not the current pid.
 */
pid_t
pid_scanner_get_tasks_next (PidScanner *scanner)
{
  struct dirent *tent;

  if (!scanner->proc_task)
    return 0;

  for (;;) {
    pid_t tpid;

    if ((tent = readdir (scanner->proc_task)) == NULL)
      return 0;
    if (!isdigit (tent->d_name[0]))
      continue;
    if ((tpid = atoi (tent->d_name)) != scanner->cur_pid) {
/*    fprintf (stdout, "pid %d has tpid %d\n", scanner->cur_pid, tpid); */
      return tpid;
    }
  }
}

#if 0 
/* urgh */
static 
static PidDeletedFn delete_cb;

/* -------------- old style /proc readdir -------------- */

/*
 * a big bit-field, one bit per pid.
 */
typedef struct {
  int  len;
  unsigned char *pids;
} PidMap;

static int
was_known_pid (PidMap *map, pid_t p)
{
  int bit = p & 0x7;
  int offset = p >> 3;
  int was_known;

  if (map->len <= offset) {
    map->len += 512;
    ma->pids = realloc (map->pids, map->len);
    memset (map->pids + map->len - 512, 0, 512);
  }

  was_known = map->pids[offset] & (1 << bit);
  map->pids[offset] |= (1 << bit);

  return was_known;
}

static void
proc_readdir_scan (PidMap *map, DIR *in_proc)
{
  DIR *proc = in_proc;
  struct dirent *ent;

  if (!proc)
    rewinddir (proc);
  else
    proc = opendir (PROC_PATH);

  if (!proc)
    return;

  while ((ent = readdir (proc)) != NULL) {
    pid_t pid;

    if (!isdigit (ent->d_name[0]))
      continue;

    if (!was_known (map, pid))
      create_cb (pid, 0);
  }

  if (!in_proc)
    closedir (proc);
}

static void
proc_readdir_consolidate (PidMap *map, PidMap *map)
{
  /* compare PidMaps and emit 'deleted' events ? */
}

static void
proc_polling_evil (void *)
{
}


static void
netlink_goodness (void *)
{
}

void
pid_scan_start (PidCreatedFn _create_cb,
		PidDeletedFn _delete_cb)
{
  PidMap map = { 0, 0 };

  create_cb = _create_cb;
  delete_cb = _delete_cb;

  proc_readdir_scan (&map, NULL);

  if (can_open_netlink_foo()) {
    pthread_create (netlink_goodness);
  } else {
    pthread_create (proc_polling_evil);
  }
}

void
pid_scan_stop (void)
{
}



/*
 * FIXME - everyone reads from the PidEntries table,
 *       - but, changes to it are queued up for merging 
 *         later ? - how can it change ? new pids @ end ?
 */

/*
 * FIXME: problems - we need to keep time_total up-to-date there ...
 *        hmmm [!] - we need a structure we can read/write to from
 *	  multiple threads concurrently. Urk.
 */

/* FIXME - threading means duplication */
/* so - we have two sets of data - a bit-field magic in here */
/* and some call-backs, queueing things up for the other process */
/* we create some memory and throw it across (somehow) */

#endif
