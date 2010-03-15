#define _XOPEN_SOURCE 600
#define _FILE_OFFSET_BITS 64
#define _LARGEFILE64_SOURCE

#include <stdio.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ptrace.h>
#include <glib.h>

#define BUFFER_SIZE (1024 * 1024 * 64)

#define HEADER_MAGIC "xp-data!"
struct _Header {
  char            magic[8];
  long            length;
  struct _Header *next;
  char            data[1];
};
typedef struct _Header Header;

typedef struct {
  int mem;
  GList *buffers;
} ProcessData;

static ProcessData *find_buffers (const char *apid)
{
  FILE *maps;
  int  mem;
  char buffer[4096];
  char *name;
  size_t result = 0;

  mem = open ((name = g_strdup_printf ("/proc/%s/mem", apid)), O_RDONLY|O_LARGEFILE);
  g_free (name);
  if (mem < 0)
    {
      fprintf (stderr, "Failed to open memory map\n"); 
      return 0;
    }
  maps = fopen ((name = g_strdup_printf ("/proc/%s/maps", apid)), "r");
  g_free (name);

  while (!result && fgets (buffer, 4096, maps))
    {
      char **elems = g_strsplit (g_strstrip (buffer), " ", -1);
      int len = g_strv_length (elems);

      if (len > 1 && !strcmp (elems[len - 1], "0"))
	{
	  char *p = strchr (elems[0], '-');
	  if (p)
	    {
	      Header header;
	      size_t start = strtoull (elems[0], NULL, 0x10);
	      size_t end = strtoull (p + 1, NULL, 0x10);
	      memset (&header, 0, sizeof (header));
	      fprintf (stderr, "map 0x%llx -> 0x%llx size: %dk\n", start, end,
		       (int)(end - start) / 1024);
	      pread (mem, &header, sizeof (header), 3009449992); // start);
	      if (!strcmp (header.magic, HEADER_MAGIC))
		{
		  fprintf (stderr, "bingo !\n");
		}
	    }
	}
      g_strfreev (elems);
    }
  fclose (maps);
  close (mem);

  return NULL;
}

int main (int argc, char **argv)
{
  volatile Header *data;
  if (argc <= 1)
    {
      fprintf (stderr, "server\n");
      data = g_malloc0 (BUFFER_SIZE);
      strcpy ((char *)data->magic, HEADER_MAGIC);
      strcpy ((char *)data->data, "this is an long essay packed with fun!");
      while ((data->data[0] == 't'))
	{
	  g_usleep (1000*500);
	}
    }
  else
    {
      int pid;
      const char *apid;
      gulong buffer_addr;

      apid = argv[argc-1];
      pid = atoi (apid);
      fprintf (stderr, "attach to pid %d\n", pid);

      if (ptrace(PTRACE_ATTACH, pid, 0, 0)) {
		fprintf (stderr, "cannot ptrace %d\n", pid);
		return;
      }

      buffer_addr = find_buffers (apid);

      ptrace(PTRACE_DETACH, pid, 0, 0);
    }

  return 0;
}
