/* bootchart-collector
 *
 * Copyright © 2009 Canonical Ltd.
 * Author: Scott James Remnant <scott@netsplit.com>.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3 of the License.

 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.

 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

/*
 * Copyright 2009 Novell, Inc.
 * 
 * URK ! - GPLv2 - code from Linux kernel.
 */

/* getdelays.c
 *
 * Utility to get per-pid and per-tgid delay accounting statistics
 * Also illustrates usage of the taskstats interface
 *
 * Copyright (C) Shailabh Nagar, IBM Corp. 2005
 * Copyright (C) Balbir Singh, IBM Corp. 2006
 * Copyright (c) Jay Lan, SGI. 2006
 */

#include <sys/time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/select.h>
#include <sys/resource.h>
#include <sys/socket.h>

#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <assert.h>
#include <dirent.h>
#include <limits.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ctype.h>

#include <linux/genetlink.h>
#include <linux/taskstats.h>
#include <linux/cgroupstats.h>

#undef HAVE_IO_PRIO
#if defined(__i386__)
#  define HAVE_IO_PRIO
#  define __NR_ioprio_set 289
#elif defined(__x86_64__)
#  define HAVE_IO_PRIO
#  define __NR_ioprio_set 251
#elif defined(__powerpc__)
#  define HAVE_IO_PRIO
#  define __NR_ioprio_set 273
#else /* not fatal */
#  warning "Architecture does not support ioprio modification"
#endif
#define IOPRIO_WHO_PROCESS 1
#define IOPRIO_CLASS_RT 1
#define IOPRIO_CLASS_SHIFT 13
#define IOPRIO_RT_HIGHEST  (0 | (IOPRIO_CLASS_RT << IOPRIO_CLASS_SHIFT))

const char *proc_path;

/* if we are running vs. a high prio I/O process we still want logging */
void
set_io_prio (void)
{
#ifdef HAVE_IO_PRIO
	if (syscall(__NR_ioprio_set, IOPRIO_WHO_PROCESS, 0, IOPRIO_RT_HIGHEST) == -1)
		perror("Can not set IO priority to top priority");
#endif
}

#define BUFSIZE 524288

typedef struct {
	pid_t pid;
	pid_t ppid;
	__u64 time_total;
} PidEntry;

static PidEntry *
get_pid_entry (pid_t pid)
{
	static PidEntry *pids = NULL;
	static pid_t     pids_size = 0;

	pid_t old_pids_size = pids_size;
	if (pid >= pids_size) {
		pids_size = pid + 512;
		pids = realloc (pids, sizeof (PidEntry) * pids_size);
		memset (pids + old_pids_size, 0, sizeof (PidEntry) * (pids_size - old_pids_size));
	}
	return pids + pid;
}

typedef struct {
	int    fd;
	char   data[BUFSIZE];
	size_t len;
} BufferFile;

static BufferFile *
buffer_file_new (const char *output_dir, const char *output_fname)
{
	int fd;
	char *fname;
	BufferFile *file;

	fname = malloc (strlen (output_dir) + 1 + strlen (output_fname) + 1);
	if (!fname)
		return NULL;

	strcpy (fname, output_dir);
	strcat (fname, "/");
	strcat (fname, output_fname);

	if ((fd = open (fname, O_WRONLY | O_CREAT | O_TRUNC, 0644)) < 0) {
		fprintf (stderr, "Error opening output file '%s': %s",
			 fname, strerror (errno));
		free (fname);
		return NULL;
	}
	free (fname);

	file = malloc (sizeof (BufferFile));
	if (!file)
		return NULL;

	file->len = 0;
	file->fd = fd;

	return file;
}

static void
buffer_file_flush (BufferFile *file)
{
	size_t writelen = 0;

	while (writelen < file->len) {
		ssize_t len;

		len = write (file->fd, file->data + writelen, file->len - writelen);
		if (len < 0) {
			perror ("write");
			exit (1);
		}

		writelen += len;
	}

	file->len = 0;
}

