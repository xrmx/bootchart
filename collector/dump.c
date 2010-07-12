/*
 * grubbing about in another process to dump its
 * buffers, and a suitable header etc.
 */
#include "common.h"

#include <sys/ptrace.h>
#include <sys/mman.h>


typedef struct {
	int pid;
	int mem;
	StackMap map;
} DumpState;

static StackMap *
search_stack (char *stack, size_t len)
{
	char *p;
	for (p = stack; p < stack + len; p++) {
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

	while (!result && fgets (buffer, 4096, maps)) {
		char *p, *copy;
		size_t start, end, toread, read_bytes;

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
			 (long) start, (long)end, (int)(end - start) / 1024,
			 buffer, p + 1);

		toread = end - start;
		copy = malloc (toread);
		for (read_bytes = 0; read_bytes < toread;) {
			ssize_t count = pread (s->mem, copy + read_bytes, toread, start);
			if (count < 0) {
				if (errno == EINTR || errno == EAGAIN)
					continue;
				else {
					fprintf (stderr, "Error '%s'\n", strerror (errno));
					break;
				}
			}
			read_bytes += count;
		}
		fprintf (stderr, "read %ld bytes of %ld\n", (long)read_bytes, (long)toread);

		map = search_stack (copy, read_bytes);
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

	if (ptrace (PTRACE_ATTACH, pid, 0, 0)) {
		fprintf (stderr, "cannot ptrace %d\n", pid);
		return NULL;
	}

	snprintf (name, 1024, "/proc/%d/mem", pid);
	s = calloc (sizeof (DumpState), 1);
	s->pid = pid;
	s->mem = open (name, O_RDONLY|O_LARGEFILE);
	if (s->mem < 0) {
		fprintf (stderr, "Failed to open memory map\n"); 
		free (s);
		return NULL;
	}

	return s;
}

/*
 * stop ptracing the process, kill it, and
 * wait a while hoping it exits (so we can
 * cleanup after it).
 */
static void close_wait_pid (DumpState *s)
{
	int i;

	ptrace (PTRACE_KILL, s->pid, 0, 0);
	ptrace (PTRACE_DETACH, s->pid, 0, 0);
	close (s->mem);

	/* wait at most second max */
	for (i = 0; i < 100; i++) {
		char buffer[1024];
		sprintf (buffer, PROC_PATH "/%d/cmdline", s->pid);
		if (access (buffer, R_OK))
			break;
		usleep (10 * 1000);
	}

	free (s);
}

static void dump_buffers (DumpState *s)
{
	int i, max_chunk;
	size_t bytes_dumped = 0;

	/* if we wrapped around, the last chunk is probably unhelpful
	   to parse, due to dis-continuous data, discard it */
	max_chunk = MIN (s->map.max_chunk, sizeof (s->map.chunks)/sizeof(s->map.chunks[0]) - 1);
  
	fprintf (stderr, "reading %d chunks (of %d) ... ", max_chunk, s->map.max_chunk);
	for (i = 0; i < max_chunk; i++) {
		FILE *output;
		char buffer[CHUNK_SIZE];
		Chunk *c = (Chunk *)&buffer;
		size_t addr = (size_t) s->map.chunks[i];

		pread (s->mem, &buffer, CHUNK_SIZE, addr);
		/*      fprintf (stderr, "type: '%s' len %d\n",
			c->dest_stream, (int)c->length); */

		output = fopen (c->dest_stream, "a+");
		fwrite (c->data, 1, c->length, output);
		bytes_dumped += c->length;
		fclose (output);
	}
	fprintf (stderr, "wrote %ld kb\n", (long)(bytes_dumped+1023)/1024);
}

/*
 * Used to find, extract and dump state from
 * a running bootchartd process.
 */
int
buffers_extract_and_dump (const char *output_path)
{
	int pid, ret = 1;
	DumpState *state;
	Arguments  args;

	chdir (output_path);

	pid = bootchart_find_running_pid (&args);
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

	close_wait_pid (state);

	return 0;
}

/*
 * finds (another) bootchart-collector process and
 * returns it's pid (or -1) if not found, ignores
 * the --usleep mode we use to simplify our scripts.
 */
int
bootchart_find_running_pid (Arguments *opt_args)
{
	DIR *proc;
	struct dirent *ent;
	int pid = -1;
	char exe_path[1024];
	Arguments sargs, *args;

	if (opt_args)
		args = opt_args;
	else
		args = &sargs;
    
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
			FILE *argf;
			int harmless = 0;

			int p = atoi (ent->d_name);

			/*      fprintf (stderr, "found collector '%s' pid %d (my pid %d)\n", link_target, p, getpid()); */

			if (p == getpid())
				continue; /* I'm not novel */

			strcpy (exe_path + strlen (exe_path) - strlen ("/exe"), "/cmdline");
			argf = fopen (exe_path, "r");
			if (argf) {
				int i;
				char abuffer[4096];

				len = fread (abuffer, 1, 4095, argf);
				if (len > 0) {
					/* step through args */
					abuffer[len] = '\0';
					int argc;
					char *argv[128];
					argv[0] = abuffer;
					for (argc = i = 0; i < len && argc < 127; i++) {
						if (abuffer[i] == '\0')
							argv[++argc] = abuffer + i + 1;
					}
					arguments_set_defaults (args);
					arguments_parse (args, argc, argv);

					if (args->usleep_time)
						harmless = 1;

					fclose (argf);
				}
			}

			if (!harmless) {
				pid = p;
				break;
			}
		}
	}
	closedir (proc);

	if (args == &sargs)
		arguments_free (&sargs);

	return pid;
}
