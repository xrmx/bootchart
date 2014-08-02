/*
 * bootchart-collector - collection framework.
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
 * inspired by Scott James Remnant <scott@netsplit.com>'s work.
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

#include "common.h"

#include <sys/mount.h>
#include <linux/fs.h>
#include <linux/genetlink.h>
#include <linux/taskstats.h>
#include <linux/cgroupstats.h>
#include <signal.h>

/* pid uniqifying code */
typedef struct {
	pid_t pid;
	pid_t ppid;
	__u64 time_total;
} PidEntry;

static inline PidEntry *
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
		while ((rep_len = recv (netlink_socket, &msg, sizeof(msg), 0)) < 0 && errno == EINTR);
  
		if (msg.n.nlmsg_type == NLMSG_ERROR ||
		    !NLMSG_OK((&msg.n), rep_len)) {
			/* process died before we got to it or somesuch */
			/* struct nlmsgerr *err = NLMSG_DATA(&msg);
			   log ("fatal reply error,  errno %d\n", err->error); */
			return NULL;
		}
  
		rep_len = GENLMSG_PAYLOAD(&msg.n);
		struct nlattr *na = (struct nlattr *) GENLMSG_DATA(&msg);
		int len = 0;
		
		while (len < rep_len) {
			len += NLA_ALIGN(na->nla_len);
			switch (na->nla_type) {
			case TASKSTATS_TYPE_AGGR_PID: {
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

	/* get reply */
	ts = wait_taskstats ();
		    
	if (!ts)
		return NULL;

	if (ts->ac_pid != pid) {
		log ("Serious error got data for wrong pid: %d %d\n",
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
get_tgid_taskstats (PidScanner *scanner)
{
	pid_t tpid;
	struct taskstats *ts;
	static struct taskstats tgits;

	memset (&tgits, 0, sizeof (struct taskstats));

	ts = get_taskstats (pid_scanner_get_cur_pid (scanner));
	if (!ts)
		return NULL;

	tgits = *ts;

	pid_scanner_get_tasks_start (scanner);
	while ((tpid = pid_scanner_get_tasks_next (scanner))) {
		struct taskstats *ts = get_taskstats (tpid);

		if (!ts)
			continue;

/*		log ("CPU aggregate %d: %ld\n", tpid, (long) ts->cpu_run_real_total); */

		/* aggregate */
		tgits.cpu_run_real_total += ts->cpu_run_real_total;
		tgits.swapin_delay_total += ts->swapin_delay_total;
		tgits.blkio_delay_total += ts->blkio_delay_total;
	}
	pid_scanner_get_tasks_stop (scanner);

	return &tgits;
}

/*
 * Linux exports one set of quite good data in:
 *   /proc/./stat: linux/fs/proc/array.c (do_task_stat)
 * and another high-res (but different) set of data in:
 *   linux/kernel/tsacct.c
 *   linux/kernel/delayacct.c - needs delay accounting enabled
 */
static void
dump_taskstat (BufferFile *file, PidScanner *scanner)
{
	pid_t ppid;
	int output_len;
	char output_line[1024];
	PidEntry *entry;
	__u64 time_total;
	struct taskstats *ts;
	
	ts = get_tgid_taskstats (scanner);
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

	/* we can get a much cleaner ppid from PROC_EVENTS */
	ppid = pid_scanner_get_cur_ppid (scanner);
	if (!ppid)
		ppid = ts->ac_ppid;

	/* NB. ensure we aggregate all fields we need in get_tgid_tasstats */
	output_len = snprintf (output_line, 1024, "%d %d %s %lld %lld %lld\n",
			       ts->ac_pid, ppid, ts->ac_comm,
			       (long long)ts->cpu_run_real_total,
			       (long long)ts->blkio_delay_total,
			       (long long)ts->swapin_delay_total);
	if (output_len < 0)
		return;

	buffer_file_append (file, output_line, output_len);

/*	   FIXME - can we get better stats on what is waiting for what ?
	   'blkio_count / blkio_delay_total' ... [etc.]
	   'delay waiting for CPU while runnable' ... [!] fun :-) */
		
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
/*		+ ho hum ! + - the big flaw ? */
	/* ppid - parent pid - ac_ppid easy */
	/* userCpu, sysCPU - we can only get the sum of these: cpu_run_real_total in ns */
	/* though we could - approximate this with ac_utime / ac_stime in 'usec' */
	/* just output 0 for sysCPU ? */
	/* 'stime' - nothing doing ... - no start time data here ... */
}
		
static void
dump_proc_stat (BufferFile *file, int pid)
{
	int  fd;
	char filename[PATH_MAX];

	sprintf (filename, PROC_PATH "/%d/stat", pid);

	fd = open (filename, O_RDONLY);
	if (fd < 0)
		return;
	
	buffer_file_dump (file, fd);

	close (fd);
}

/* ---- called from netlink thread ---- */
static void
dump_cmdline (BufferFile *file, pid_t pid)
{
	int fd, len;
	char str[PATH_MAX], path[PATH_MAX], buffer[4096];

	sprintf (str, PROC_PATH "/%d/exe", pid);
	if ((len = readlink (str, path, sizeof (path) - 1)) < 0)
		return;
	path[len] = '\0';

	/* Zero delimited everything */

	/* write <pid>\n<exe-path>\n */
	sprintf (str, "%d\n:%s\n:", pid, path);
	buffer_file_append (file, str, strlen (str));

	/* write [zero delimited] <cmdline> */
	sprintf (str, PROC_PATH "/%d/cmdline", pid);
	fd = open (str, O_RDONLY);
	if (fd >= 0) {
		int i, start;

		len = read (fd, buffer, 4096);
		buffer[4095] = '\0';
		for (start = i = 0; i < len; i++) {
			int newline = buffer[i] == '\n';

			/* new lines are not so good for rendering, and worse for parsing */
			if (newline)
				buffer[i] = '\0';

			if (buffer[i] == '\0') {
				buffer_file_append (file, buffer + start, i - start + 1);
				if (newline) {
					/* skip to the next arg */
					for (; i < len && buffer[i] != '\0'; i++) ;
				}
				start = i + 1;
			}
		}
		close (fd);
	}

	buffer_file_append (file, "\n\n", 2);
}

/* ---- called from netlink thread ---- */
static void
dump_paternity (BufferFile *file, pid_t pid, pid_t ppid)
{
	char str[1024];
	/* <Child> <Parent> */
	sprintf (str, "%d %d\n", pid, ppid);
	buffer_file_append (file, str, strlen (str));
}

typedef struct {
	BufferFile *cmdline_file;
	BufferFile *paternity_file;
} PidEventClosure;

/* ---- called from netlink thread ---- */
static void
pid_event_cb (const PidScanEvent *event, void *user_data)
{
	PidEventClosure *cl = user_data;

	switch (event->type) {
	case PID_SCAN_EVENT_EXEC:
		dump_cmdline (cl->cmdline_file, event->pid);
		break;
	case PID_SCAN_EVENT_CREATED:
		dump_paternity (cl->paternity_file, event->pid, event->u.ppid);
		break;
	default:
		break;
	}
}

static unsigned long
get_uptime (int fd)
{
	char          buf[80];
	ssize_t       len;
	unsigned long u1, u2;

	lseek (fd, SEEK_SET, 0);

	len = read (fd, buf, sizeof(buf)-1);
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

/*
 * Probe the controller in genetlink to find the family id
 * for the TASKSTATS family
 */
static __u16 get_family_id(int sd)
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
	if (rc < 0)
		return 0;

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

static int
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

	return netlink_taskstats_id != 0;
error:
	if (netlink_socket >= 0)
		close (netlink_socket);

	return 0;
}

static int
am_in_initrd (void)
{
	FILE *mi;
	int ret = 0;
	char buffer[4096];

	mi = fopen (PROC_PATH "/self/mountinfo", "r");
	if (!mi)
		return ret;

	/* find a single mount; parent of itself: an initrd */
	while (fgets (buffer, 4096, mi)) {
		/* we expect: "1 1 0:1 / / rw - rootfs rootfs rw" */
		if (!strncmp (buffer, "1 1 ", 4)) {
			ret = 1;
			break;
		}
	}
	fclose (mi);

	log ("bootchart-collector run %sside initrd\n", ret ? "in" : "out");
	return ret;
}


static int
have_dev_tmpfs (void)
{
	FILE *mi;
	int ret = 0;
	char buffer[4096];

	mi = fopen (PROC_PATH "/self/mountinfo", "r");
	if (!mi)
		return ret;

	/* find a single mount; parent of itself: an initrd */
	while (fgets (buffer, 4096, mi)) {
		/* we expect: "17 1 0:15 / /dev rw,relatime - tmpfs udev rw,nr_inodes=0,mode=755 */
		if (strstr (buffer, "/dev") &&
		    strstr (buffer, "rw") &&
		    strstr (buffer, "tmpfs")) {
			ret = 1;
			break;
		}
	}
	fclose (mi);

	log ("bootchart-collector has %stmpfs on /dev\n", ret ? "" : "no ");
	return ret;
}

/*
 * If we were started during the initrd, (some initrds replace
 * 'init' with bootchartd (strangely) -but- we have no
 * init=/sbin/bootchartd, no-one will be started in the
 * main-system to stop logging, so we'll run forever; urk !
 */
static int
sanity_check_initrd (void)
{
	FILE *cmdline;
	char buffer[4096];

	cmdline = fopen (PROC_PATH "/cmdline", "r");
	if (!cmdline) {
		log ("Urk ! no" PROC_PATH "/cmdline on a linux system !?\n");
		return 1;
	}
	assert (NULL != fgets (buffer, sizeof (buffer), cmdline));
	fclose (cmdline);

	if (!strstr (buffer, "init=") ||
	    !strstr (buffer, "bootchartd")) {
		log ("Urk ! can't find bootchartd on the cmdline\n");
		return 1;
	}

	return 0;
}

/*
 * We cannot rely on a generic Linux knowing that we need have
 * our special TMPFS_PATH move mounted into the running system
 * in order to cleanup the initrd. Soo ... we do that ourselves
 * when we think the time is right. We do this by leaching off
 * the /dev/ mount which is always (often?) move mounted into the
 * running system...
 */
static int
chroot_into_dev (void)
{
	log ("bootchart-collector - migrating into /dev/\n");

	if (mkdir (MOVE_DEV_PATH, 0777)) {
		if (errno != EEXIST) {
			log ("bootchart-collector - failed to create "
				 MOVE_DEV_PATH " move mount-point: '%s'\n", strerror (errno));
			return 1;
		}
	}
	if (mount (TMPFS_PATH, MOVE_DEV_PATH, NULL, MS_MGC_VAL | MS_MOVE, NULL)) {
		log ("bootchart-collector - mount failed: '%s'\n", strerror (errno));
		return 1;
	}
	if (chroot (MOVE_DEV_PATH)) {
		log ("bootchart-collector - chroot failed: '%s'\n", strerror (errno));
		return 1;
	}
	return 0;
}

static void
usage (void)
{
	fprintf (stderr, "Usage: bootchart-collector [--usleep <usecs>] [-r] [--dump <path>] [hz=50]\n");
	fprintf (stderr, "swiss-army boot-charting tool.\n");
	fprintf (stderr, "   --usleep <usecs>	sleeps for given number of usecs and exits.\n");
	fprintf (stderr, "   --probe-running	returns success if a bootchart collector is running.\n");
	fprintf (stderr, "   --dump <path>	if another bootchart is running, dumps it's state to <path> and exits.\n");
	fprintf (stderr, "   -r		use relative time-stamps from the profile starting\n");
	fprintf (stderr, "   --console/-c	output debug on the console, not into kernel log\n");
	fprintf (stderr, "   <otherwise>	internally logs profiling data samples at frequency <hz>\n");
	exit (1);
}

/*
 * setup our environment, of course we could package these,
 * but it's easier to just require a single directory in
 * people's initrd.
 */
static int
enter_environment (int console_debug)
{
	/* create a happy tmpfs */
	if (mount ("none", TMPFS_PATH, "tmpfs", MS_NOEXEC|MS_NOSUID, NULL) < 0) {
		if (errno != EBUSY) {
			log ("bootchart-collector tmpfs mount to " TMPFS_PATH " failed\n");
			return 1;
		}
	}

	/* re-direct debugging output */
	if (mknod (TMPFS_PATH "/kmsg", S_IFCHR|0666, makedev(1, 11)) < 0) {
		if (errno != EEXIST) {
			log ("bootchart-collector can't create kmsg node\n");
			return 1;
		}
	}

	if (!console_debug)
		if (!freopen (TMPFS_PATH "/kmsg", "w", stderr)) {
			log ("freopen() failed\n");
			return 1;
		}

	/* we badly need proc */
	if (mkdir (PROC_PATH, 0777) < 0) {
		if (errno != EEXIST) {
			log ("bootchart-collector proc mkdir at " PROC_PATH " failed\n");
			return 1;
		}
	}
	if (mount ("none", PROC_PATH, "proc",
		   MS_NODEV|MS_NOEXEC|MS_NOSUID , NULL) < 0) {
		if (errno != EBUSY) {
			log ("bootchart-collector proc mount to " PROC_PATH " failed\n");
			return 1;
		}
	}

	/* we need our tmpfs to look like this file-system,
	   so we can chroot into it if necessary */
	mkdir (TMPFS_PATH EARLY_PREFIX, 0777);
	mkdir (TMPFS_PATH EARLY_PREFIX LIBDIR, 0777);
	mkdir (TMPFS_PATH PKGLIBDIR, 0777);
	if (symlink ("../..", TMPFS_PATH TMPFS_PATH)) {
		if (errno != EEXIST) {
			log ("bootchart-collector failed to create a chroot at "
				 TMPFS_PATH TMPFS_PATH " error '%s'\n", strerror (errno));
			return 1;
		}
	}

	return 0;
}

static void
cleanup_dev (void)
{
	if (!access (MOVE_DEV_PATH "/kmsg", W_OK)) {
		umount2 (MOVE_DEV_PATH PROC_PATH, MNT_DETACH);
		umount2 (MOVE_DEV_PATH, MNT_DETACH);
		rmdir (MOVE_DEV_PATH);
	}
}

static int
clean_enviroment (void)
{
	int ret = 0;

	if (umount2 (PROC_PATH, MNT_DETACH) < 0) {
		perror ("umount " PROC_PATH);
		ret = 1;
	}

	if (unlink (TMPFS_PATH "/kmsg") < 0) {
		perror ("unlinking " TMPFS_PATH "/kmsg");
		ret = 1;
	}

	if (umount2 (TMPFS_PATH, MNT_DETACH) < 0) {
		perror ("umount " TMPFS_PATH);
		ret = 1;
	}

	return ret;
}

static void
term_handler (int sig)
{
	int ret = 0;

	if (unlink (TMPFS_PATH "/kmsg") < 0)
		ret = 1;

	if (umount2 (PROC_PATH, MNT_DETACH) < 0)
		ret = 1;

	if (umount2 (TMPFS_PATH, MNT_DETACH) < 0)
		ret = 1;

	_exit(ret == 0 ? EXIT_SUCCESS : EXIT_FAILURE);
}

static void
setup_sigaction(int sig)
{
	struct sigaction sa;
	sigset_t block_mask;

	sigemptyset(&block_mask);
	sa.sa_handler = term_handler;
	sa.sa_mask = block_mask;
	sa.sa_flags = 0;
	sigaction(sig, &sa, NULL);
}

static void
test (void)
{
	dump_header (NULL);
}

void
arguments_set_defaults (Arguments *args)
{
	memset (args, 0, sizeof (Arguments));
/*	args->console_debug = 1;  */
}

void arguments_free (Arguments *args)
{
	if (args->dump_path)
		free (args->dump_path);
}

void arguments_parse (Arguments *args, int argc, char **argv)
{
	int i;

	for (i = 1; i < argc; i++)  {
		if (!argv[i]) continue;
    
/*		log ("arg %d = '%s'\n", i, argv[i]); */

		/* commands with an argument */
		if (i < argc - 1) {
			const char *param = argv[i+1];

			/* usleep can be hard to find */
			if (!strcmp (argv[i], "--usleep"))
				args->usleep_time = strtoul (param, NULL, 0);

			/* output mode */
			else if (!strcmp (argv[i], "-d") ||
				 !strcmp (argv[i], "--dump"))
				args->dump_path = strdup (param);
		}
      
		if (!strcmp (argv[i], "--probe-running"))
			args->probe_running = 1;
      
		else if (!strcmp (argv[i], "-r"))
			args->relative_time = 1;
      
		else if (!strcmp (argv[i], "-c") ||
			 !strcmp (argv[i], "--console"))
			args->console_debug = 1;

		else if (!strcmp (argv[i], "-h") ||
			 !strcmp (argv[i], "--help"))
			usage();

		else if (!strcmp (argv[i], "-t") ||
			 !strcmp (argv[i], "--test"))
			test();
      
		/* appended args mode args */
		else if (!args->hz)
			args->hz = strtoul (argv[i], NULL, 0);

		else
			usage();
	}
}

int main (int argc, char *argv[])
{
	Arguments args;
	int i, use_taskstat;
	int in_initrd = 0, clean_environment = 1;
	int stat_fd, disk_fd, uptime_fd, meminfo_fd,  pid, ret = 1;
	PidScanner *scanner = NULL;
	unsigned long reltime = 0;
	BufferFile *stat_file, *disk_file, *per_pid_file, *meminfo_file;
	PidEventClosure pid_ev_cl;
	int *fds[] = { &stat_fd, &disk_fd, &uptime_fd, &meminfo_fd, NULL };
	const char *fd_names[] = { "/stat", "/diskstats", "/uptime", "/meminfo", NULL };
	StackMap map = STACK_MAP_INIT; /* make me findable */

	arguments_set_defaults (&args);
	arguments_parse (&args, argc, argv);

	if (args.usleep_time > 0) {
		usleep (args.usleep_time);
		return 0;
	}

	if (enter_environment (args.console_debug))
		return 1;

	setup_sigaction(SIGTERM);

	log ("bootchart-collector started as pid %d with %d args: ",
		 (int) getpid(), argc - 1);
	for (i = 1; i < argc; i++)
		log ("'%s' ", argv[i]);
	log ("\n");

	if (args.dump_path) {
		Arguments remote_args;

		ret = buffers_extract_and_dump (args.dump_path, &remote_args);
		ret |= dump_header (args.dump_path);

		if (!remote_args.relative_time)
			ret |= dump_dmsg (args.dump_path);
		if (!ret)
			cleanup_dev ();
		goto exit;
	}

	if (!args.relative_time) { /* manually started */
		in_initrd = am_in_initrd ();
		if (in_initrd && sanity_check_initrd ())
			goto exit;
	}

	pid = bootchart_find_running_pid (NULL);
	if (args.probe_running) {
		clean_environment = pid < 0;
		ret = pid < 0;
		goto exit;
	} else {
		if (pid >= 0) {
			clean_environment = 0;
			log ("bootchart collector already running as pid %d, exiting...\n", pid);
			goto exit;
		}
	}
      
	/* defaults */
	if (!args.hz)
		args.hz = 50;

	for (i = 0; fds [i]; i++) {
		char *path = malloc (strlen (PROC_PATH) + strlen (fd_names[i]) + 1);
		if (!path) {
			perror("malloc");
			exit(1);
		}
		strcpy (path, PROC_PATH);
		strcat (path, fd_names[i]);

		*fds[i] = open (path, O_RDONLY);
		if (*fds[i] < 0) {
			log ("error opening '%s': %s'\n",
				 path, strerror (errno));
			exit (1);
		}
		free (path);
	}

	stat_file = buffer_file_new (&map, "proc_stat.log");
	disk_file = buffer_file_new (&map, "proc_diskstats.log");
	if ( (use_taskstat = init_taskstat()) )
		per_pid_file = buffer_file_new (&map, "taskstats.log");
	else
		per_pid_file = buffer_file_new (&map, "proc_ps.log");
	meminfo_file = buffer_file_new (&map, "proc_meminfo.log");
	pid_ev_cl.cmdline_file = buffer_file_new (&map, "cmdline2.log");
	pid_ev_cl.paternity_file = buffer_file_new (&map, "paternity.log");

	if (!stat_file || !disk_file || !per_pid_file || !meminfo_file ||
	    !pid_ev_cl.cmdline_file || !pid_ev_cl.paternity_file) {
		log ("Error allocating output buffers\n");
		return 1;
	}

	scanner = pid_scanner_new_netlink (pid_event_cb, &pid_ev_cl);
	if (!scanner)
		scanner = pid_scanner_new_proc (PROC_PATH, pid_event_cb, &pid_ev_cl);
	if (!scanner)
		return 1;

	if (args.relative_time) {
		reltime = get_uptime (uptime_fd);
		if (! reltime)
			exit (1);
	}

	while (1) {
		pid_t pid;
		char uptime[80];
		size_t uptimelen;
		unsigned long u;

		if (in_initrd) {
			if (have_dev_tmpfs ()) {
				if (chroot_into_dev ()) {
					log ("failed to chroot into /dev - exiting so run_init can proceed\n");
					return 1;
				}
				in_initrd = 0;
			}
		}
      
		u = get_uptime (uptime_fd);
		if (!u)
			return 1;

		uptimelen = sprintf (uptime, "%lu\n", u - reltime);

		buffer_file_dump_frame_with_timestamp (stat_file, stat_fd, uptime, uptimelen);
		buffer_file_dump_frame_with_timestamp (disk_file, disk_fd, uptime, uptimelen);
		buffer_file_dump_frame_with_timestamp (meminfo_file, meminfo_fd, uptime, uptimelen);

		/* output data for each pid */
		buffer_file_append (per_pid_file, uptime, uptimelen);

		pid_scanner_restart (scanner);
		while ((pid = pid_scanner_next (scanner))) {

			if (use_taskstat)
				dump_taskstat (per_pid_file, scanner);
			else
				dump_proc_stat (per_pid_file, pid);
		}
		buffer_file_append (per_pid_file, "\n", 1);

		usleep (1000000 / args.hz);
	}

	/*
	 * In reality - we are always killed before we reach
	 * this point
	 */
	if (use_taskstat) {
		if (close (netlink_socket) < 0) {
			perror ("failed to close netlink socket");
			exit (1);
		}
	}

	for (i = 0; fds [i]; i++) {
		if (close (*fds[i]) < 0) {
			log ("error closing file '%s': %s'\n",
				 fd_names[i], strerror (errno));
			return 1;
		}
	}

	ret = 0;

 exit:
	arguments_free (&args);

	if (scanner)
		ret |= pid_scanner_free (scanner);

	if (clean_environment) {
		if (clean_enviroment() == 0)
			log ("bootchart-collector pid: %d unmounted proc / clean exit\n", getpid());
	}

	return ret;
}