static void
buffer_file_append (BufferFile *file, const char *str, size_t len)
{
	assert (len <= BUFSIZE);

	if (file->len + len > BUFSIZE)
		buffer_file_flush (file);

	memcpy (file->data + file->len, str, len);
	file->len += len;
}

/* dump whole contents of input_fd to the output 'file' */
static void
buffer_file_dump (BufferFile *file, int input_fd)
{
	for (;;) {
		ssize_t len;

		if (file->len >= BUFSIZE)
			buffer_file_flush (file);

		len = read (input_fd, file->data + file->len, BUFSIZE - file->len);
		if (len < 0) {
			perror ("read error");
			return;
		} else if (len == 0)
			break;

		file->len += len;
	}
}

static void
buffer_file_dump_frame_with_timestamp (BufferFile *file, int input_fd,
				       const char *uptime, size_t uptimelen)
{
	buffer_file_append (file, uptime, uptimelen);

	lseek (input_fd, SEEK_SET, 0);
	buffer_file_dump (file, input_fd);

	buffer_file_append (file, "\n", 1);
}

static void
buffer_file_close (BufferFile *file)
{
  buffer_file_flush (file);
  if (close (file->fd) < 0)
	perror ("closing output file");
  free (file);
}

unsigned long get_uptime (int fd);
void sig_handler (int signum);

/* Netlink socket-set bits */
static int   netlink_socket = -1;
static __u16 netlink_taskstats_id;

#define GENLMSG_DATA(glh)	((void *)(NLMSG_DATA(glh) + GENL_HDRLEN))
#define GENLMSG_PAYLOAD(glh)	(NLMSG_PAYLOAD(glh, 0) - GENL_HDRLEN)
#define NLA_DATA(na)		((void *)((char*)(na) + NLA_HDRLEN))
#define NLA_PAYLOAD(len)	(len - NLA_HDRLEN)

/* Maximum size of response requested or message sent */
#define MAX_MSG_SIZE	1024

struct msgtemplate {
	struct nlmsghdr n;
	struct genlmsghdr g;
	char buf[MAX_MSG_SIZE];
};

extern int dbg;
#define PRINTF(fmt, arg...) {			\
    fprintf(stderr, fmt, ##arg);			\
	}

static int send_cmd(int sd, __u16 nlmsg_type, __u32 nlmsg_pid,
	     __u8 genl_cmd, __u16 nla_type,
	     void *nla_data, int nla_len)
{
	struct nlattr *na;
	struct sockaddr_nl nladdr;
	int r, buflen;
	char *buf;

	struct msgtemplate msg = { { 0, } };

	msg.n.nlmsg_len = NLMSG_LENGTH(GENL_HDRLEN);
	msg.n.nlmsg_type = nlmsg_type;
	msg.n.nlmsg_flags = NLM_F_REQUEST;
	msg.n.nlmsg_seq = 0;
	msg.n.nlmsg_pid = nlmsg_pid;
	msg.g.cmd = genl_cmd;
	msg.g.version = 0x1;
	na = (struct nlattr *) GENLMSG_DATA(&msg);
	na->nla_type = nla_type;
	na->nla_len = nla_len + 1 + NLA_HDRLEN;
	memcpy(NLA_DATA(na), nla_data, nla_len);
	msg.n.nlmsg_len += NLMSG_ALIGN(na->nla_len);

	buf = (char *) &msg;
	buflen = msg.n.nlmsg_len ;
	memset(&nladdr, 0, sizeof(nladdr));
	nladdr.nl_family = AF_NETLINK;
	while ((r = sendto(sd, buf, buflen, 0, (struct sockaddr *) &nladdr,
			   sizeof(nladdr))) < buflen) {
		if (r > 0) {
			buf += r;
			buflen -= r;
		} else if (errno != EAGAIN)
			return -1;
	}
	return 0;
}

