#define _XOPEN_SOURCE 600
#define _FILE_OFFSET_BITS 64
#define _LARGEFILE64_SOURCE
#define _BSD_SOURCE

#include <stdio.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ptrace.h>
#include <sys/mman.h>
#include <glib.h>

/* Max ~ 128Mb of space for logging, should be enough */
#define CHUNK_SIZE (128 * 1024)
#define STACK_MAP_MAGIC "really-unique-stack-pointer-for-xp-detection-goodness"

typedef struct _Chunk Chunk;
struct _Chunk {
  char	 dest_stream[60];
  long   length;
  char   data[0];
};
#define CHUNK_PAYLOAD (CHUNK_SIZE - sizeof (Chunk))

typedef struct {
  char   magic[sizeof (STACK_MAP_MAGIC)];
  Chunk *chunks[1024];
  int    max_chunk;
} StackMap;
#define STACK_MAP_INIT { STACK_MAP_MAGIC, { 0, }, 0 }

typedef struct {
  StackMap *sm;
  Chunk    *cur;
} Buffer;

static Chunk *chunk_alloc (StackMap *sm, const char *dest)
{
  Chunk *c;

  /* if we run out of buffer, just keep writing to the last buffer */
  if (sm->max_chunk == G_N_ELEMENTS (sm->chunks))
    {
      c = sm->chunks[sm->max_chunk - 1];
      c->length = 0;
      return c;
    }

  c = mmap (NULL, CHUNK_SIZE, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
  memset (c, 0, sizeof (Chunk));
  strncpy (c->dest_stream, dest, sizeof (c->dest_stream));
  sm->chunks[sm->max_chunk++] = c;
  return c;
}

static Buffer *
buffer_new (StackMap *sm, const char *dest)
{
  Buffer *b = g_new0 (Buffer, 1);
  b->sm = sm;
  b->cur = chunk_alloc (b->sm, dest);
  return b;
}

static void buffer_append (Buffer *b, const char *str, long len)
{
  while (len > 0)
    {
      Chunk *c = b->cur;
      long append;

      append = MIN (len, CHUNK_PAYLOAD - c->length);
      
      strncpy (c->data + c->length, str, append);
      str += append;
      c->length += append;
      len -= append;

      if (c->length == CHUNK_PAYLOAD)
	  b->cur = chunk_alloc (b->sm, c->dest_stream);
    }
}

typedef struct {
  int pid;
  int mem;
  StackMap map;
} DumpState;

static DumpState *open_pid (const char *apid)
{
  int pid;
  char *name;
  DumpState *s;

  pid = atoi (apid);
  fprintf (stderr, "attach to pid %d\n", pid);

  if (ptrace(PTRACE_ATTACH, pid, 0, 0))
    {
      fprintf (stderr, "cannot ptrace %d\n", pid);
      return NULL;
    }

  s = g_new0 (DumpState, 1);
  s->pid = pid;
  s->mem = open ((name = g_strdup_printf ("/proc/%s/mem", apid)), O_RDONLY|O_LARGEFILE);
  g_free (name);
  if (s->mem < 0)
    {
      fprintf (stderr, "Failed to open memory map\n"); 
      g_free (s);
      return NULL;
    }

  return s;
}

static void close_pid (DumpState *s)
{
  ptrace (PTRACE_DETACH, s->pid, 0, 0);
  close (s->mem);
  g_free (s);
}

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

static void find_chunks (DumpState *s)
{
  FILE *maps;
  char buffer[4096];
  char *name;
  size_t result = 0;
  StackMap *map;

  maps = fopen ((name = g_strdup_printf ("/proc/%d/maps", s->pid)), "r");
  g_free (name);

  while (!result && fgets (buffer, 4096, maps))
    {
      char **elems = g_strsplit (g_strstrip (buffer), " ", -1);
      int len = g_strv_length (elems);

      /* anonymous maps only */
      if (len > 1 && strstr (elems[len - 1], "stack"))
	{
	  /* 0x12345-0x23456 */
	  char *p = strchr (elems[0], '-');
	  fprintf (stderr, "addrs: '%s'\n", elems[0]);
	  if (p)
	    {
	      char *copy;
	      size_t start, end;
	      *p = '\0';
	      start = strtoull (elems[0], NULL, 0x10);
	      end = strtoull (p + 1, NULL, 0x10);

	      fprintf (stderr, "map 0x%lx -> 0x%lx size: %dk from '%s'\n",
		       (long) start, (long)end,
		       (int)(end - start) / 1024, elems[0]);

	      copy = g_malloc (end - start);
	      pread (s->mem, copy, end - start, start);

	      map = search_stack (copy, end- start);
	      if (map)
		  s->map = *map;

	      g_free (copy);
	    }
	}
      g_strfreev (elems);
    }
  fclose (maps);
}

static void dump_buffers (DumpState *s)
{
  int i;

  fprintf (stderr, "%d chunks\n", s->map.max_chunk);
  for (i = 0; i < s->map.max_chunk; i++)
    {
      char buffer[CHUNK_SIZE];
      Chunk *c = (Chunk *)&buffer;
      size_t addr = (size_t) s->map.chunks[i];

      pread (s->mem, &buffer, CHUNK_SIZE, addr);
      fprintf (stderr, "type: '%s' len %d\n",
	       c->dest_stream, (int)c->length);
      fwrite (c->data, 1, c->length, stderr);
      fprintf (stderr, "\n");
    }
}

int main (int argc, char **argv)
{
  if (argc <= 1)
    {
      int i;
      Buffer *b[2];
      StackMap sm = STACK_MAP_INIT;
      fprintf (stderr, "server\n");
      b[0] = buffer_new (&sm, "fish");
      b[1] = buffer_new (&sm, "heads");
      for (i = 0; i < 80; i++)
	{
	  char *txt = g_strdup_printf ("freznel mirrors are the future: %d\n", i);
	  buffer_append (b[i%2], txt, strlen (txt));
	  g_free (txt);
	}
      fprintf (stderr, "logging complete.\n");
      while (TRUE)
	{
	  g_usleep (1000*500);
	}
    }
  else
    {
      const char *apid;
      DumpState *state;

      apid = argv[argc-1];

      state = open_pid (apid);
      if (state) 
	{
	  find_chunks (state);
	  dump_buffers (state);
	  close_pid (state);
	}
    }

  return 0;
}
