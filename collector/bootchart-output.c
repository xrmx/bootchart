/*
 * bootchart-output - finds, and dumps state from a main bootchart process
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
 * Copyright (C) 2009-2010 Novell, Inc.
 */

#include "bootchart-common.h"

#include <sys/ptrace.h>
#include <sys/mman.h>


/* simple, easy to unwind via ptrace-able buffer structures */

static Chunk *chunk_alloc (StackMap *sm, const char *dest)
{
  Chunk *c;

  /* if we run out of buffer, just keep writing to the last buffer */
  if (sm->max_chunk == sizeof (sm->chunks)/sizeof(sm->chunks[0]))
    {
      static int overflowed = 0;
      if (!overflowed)
	{
	  fprintf (stderr, "bootchart-collector - internal buffer overflow! "
		   "did you set hz (%lu) too high\n", hz);
	  overflowed = 1;
	}
      c = sm->chunks[sm->max_chunk - 1];
      c->length = 0;
      return c;
    }

  c = calloc (CHUNK_SIZE, 1);
  strncpy (c->dest_stream, dest, sizeof (c->dest_stream));
  c->length = 0;
  sm->chunks[sm->max_chunk++] = c;
  return c;
}

BufferFile *
buffer_file_new (StackMap *sm, const char *output_fname)
{
  BufferFile *b = calloc (sizeof (BufferFile), 1);
  b->sm = sm;
  b->dest = output_fname;
  b->cur = chunk_alloc (b->sm, b->dest);
  return b;
}

void
buffer_file_append (BufferFile *file, const char *str, size_t len)
{
  do {
    unsigned long to_write = MIN (CHUNK_PAYLOAD - file->cur->length, len);
    memcpy (file->cur->data + file->cur->length, str, to_write);
    str += to_write;
    len -= to_write;
    file->cur->length += to_write;
    if (file->cur->length >= CHUNK_PAYLOAD)
      file->cur = chunk_alloc (file->sm, file->dest);
  } while (len > 0);
}

/* dump whole contents of input_fd to the output 'file' */

void
buffer_file_dump (BufferFile *file, int input_fd)
{
  for (;;) {
    unsigned long to_read = CHUNK_PAYLOAD - file->cur->length;

    to_read = read (input_fd, file->cur->data + file->cur->length, to_read);
    if (to_read < 0) {
      perror ("read error");
      break;
    } else if (to_read == 0) {
      break;
    }
    file->cur->length += to_read;
    if (file->cur->length >= CHUNK_PAYLOAD)
      file->cur = chunk_alloc (file->sm, file->dest);
  }
}

void
buffer_file_dump_frame_with_timestamp (BufferFile *file, int input_fd,
				       const char *uptime, size_t uptimelen)
{
  buffer_file_append (file, uptime, uptimelen);

  lseek (input_fd, SEEK_SET, 0);
  buffer_file_dump (file, input_fd);
  
  buffer_file_append (file, "\n", 1);
}

/* grubbing about in another process to dump those buffers */

typedef struct {
  int pid;
  int mem;
  StackMap map;
} DumpState;

static StackMap *
search_stack (char *stack, size_t len)
{
  char *p;
  for (p = stack; p < stack + len; p++)
    {
      if (!strcmp (((StackMap *)p)->magic, STACK_MAP_MAGIC))
	return (StackMap *)p;
    }
  return NULL;
}

static int
find_chunks (DumpState *s)
{
  FILE *maps;
  char buffer[1024];
  size_t result = 0;
  StackMap *map;
  int ret = 1;

  snprintf (buffer, 1024, "/proc/%d/maps", s->pid);
  maps = fopen (buffer, "r");

  while (!result && fgets (buffer, 4096, maps))
    {
      char *p, *copy;
      size_t start, end;

      /* hunt the stackstack only */
      if (!strstr (buffer, "[stack]"))
	continue;

      if (!(p = strchr (buffer, ' ')))
	continue;
      *p = '\0';

      /* buffer: 0x12345-0x23456 */
      if (!(p = strchr (buffer, '-')))
	continue;
      *p = '\0';

      start = strtoull (buffer, NULL, 0x10);
      end = strtoull (p + 1, NULL, 0x10);
	  
      fprintf (stderr, "map 0x%lx -> 0x%lx size: %dk from '%s' '%s'\n",
	       (long) start, (long)end,
	       (int)(end - start) / 1024,
	       buffer, p + 1);

      copy = malloc (end - start);
      pread (s->mem, copy, end - start, start);

      map = search_stack (copy, end - start);
      if (map) {
	s->map = *map;
	ret = 0;
      }

      free (copy);
    }
  fclose (maps);

  return ret;
}