static struct taskstats *
wait_taskstats (void)
{
  static struct msgtemplate msg;
  int rep_len;

  for (;;) {

    while ((rep_len = recv(netlink_socket, &msg, sizeof(msg), 0)) < 0 && errno == EINTR);
  
    if (msg.n.nlmsg_type == NLMSG_ERROR ||
	!NLMSG_OK((&msg.n), rep_len)) {
      /* process died before we got to it or somesuch */
      /* struct nlmsgerr *err = NLMSG_DATA(&msg);
	 fprintf (stderr, "fatal reply error,  errno %d\n", err->error); */
      return NULL;
    }
  
    int rep_len = GENLMSG_PAYLOAD(&msg.n);
    struct nlattr *na = (struct nlattr *) GENLMSG_DATA(&msg);
    int len = 0;
  
    while (len < rep_len) {
      len += NLA_ALIGN(na->nla_len);
      switch (na->nla_type) {
      case TASKSTATS_TYPE_AGGR_PID:
	{
	  int aggr_len = NLA_PAYLOAD(na->nla_len);
	  int len2 = 0;

	  /* For nested attributes, na follows */
	  na = (struct nlattr *) NLA_DATA(na);

	  /* find the record we care about */
	  while (na->nla_type != TASKSTATS_TYPE_STATS) {
	    len2 += NLA_ALIGN(na->nla_len);

	    if (len2 >= aggr_len)
	      goto next_attr;
	    na = (struct nlattr *) ((char *) na + len2);
	  }
	  return (struct taskstats *) NLA_DATA(na);
	}
      }
    next_attr:
      na = (struct nlattr *) (GENLMSG_DATA(&msg) + len);
    }
  }
  return NULL;
}

/*
 * Unfortunately the TGID stuff doesn't work at all well
 * in the kernel - we have to manually aggregate here.
 */
static struct taskstats *
get_taskstats (pid_t pid)
{
	struct taskstats *ts;

	/* set_pid */
	int rc = send_cmd (netlink_socket, netlink_taskstats_id, 0,
			   TASKSTATS_CMD_GET, TASKSTATS_CMD_ATTR_PID,
			   &pid, sizeof(__u32));

	if (rc < 0)
		return NULL;
	;

	/* get reply */
	ts = wait_taskstats ();
		    
	if (!ts)
		return NULL;

	if (ts->ac_pid != pid) {
		fprintf (stderr, "Serious error got data for wrong pid: %d %d\n",
			 (int)ts->ac_pid, (int)pid);
		return NULL;
	}

	return ts;
}

/*
 * Unfortunately the TGID stuff doesn't work at all well
 * in the kernel - we have to manually aggregate here.
 */
static struct taskstats *
get_tgid_taskstats (pid_t pid)
{
	DIR *tdir;
	struct dirent *tent;
	struct taskstats *ts;
	static struct taskstats tgits;
	char proc_task_buffer[1024];

	memset (&tgits, 0, sizeof (struct taskstats));

	ts = get_taskstats (pid);
	if (!ts)
		return NULL;

	tgits = *ts;

	snprintf (proc_task_buffer, 1023, "%s/%d/task", proc_path, pid);
	tdir = opendir (proc_task_buffer);
	if (!tdir)
		return &tgits;

	while ((tent = readdir (tdir)) != NULL) {
		pid_t tpid;
		if (!isdigit (tent->d_name[0]))
			continue;
		tpid = atoi (tent->d_name);
		if (pid != tpid) {
			struct taskstats *ts = get_taskstats (tpid);

			if (!ts)
				continue;

			/* aggregate */
			tgits.cpu_run_real_total += ts->cpu_run_real_total;
			tgits.swapin_delay_total += ts->swapin_delay_total;
			tgits.blkio_delay_total += ts->blkio_delay_total;
		}
	}
	return &tgits;
}

