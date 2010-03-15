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

/*
 * Allocation fun ...
 */

// #define CHUNK_SIZE (128 * 1024)
#define CHUNK_SIZE 128
#define CHUNK_MAGIC "xp-dt!"

typedef struct _Chunk Chunk;
struct _Chunk {
  char   magic[8];
  char	 dest_stream[64];
  guint  head : 1;
  long   length : 31;
  Chunk *next;
  char   data[0];
};
#define CHUNK_PAYLOAD (CHUNK_SIZE - sizeof (Chunk))

typedef struct {
  Chunk *head;
  Chunk *cur;
} Buffer;

static Chunk *chunk_alloc (const char *dest)
{
  Chunk *p = mmap (NULL, CHUNK_SIZE, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
  memset (p, 0, sizeof (Chunk));
  strncpy (p->magic, CHUNK_MAGIC, sizeof (p->magic));
  strncpy (p->dest_stream, dest, sizeof (p->dest_stream));
  return p;
}

static Buffer *
buffer_new (const char *dest)
{
  Buffer *b = g_new0 (Buffer, 1);
  b->head = chunk_alloc (dest);
  b->head->head = 1;
  b->cur = b->head;
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
	{
	  c->next = chunk_alloc (c->dest_stream);
	  b->cur = c->next;
	}
    }
}

typedef struct {
  size_t addr;
} ChunkPtr;

typedef struct {
  int    pid;
  int    mem;
  GList *heads;
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

/*
 * Work out where the linked lists are.
 */
static void find_heads (DumpState *s)
{
  FILE *maps;
  char buffer[4096];
  char *name;
  size_t result = 0;

  maps = fopen ((name = g_strdup_printf ("/proc/%d/maps", s->pid)), "r");
  g_free (name);

  while (!result && fgets (buffer, 4096, maps))
    {
      char **elems = g_strsplit (g_strstrip (buffer), " ", -1);
      int len = g_strv_length (elems);

      /* anonymous maps only */
      if (len > 1 && !strcmp (elems[len - 1], "0"))
	{
	  /* 0x12345-0x23456 */
	  char *p = strchr (elems[0], '-');
	  fprintf (stderr, "addrs: '%s'\n", elems[0]);
	  if (p)
	    {
	      Chunk chunk;
	      size_t start, end;
	      *p = '\0';
	      start = strtoull (elems[0], NULL, 0x10);
	      end = strtoull (p + 1, NULL, 0x10);
	      memset (&chunk, 0, sizeof (chunk));
	      fprintf (stderr, "map 0x%lx -> 0x%lx size: %dk from '%s'\n",
		       (long) start, (long)end,
		       (int)(end - start) / 1024, elems[0]);
	      pread (s->mem, &chunk, sizeof (chunk), start);
	      fprintf (stderr, "magic: '%s' dest '%s'\n", chunk.magic, chunk.dest_stream);
	      if (!strcmp (chunk.magic, CHUNK_MAGIC))
		{
		  ChunkPtr *p = g_new0 (ChunkPtr, 1);
		  p->addr = start;
		  s->heads = g_list_prepend (s->heads, p);
		}
	    }
	}
      g_strfreev (elems);
    }
  fclose (maps);
}

static void dump_buffers (DumpState *s)
{
  GList *l;
  char buffer[CHUNK_SIZE];
  Chunk *c = (Chunk *)&buffer;

  fprintf (stderr, "%d heads\n", g_list_length (s->heads));
  for (l = s->heads; l; l = l->next)
    {
      ChunkPtr *p = l->data;
      size_t addr = p->addr;
      while (addr != 0)
	{
	  pread (s->mem, &buffer, CHUNK_SIZE, addr);
	  fprintf (stderr, "Magic '%s', type: '%s'\n", c->magic, c->dest_stream);
	  fwrite (c->data, 1, c->length, stderr);
	  addr = (size_t) c->next;
	}
    }
}

int main (int argc, char **argv)
{
  if (argc <= 1)
    {
      int i;
      Buffer *b[2];
      fprintf (stderr, "server\n");
      b[0] = buffer_new ("fish");
      b[1] = buffer_new ("heads");
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
	  find_heads (state);
	  dump_buffers (state);
	  close_pid (state);
	}
    }

  return 0;
}
