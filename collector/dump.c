/*
 * grubbing about in another process to dump its
 * buffers, and a suitable header etc.
 */
#include "common.h"

#include <sys/ptrace.h>
#include <sys/mman.h>
#include <sys/klog.h>
#include <sys/utsname.h>

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
	if (!maps)
		return ret;

	while (!result && fgets (buffer, 1024, maps)) {
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
	  
		log ("map 0x%lx -> 0x%lx size: %dk from '%s' '%s'\n",
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
					log ("pread error '%s'\n", strerror (errno));
					break;
				}
			}
			read_bytes += count;
		}
		log ("read %ld bytes of %ld\n", (long)read_bytes, (long)toread);

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

static DumpState *
open_pid (int pid)
{
	char name[1024];
	DumpState *s;

	if (ptrace (PTRACE_ATTACH, pid, 0, 0)) {
		log ("cannot ptrace %d\n", pid);
		return NULL;
	}

	snprintf (name, 1024, "/proc/%d/mem", pid);
	s = calloc (sizeof (DumpState), 1);
	s->pid = pid;
	s->mem = open (name, O_RDONLY|O_LARGEFILE);
	if (s->mem < 0) {
		log ("Failed to open memory map\n"); 
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
static int
close_pid (DumpState *s, int avoid_kill)
{
	int pid;

	/* Rather terminate the process then killing, less scary messages */
	if (!avoid_kill && kill(s->pid,SIGTERM))
		log ("failed to terminate pid %d: %s\n",
			 s->pid, strerror (errno));

	/* presumably dead by now - but detach anyway */
	ptrace (PTRACE_DETACH, s->pid, 0, 0);

	close (s->mem);
	pid = s->pid;
	free (s);

	return pid;
}

static void
close_wait_pid (DumpState *s, int avoid_kill)
{
	int i, pid;

	pid = close_pid (s, avoid_kill);
	/* 's' invalid */
	
	/* wait at most second max */
	for (i = 0; i < 100; i++) {
		char buffer[1024];
		sprintf (buffer, PROC_PATH "/%d/cmdline", pid);
		if (access (buffer, R_OK))
			break;
		usleep (10 * 1000);
	}
}

static void dump_buffers (DumpState *s)
{
	int i, max_chunk;
	size_t bytes_dumped = 0;

	/* if we wrapped around, the last chunk is probably unhelpful
	   to parse, due to dis-continuous data, discard it */
	max_chunk = MIN (s->map.max_chunk, sizeof (s->map.chunks)/sizeof(s->map.chunks[0]) - 1);
  
	log ("reading %d chunks (of %d) ... ", max_chunk, s->map.max_chunk);
	for (i = 0; i < max_chunk; i++) {
		FILE *output;
		char buffer[CHUNK_SIZE];
		Chunk *c = (Chunk *)&buffer;
		size_t addr = (size_t) s->map.chunks[i];

		pread (s->mem, &buffer, CHUNK_SIZE, addr);
		/*      log ("type: '%s' len %d\n",
			c->dest_stream, (int)c->length); */

		output = fopen (c->dest_stream, "a+");
		fwrite (c->data, 1, c->length, output);
		bytes_dumped += c->length;
		fclose (output);
	}
	log ("wrote %ld kb\n", (long)(bytes_dumped+1023)/1024);
}

/*
 * Used to find, extract and dump state from
 * a running bootchartd process.
 */
int
buffers_extract_and_dump (const char *output_path, Arguments *remote_args)
{
	int i, pid, ret = 0;
	DumpState *state;

	assert (chdir (output_path));

	pid = bootchart_find_running_pid (remote_args);
	if (pid < 0) {
		log ("Failed to find the collector's pid\n");
		return 1;
	}
	log ("Extracting profile data from pid %d\n", pid);

	/* the kernel for reasons of it's own really likes to return
	   ESRCH - No such process from pread randomly, so retry a bit */
	for (i = 0; i < 8; i++) {
		if (!(state = open_pid (pid)))
			return 1;

		if (find_chunks (state)) {
			ret = 1;
			log ("Couldn't find state structures on pid %d's stack%s\n",
				 pid, i < 7 ? ", retrying" : " aborting");
			close_pid (state, 1);
		} else {
			ret = 0;
			dump_buffers (state);
			close_wait_pid (state, 0);
			break;
		}
	}

	return ret;
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

	if (opt_args) {
		args = opt_args;
	} else {
		args = &sargs;
		arguments_set_defaults (args);
	}
    
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

		if ((len = readlink (exe_path, link_target, 1024-1)) < 0)
			continue;
		link_target[len] = '\0';

		if (strstr (link_target, PROGRAM_PREFIX "bootchart" PROGRAM_SUFFIX "-collector")) {
			FILE *argf;
			int harmless = 0;

			int p = atoi (ent->d_name);

			/*      log ("found collector '%s' pid %d (my pid %d)\n", link_target, p, getpid()); */

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
					int argc;
					char *argv[128];
					abuffer[len] = '\0';
					argv[0] = abuffer;
					for (argc = i = 0; i < len && argc < 127; i++) {
						if (abuffer[i] == '\0')
							argv[++argc] = abuffer + i + 1;
					}
					arguments_set_defaults (args);
					arguments_parse (args, argc, argv);

					if (args->usleep_time)
						harmless = 1;

				}
				fclose (argf);
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

/*
 * Dump kernel dmesg log for kernel init charting.
 */
int
dump_dmsg (const char *output_path)
{
	int size, i, count;
	char *logbuf = NULL;
	char fname[4096];
	FILE *dmesg;

	for (size = 256 * 1024;; size *= 2) {
		logbuf = (char *)realloc (logbuf, size);
		count = klogctl (3, logbuf, size);
		if (count < size - 1)
			break;
	}

	if (!count) {
		free(logbuf);
		log (" odd - no dmesg log data\n");
		return 1;
	}
	
	logbuf[count] = '\0';

	snprintf (fname, 4095, "%s/dmesg", output_path);
	dmesg = fopen (fname, "w");
	if (!dmesg) {
		free(logbuf);
		return 1;
	}

	for (i = 0; i < count; i++) {

		/* skip log level header '<2>...' eg. */
		while (i < count && logbuf[i] != '>') i++;
		i++;

		/* drop line to disk */
		while (i < count && logbuf[i - 1] != '\n')
			fputc (logbuf[i++], dmesg);
	}
	if (logbuf[count - 1] != '\n')
		fputs ("\n", dmesg);

	fclose (dmesg);
	free(logbuf);
	return 0;
}

/* sane ASCII chars only please */
static void
rewrite_ascii (char *string)
{
	char *p;
	for (p = string; *p; p++) {
		if (!isgraph (*p) && !isblank (*p))
			*p = '.';
	}
}

int
dump_header (const char *output_path)
{
	FILE *header;
	char fname[4096];

	if (output_path) {
		snprintf (fname, 4095, "%s/header", output_path);
		header = fopen (fname, "w");
	} else
		header = stdout;

	if (!header)
		return 1;

	fprintf (header, "version = " VERSION "\n");

	{
		time_t now;
		char host_buf[4096] = { '\0' };
		char domain_buf[2048] = { '\0' };
		char time_buf[128];

		if (!gethostname (host_buf, 2047) &&
		    !getdomainname (domain_buf, 2048)) {
			if (strlen (domain_buf)) {
				strcat (host_buf, ".");
				strcat (host_buf, domain_buf);
			}
		} else
			strcpy (host_buf, "unknown");

		rewrite_ascii (host_buf);

		now = time (NULL);
		ctime_r (&now, time_buf);
		if (strrchr (time_buf, '\n'))
			*strrchr (time_buf, '\n') = '\0';

		fprintf (header, "title = Boot chart for %s (%s)\n", host_buf, time_buf);
	}

	{
		struct utsname ubuf;
		if (!uname (&ubuf))
			fprintf (header, "system.uname = %s %s %s %s\n",
				 ubuf.sysname, ubuf.release, ubuf.version, ubuf.machine);
	}
	{
		FILE *lsb;
		char release[4096] = "";

		lsb = popen ("lsb_release -sd", "r");
		if (lsb && fgets (release, 4096, lsb)) {
			if (release[0] == '"')
				memmove (release, release + 1, strlen (release + 1));
			if (strrchr (release, '"'))
				*strrchr (release, '"') = '\0';
		} else
			release[0] = '\0';
		fprintf (header, "system.release = %s\n", release);
		if (lsb)
			pclose (lsb);
	}

	{
		FILE *cpuinfo = fopen ("/proc/cpuinfo", "r");
		FILE *cpuinfo_dump;
		char fname[4096];
		char line[4096];
		char cpu_model[4096] = {'\0'};
		char cpu_model_alt[4096] = {'\0'};
		char *cpu_m = cpu_model;
		int  cpus = 0;

		sprintf (fname, "%s/proc_cpuinfo.log", output_path);
		cpuinfo_dump = fopen(fname, "w");

		/* Dump /proc/cpuinfo for easier debugging with unexpected formats */
		while (cpuinfo && fgets (line, 4096, cpuinfo)) {
			if (!strncmp (line, "model name", 10) && strchr (line, ':'))
				strcpy (cpu_model, strstr (line, ": ") + 2);
			/* ARM platforms save cpu model on Processor field so try to get it */
			if (!strncasecmp (line, "processor", 9)) {
				cpus++;
				strcpy (cpu_model_alt, strstr (line, ": ") + 2);
			}
			if (cpuinfo_dump)
				fprintf(cpuinfo_dump, "%s", line);
		}
		if (cpuinfo)
			fclose (cpuinfo);
		if (cpuinfo_dump)
			fclose(cpuinfo_dump);
		if (!cpu_model[0])
			cpu_m = cpu_model_alt;
		if (strrchr (cpu_m, '\n'))
			*strrchr (cpu_m, '\n') = '\0';
		fprintf (header, "system.cpu = %s %d\n", cpu_m, cpus);
		fprintf (header, "system.cpu.num = %d\n", cpus);
	}
	{
		FILE *cmdline = fopen ("/proc/cmdline", "r");
		if (cmdline) {
			char line [4096] = "";
			assert (NULL != fgets (line, 4096, cmdline));
			fprintf (header, "system.kernel.options = %s", line);
			fclose (cmdline);
		}
	}
	{
		fflush (header);
		int maxpid = fork();
		if (!maxpid) _exit(0);
		fprintf (header, "system.maxpid = %d\n", maxpid);
	}

	if (header != stdout)
		fclose (header);
	return 0;
}