/*
 * Linux exports one set of quite good data in:
 *   /proc/./stat: linux/fs/proc/array.c (do_task_stat)
 * and another high-res (but different) set of data in:
 *   linux/kernel/tsacct.c
 *   linux/kernel/delayacct.c // needs delay accounting enabled
 */
static void
dump_taskstat (BufferFile *file, pid_t pid)
{
	int output_len;
	char output_line[1024];
	PidEntry *entry;
	__u64 time_total;
	struct taskstats *ts;
	
	ts = get_tgid_taskstats (pid);

	if (!ts) /* process exited before we got there */
		return;

	/* reduce the amount of parsing we have to do later */
	entry = get_pid_entry (ts->ac_pid);
	time_total = (ts->cpu_run_real_total + ts->blkio_delay_total +
		      ts->swapin_delay_total);
	if (entry->time_total == time_total && entry->ppid == ts->ac_ppid)
		return;
	entry->time_total = time_total;
	entry->ppid = ts->ac_ppid;

	/* NB. ensure we aggregate all fields we need in get_tgid_tasstats */
	output_len = snprintf (output_line, 1024, "%d %d %s %lld %lld %lld\n",
			       ts->ac_pid, ts->ac_ppid, ts->ac_comm,
			       (long long)ts->cpu_run_real_total,
			       (long long)ts->blkio_delay_total,
			       (long long)ts->swapin_delay_total);
	if (output_len < 0)
		return;

//	fprintf (stderr, "%s", output_line);
	buffer_file_append (file, output_line, output_len);

	// FIXME - can we get better stats on what is waiting for what ?
	// 'blkio_count / blkio_delay_total' ... [etc.]
	// 'delay waiting for CPU while runnable' ... [!] fun :-)
		
	/* The data we get from /proc is: */
	/*
	  opid, cmd, state, ppid = float(tokens[0]), ' '.join(tokens[1:2+offset]), tokens[2+offset], int(tokens[3+offset])
	  userCpu, sysCpu, stime= int(tokens[13+offset]), int(tokens[14+offset]), int(tokens[21+offset]) */
		
	/* opid - our pid - ac_pid easy */
	/* cmd - easy */
	/* synthetic state ? ... - can we get something better ? */
	/* 'state' - 'S' or ... */
	/* instead we really want the I/O delay rendered I think */
	/* Grief - how reliable & rapidly updated is the "state" information ? */
//		+ ho hum ! + - the big flaw ?
	/* ppid - parent pid - ac_ppid easy */
	/* userCpu, sysCPU - we can only get the sum of these: cpu_run_real_total in ns */
	/* though we could - approximate this with ac_utime / ac_stime in 'usec' */
	/* just output 0 for sysCPU ? */
	/* 'stime' - nothing doing ... - no start time data here ... */
}
		
static void
dump_proc (BufferFile *file, const char *name)
{
	int  fd;
	char filename[PATH_MAX];

	sprintf (filename, "%s/%s/stat", proc_path, name);

	fd = open (filename, O_RDONLY);
	if (fd < 0)
		return;
	
	buffer_file_dump (file, fd);

	close (fd);
}

unsigned long
get_uptime (int fd)
{
	char          buf[80];
	ssize_t       len;
	unsigned long u1, u2;

	lseek (fd, SEEK_SET, 0);

	len = read (fd, buf, sizeof buf);
	if (len < 0) {
		perror ("read");
		return 0;
	}

	buf[len] = '\0';

	if (sscanf (buf, "%lu.%lu", &u1, &u2) != 2) {
		perror ("sscanf");
		return 0;
	}

	return u1 * 100 + u2;
}


void
sig_handler (int signum)
{
}

/*
 * Probe the controller in genetlink to find the family id
 * for the TASKSTATS family
 */
