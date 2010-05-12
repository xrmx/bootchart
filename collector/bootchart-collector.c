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

#include "bootchart-common.h"

#include <linux/genetlink.h>
#include <linux/taskstats.h>
#include <linux/cgroupstats.h>

const char *proc_path = "proc";

/* pid uniqifying code */
typedef struct {
	pid_t pid;
	pid_t ppid;
	__u64 time_total;
	unsigned int dumped_args : 1;
} PidEntry;

static inline PidEntry *
get_pid_entry (pid_t pid)
{
  static PidEntry *pids = NULL;
  static pid_t     pids_size = 0;

  pid_t old_pids_size = pids_size;
  if (pid >= pids_size)
    {
      pids_size = pid + 512;
      pids = realloc (pids, sizeof (PidEntry) * pids_size);
      memset (pids + old_pids_size, 0, sizeof (PidEntry) * (pids_size - old_pids_size));
    }
  return pids + pid;
}

unsigned long get_uptime (int fd);

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
	if (!tdir) {
//		fprintf (stderr, "no task data for %d (at '%s')\n", pid, proc_task_buffer);
		return &tgits;
	}

	while ((tent = readdir (tdir)) != NULL) {
		pid_t tpid;
		if (!isdigit (tent->d_name[0]))
			continue;

//		fprintf (stderr, "read taskstats data from %d/%s\n", pid, tent->d_name);
		tpid = atoi (tent->d_name);
		if (pid != tpid) {
			struct taskstats *ts = get_taskstats (tpid);

			if (!ts) {
//				fprintf (stderr, "error no taskstats %d\n", tpid);
				continue;
			}

//			fprintf (stderr, "CPU aggregate %d: %ld\n", tpid, (long) ts->cpu_run_real_total);

			/* aggregate */
			tgits.cpu_run_real_total += ts->cpu_run_real_total;
			tgits.swapin_delay_total += ts->swapin_delay_total;
			tgits.blkio_delay_total += ts->blkio_delay_total;
		}
	}
	closedir (tdir);

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