static DumpState *open_pid (int pid)
{
  char name[1024];
  DumpState *s;

  if (ptrace(PTRACE_ATTACH, pid, 0, 0))
    {
      fprintf (stderr, "cannot ptrace %d\n", pid);
      return NULL;
    }

  snprintf (name, 1024, "/proc/%d/mem", pid);
  s = calloc (sizeof (DumpState), 1);
  s->pid = pid;
  s->mem = open (name, O_RDONLY|O_LARGEFILE);
  if (s->mem < 0)
    {
      fprintf (stderr, "Failed to open memory map\n"); 
      free (s);
      return NULL;
    }

  return s;
}

static void close_pid (DumpState *s)
{
  ptrace (PTRACE_KILL, s->pid, 0, 0);
  ptrace (PTRACE_DETACH, s->pid, 0, 0);
  close (s->mem);
  free (s);
}

static void dump_buffers (DumpState *s)
{
  int i;

  fprintf (stderr, "%d chunks\n", s->map.max_chunk);
  for (i = 0; i < s->map.max_chunk; i++)
    {
      FILE *output;
      char buffer[CHUNK_SIZE];
      Chunk *c = (Chunk *)&buffer;
      size_t addr = (size_t) s->map.chunks[i];

      pread (s->mem, &buffer, CHUNK_SIZE, addr);
      fprintf (stderr, "type: '%s' len %d\n",
	       c->dest_stream, (int)c->length);

      output = fopen (c->dest_stream, "a+");
      fwrite (c->data, 1, c->length, output);
      fclose (output);
    }
}
 
/*
 * Used to find, extract and dump state from
 * a running bootchartd process.
 */
int
dump_state (const char *output_path)
{
  int pid, ret = 1;
  DumpState *state;

  chdir (output_path);

  pid = bootchart_find_running_pid ();
  if (pid < 0) {
    fprintf (stderr, "Failed to find the collector's pid\n");
    return 1;
  }
  fprintf (stderr, "Extracting profile data from pid %d\n", pid);

  if (!(state = open_pid (pid))) 
    return 1;

  if (find_chunks (state)) {
    fprintf (stderr, "Couldn't find state structures on pid %d's stack\n", pid);
    ret = 1;
  } else
    dump_buffers (state);

  close_pid (state);

  return 0;
}

/*
 * finds (another) bootchart-collector process and
 * returns it's pid (or -1) if not found, ignores
 * the --usleep mode we use to simplify our scripts.
 */
int
bootchart_find_running_pid (void)
{
  DIR *proc;
  struct dirent *ent;
  int pid = -1;
  char exe_path[1024];
    
  proc = opendir (PROC_PATH);
  while ((ent = readdir (proc)) != NULL) {
    int len;
    char link_target[1024];

    if (!isdigit (ent->d_name[0]))
      continue;

    strcpy (exe_path, PROC_PATH);
    strcat (exe_path, "/");
    strcat (exe_path, ent->d_name);
    strcat (exe_path, "/exe");

    if ((len = readlink (exe_path, link_target, 1024)) < 0)
      continue;
    link_target[len] = '\0';

    if (strstr (link_target, "bootchart-collector")) {
      FILE *args;
      int harmless = 0;

      int p = atoi (ent->d_name);

/*      fprintf (stderr, "found collector '%s' pid %d (my pid %d)\n", link_target, p, getpid()); */

      if (p == getpid())
	continue; /* I'm not novel */

      strcpy (exe_path + strlen (exe_path) - strlen ("/exe"), "/cmdline");
      args = fopen (exe_path, "r");
      if (args) {
	int i;
	char abuffer[4096];

	len = fread (abuffer, 1, 4095, args);
	if (len > 0) {
	  /* step through args */
	  abuffer[len] = '\0';
	  for (i = 0; i < len - 1; i++)
	    if (abuffer[i] == '\0') {
	      if (!strcmp (abuffer + i + 1, "--usleep"))
		harmless = 1;
/*	      fprintf (stderr, "arg '%s' -> %d\n", abuffer + i + 1, harmless); */
	    }
	  fclose (args);
	}
      }

      if (!harmless) {
	pid = p;
	break;
      }
    }
  }
  closedir (proc);

  return pid;
}