static int get_family_id(int sd)
{
	struct {
		struct nlmsghdr n;
		struct genlmsghdr g;
		char buf[256];
	} ans;

	int id = 0, rc;
	struct nlattr *na;
	int rep_len;

        char name[100];
	strcpy(name, TASKSTATS_GENL_NAME);
	rc = send_cmd (sd, GENL_ID_CTRL, getpid(), CTRL_CMD_GETFAMILY,
			CTRL_ATTR_FAMILY_NAME, (void *)name,
			strlen(TASKSTATS_GENL_NAME)+1);

	rep_len = recv(sd, &ans, sizeof(ans), 0);
	if (ans.n.nlmsg_type == NLMSG_ERROR ||
	    (rep_len < 0) || !NLMSG_OK((&ans.n), rep_len))
		return 0;

	na = (struct nlattr *) GENLMSG_DATA(&ans);
	na = (struct nlattr *) ((char *) na + NLA_ALIGN(na->nla_len));
	if (na->nla_type == CTRL_ATTR_FAMILY_ID) {
		id = *(__u16 *) NLA_DATA(na);
	}
	return id;
}

int
init_taskstat (void)
{
	struct sockaddr_nl addr;

	netlink_socket = socket(AF_NETLINK, SOCK_RAW, NETLINK_GENERIC);
	if (netlink_socket < 0)
		goto error;

	memset (&addr, 0, sizeof (addr));
	addr.nl_family = AF_NETLINK;

	if (bind (netlink_socket, (struct sockaddr *) &addr, sizeof (addr)) < 0)
		goto error;

	netlink_taskstats_id = get_family_id (netlink_socket);

	return 1;
error:
	if (netlink_socket >= 0)
		close (netlink_socket);

	return 0;
}

static void
usage ()
{
	fprintf (stderr, "Usage: bootchart-collector [-r] [-p /proc/path] [-o /output/path] HZ\n");
	exit (1);
}