static void
dump_cmdline (BufferFile *file, pid_t pid)
{
	int fd;
	PidEntry *entry;
	char str[PATH_MAX], path[PATH_MAX];

	entry = get_pid_entry (pid);

	if (entry->dumped_args)
		return;

	entry->dumped_args = 1;

	sprintf (str, "%s/%d/exe", proc_path, pid);
	if (readlink (str, path, sizeof (path) - 1) < 0)
		return;

	/* write <pid>\n<exe-path>\n */
	path [sizeof (path) - 1] = '\0';
	sprintf (str, "%d\n%s\n", pid, path);
	buffer_file_append (file, str, strlen (str));

	/* write [zero delimited] <cmdline> */
	sprintf (str, "%s/%d/cmdline", proc_path, pid);
	fd = open (str, O_RDONLY);
	if (fd >= 0) { /* usually no '\n's in arguments - we hope */
		buffer_file_dump (file, fd);
		close (fd);
	}

	buffer_file_append (file, "\n\n", 2);
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

  /* are we in a possibly flaky initrd */
  if (!access ("/dev/random", R_OK))
    return 0;

  cmdline = fopen ("proc/cmdline", "r");
  if (!cmdline) {
    fprintf (stderr, "Urk ! no proc/cmdline on a linux system !?\n");
    return 1;
  }
  fgets (buffer, sizeof (buffer), cmdline);
  fclose (cmdline);

  if (!strstr (buffer, "init=") ||
      !strstr (buffer, "bootchartd")) {
    fprintf (stderr, "Urk ! can't find bootchartd on the cmdline\n");
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
  fprintf (stderr, "   <otherwise>	internally logs profiling data samples at frequency <hz>\n");
  exit (1);
}

int main (int argc, char *argv[])
{
  DIR *proc;
  int i, use_taskstat, rel, mnt = 0;
  int stat_fd, disk_fd, uptime_fd;
  unsigned long hz = 0, reltime = 0;
  BufferFile *stat_file, *disk_file, *per_pid_file, *cmdline_file;
  int *fds[] = { &stat_fd, &disk_fd, &uptime_fd, NULL };
  const char *fd_names[] = { "/stat", "/diskstats", "/uptime", NULL };
  StackMap map = STACK_MAP_INIT; /* make me findable */

  rel = 0;
  if (access ("/proc/kmsg", W_OK))
    freopen ("/proc/kmsg", "a", stderr);
  else
    freopen ("kmsg", "a", stderr);

  fprintf (stderr, "bootchart-collector started\n");

  for (i = 1; i < argc; i++) 
    {
      if (!argv[i]) continue;
    
      /* commands with an argument */
      if (i < argc - 1)
	{
	  const char *param = argv[i+1];

	  /* usleep can be hard to find */
	  if (!strcmp (argv[i], "--usleep"))
	    {
	      long sleep = strtoul (param, NULL, 0);
	      usleep (sleep);
	      return 0;
	    }

	  /* output mode */
	  if (!strcmp (argv[i], "-d") ||
	      !strcmp (argv[i], "--dump"))
	    return dump_state (param);
	}
      
      if (!strcmp (argv[i], "--probe-running"))
	return probe_running ();

      else if (!strcmp (argv[i], "-r"))
	rel = 1;
      
      else if (!strcmp (argv[i], "-h") ||
	       !strcmp (argv[i], "--help"))
	usage();
      
      /* default mode args */
      else if (!hz)
	hz = strtoul (argv[i], NULL, 0);

      else
	usage();
    }

  if (mount ("none", proc_path, "proc",
	      MS_NODEV|MS_NOEXEC|MS_NOSUID , NULL) < 0) {
    if (errno != EBUSY) {
      fprintf (stderr, "bootchart-collector proc mount failed\n");
      exit (1);
    }
  } else
    mnt = 1;

  fprintf (stderr, "bootchart-collector mounted proc\n");

  if (sanity_check_initrd ())
    return 1;
      
  /* defaults */
  if (!hz)
    hz = 50;
      
  proc = opendir (proc_path);
  if (!proc)
    {
      fprintf (stderr, "Failed to open %s: %s\n", proc_path, strerror(errno));
      return 1;
    }

  for (i = 0; fds [i]; i++)
    {
      char *path = malloc (strlen (proc_path) + strlen (fd_names[i]) + 1);
      strcpy (path, proc_path);
      strcat (path, fd_names[i]);

      *fds[i] = open (path, O_RDONLY);
      if (*fds[i] < 0)
	{
	  fprintf (stderr, "error opening '%s': %s'\n",
		   path, strerror (errno));
	  exit (1);
	}
    }

  stat_file = buffer_file_new (&map, "proc_stat.log");
  disk_file = buffer_file_new (&map, "proc_diskstats.log");
  if ( (use_taskstat = init_taskstat()) )
    per_pid_file = buffer_file_new (&map, "taskstats.log");
  else
    per_pid_file = buffer_file_new (&map, "proc_ps.log");
  cmdline_file = buffer_file_new (&map, "cmdline.log");

  if (!stat_file || !disk_file || !per_pid_file || !cmdline_file)
    {
      fprintf (stderr, "Error allocating output buffers\n");
      return 1;
    }

  if (rel) {
    reltime = get_uptime (uptime_fd);
    if (! reltime)
      exit (1);
  }

  while (1)
    {
      char uptime[80];
      size_t uptimelen;
      unsigned long u;
      struct dirent *ent;

      u = get_uptime (uptime_fd);
      if (!u)
	return 1;

      uptimelen = sprintf (uptime, "%lu\n", u - reltime);

      buffer_file_dump_frame_with_timestamp (stat_file, stat_fd,
					     uptime, uptimelen);
      buffer_file_dump_frame_with_timestamp (disk_file, disk_fd,
					     uptime, uptimelen);

      /* output data for each pid */
      buffer_file_append (per_pid_file, uptime, uptimelen);

      rewinddir (proc);
      while ((ent = readdir (proc)) != NULL) {
	pid_t pid;

	if (!isdigit (ent->d_name[0]))
	  continue;

	pid = atoi (ent->d_name);
	if (use_taskstat)
	  dump_taskstat (per_pid_file, pid);
	else
	  dump_proc (per_pid_file, ent->d_name);
	dump_cmdline (cmdline_file, pid);
      }
      buffer_file_append (per_pid_file, "\n", 1);

      usleep (10000000 / hz);
    }

  /*
   * In reality - we are always killed before we reach
   * this point
   */
  if (use_taskstat)
    {
      if (close (netlink_socket) < 0)
	{
	  perror ("failed to close netlink socket");
	  exit (1);
	}
    }

  for (i = 0; fds [i]; i++)
    {
      if (close (*fds[i]) < 0)
	{
	  fprintf (stderr, "error closing file '%s': %s'\n",
		   fd_names[i], strerror (errno));
	  return 1;
	}
    }

  if (closedir (proc) < 0)
    {
      perror ("close /proc");
      exit (1);
    }

  if (mnt && umount (proc_path) < 0) {
    perror ("umount /proc");
    exit (1);
  }

  fprintf (stderr, "bootchart-collector unmounted proc / clean exit\n");

  return 0;
}
