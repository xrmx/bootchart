#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <glib.h>

#define BUFFER_SIZE (1024 * 1024 * 64)
typedef long long addr_t;

typedef struct {
  char    magic[8];
  long    length;
  Header *next;
  char    data[1];
} Header;

typedef struct {
  int mem;
  GList *buffers;
} ProcessData;

static ProcessData *find_buffers (const char *apid)
{
  FILE *file;
  int  mem;
  char buffer[4096];
  char *name;
  addr_t result = 0;

  mem = open ((name = g_strdup_printf ("/proc/%s/mem", apid)), 0);
  g_free (name);
  if (mem < 0)
    {
      fprintf (stderr, "Failed to open memory map\n"); 
      return 0;
    }
  maps = fopen ((name = g_strdup_printf ("/proc/%s/maps", apid)), "r");
  g_free (name);

  mem = open (mem, "r");
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
	      addr_t start = strtoll (elems[0], NULL, 0x10);
	      addr_t end = strtoll (p + 1, NULL, 0x10);
	      fprintf (stderr, "map 0x%llx -> 0x%llx size: %dk\n", start, end,
		       (end - start) / 1024);
	      lseek (mem, start, SEEK_SET);
	      read (header, 
	    }
	}
      g_strfreev (elems);
    }
  fclose (maps);
  fclose (mem);

  return result;
}

int main (int argc, char **argv)
{
  volatile Header *data;
  if (argc <= 1)
    {
      fprintf (stderr, "server\n");
      data = g_malloc0 (BUFFER_SIZE);
      strcpy (data->magic, "buf-data");
      strcpy (data->data, "this is an long essay packed with fun!");
      while ((data[0] == 't'))
	{
	  g_usleep (1000*500);
	}
    }
  else
    {
      const char *apid;
      gulong buffer_addr;

      apid = argv[argc-1];
      fprintf (stderr, "attach to pid %s\n", apid);

      buffer_addr = find_buffers (apid);
    }

  return 0;
}