int
main (int   argc,
      char *argv[])
{
	struct sigaction  act;
	sigset_t          mask, oldmask;
	struct rlimit     rlim;
	struct timespec   timeout;
	const char       *output_dir;
	const char       *hz_string;
	int               stat_fd, disk_fd, uptime_fd;
	DIR              *proc;
	BufferFile       *stat_file, *disk_file;
	BufferFile       *per_pid_file;
	unsigned long     reltime = 0;
	int               rel, i;
	int		  use_taskstat;
	int               *fds[] = {
		&stat_fd, &disk_fd, &uptime_fd, NULL
	};
	const char *fd_names[] = {
		"/stat", "/diskstats", "/uptime", NULL
	};

	/* defaults */
	rel = 0;
	proc_path = "/proc";
	output_dir = ".";
	hz_string = "10";

	for (i = 1; i < argc; i++) {
		if (!argv[i]) continue;
		if (argv[i][0] == '-') {
			switch (argv[i][1]) {
			case 'r':
				rel = 1;
				break;
			case 'o':
				if (i < argc - 1)
					output_dir = argv[++i];
				else {
					fprintf (stderr, "Error: -o takes a directory argument\n");
					usage();
				}
				break;
			case 'p':
				if (i < argc - 1)
					proc_path = argv[++i];
				else {
					fprintf (stderr, "Error: -p takes a proc mount-point path\n");
					usage();
				}
				break;
			default:
				fprintf (stderr, "Error: unknown option '%s'\n", argv[i]);
				usage();
				break;
			}
		} else
			hz_string = argv[i];
	}

	{
		unsigned long  hz;
		char          *endptr;

		hz = strtoul (hz_string, &endptr, 10);
		if (*endptr) {
			fprintf (stderr, "%s: HZ not an integer\n", argv[0]);
			exit (1);
		}

		if (hz > 1) {
			timeout.tv_sec = 0;
			timeout.tv_nsec = 1000000000 / hz;
		} else {
			timeout.tv_sec = 1;
			timeout.tv_nsec = 0;
		}
	}

	sigemptyset (&mask);
	sigaddset (&mask, SIGTERM);
	sigaddset (&mask, SIGINT);

	if (sigprocmask (SIG_BLOCK, &mask, &oldmask) < 0) {
		perror ("sigprocmask");
		exit (1);
	}

	act.sa_handler = sig_handler;
	act.sa_flags = 0;
	sigemptyset (&act.sa_mask);

	if (sigaction (SIGTERM, &act, NULL) < 0) {
		perror ("sigaction SIGTERM");
		exit (1);
	}

	if (sigaction (SIGINT, &act, NULL) < 0) {
		perror ("sigaction SIGINT");
		exit (1);
	}

	/* Drop cores if we go wrong */
	//	if (chdir ("/"))
	//		;

	rlim.rlim_cur = RLIM_INFINITY;
	rlim.rlim_max = RLIM_INFINITY;

	setrlimit (RLIMIT_CORE, &rlim);
	set_io_prio ();

	proc = opendir (proc_path);
	if (! proc) {
		perror ("opendir proc");
		exit (1);
	}

	for (i = 0; fds [i]; i++) {
		char *path = malloc (strlen (proc_path) + strlen (fd_names[i]) + 1);
		strcpy (path, proc_path);
		strcat (path, fd_names[i]);

		*fds[i] = open (path, O_RDONLY);
		if (*fds[i] < 0) {
			fprintf (stderr, "error opening '%s': %s'\n",
				 path, strerror (errno));
			exit (1);
		}
	}

	stat_file = buffer_file_new (output_dir, "proc_stat.log");
	disk_file = buffer_file_new (output_dir, "proc_diskstats.log");
	if ( (use_taskstat = init_taskstat()) )
		per_pid_file = buffer_file_new (output_dir, "taskstats.log");
	else
		per_pid_file = buffer_file_new (output_dir, "proc_ps.log");

	if (!stat_file || !disk_file || !per_pid_file) {
		fprintf (stderr, "Error opening an output file");
		exit (1);
	}

	if (rel) {
		reltime = get_uptime (uptime_fd);
		if (! reltime)
			exit (1);
	}

	for (;;) {
		char          uptime[80];
		size_t        uptimelen;
		unsigned long u;
		struct dirent *ent;

		u = get_uptime (uptime_fd);
		if (! u)
			exit (1);

		uptimelen = sprintf (uptime, "%lu\n", u - reltime);

		buffer_file_dump_frame_with_timestamp (stat_file, stat_fd,
						       uptime, uptimelen);
		buffer_file_dump_frame_with_timestamp (disk_file, disk_fd,
						       uptime, uptimelen);

		/* output data for each pid */
		buffer_file_append (per_pid_file, uptime, uptimelen);

		rewinddir (proc);
		while ((ent = readdir (proc)) != NULL) {
			if (!isdigit (ent->d_name[0]))
				continue;

			if (use_taskstat) {
				pid_t pid = atoi (ent->d_name);
				dump_taskstat (per_pid_file, pid);
			} else
				dump_proc (per_pid_file, ent->d_name);
		}
		buffer_file_append (per_pid_file, "\n", 1);

		if (pselect (0, NULL, NULL, NULL, &timeout, &oldmask) < 0) {
			if (errno == EINTR) {
				break;
			} else {
				perror ("pselect");
				exit (1);
			}
		}
	}

	buffer_file_close (stat_file);
	buffer_file_close (disk_file);

	if (use_taskstat) {
		if (close (netlink_socket) < 0) {
			perror ("failed to close netlink socket");
			exit (1);
		}
	}
	buffer_file_close (per_pid_file);

	for (i = 0; fds [i]; i++) {
		if (close (*fds[i]) < 0) {
			fprintf (stderr, "error closing file '%s': %s'\n",
				 fd_names[i], strerror (errno));
			exit (1);
		}
	}

	if (closedir (proc) < 0) {
		perror ("close /proc");
		exit (1);
	}

	return 0;
}
