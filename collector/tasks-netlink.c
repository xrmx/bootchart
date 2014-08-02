/*
 * tasks-netlink.c
 *
 * Listen for netlink events that give us news of process creation / exit.
 * This saves polling /proc, and gives us true parent details giving a
 * much cleaner process tree.
 *
 * Copyright Novell, Inc, 2010
 *
 * Copyright IBM Corporation, 2007
 * Author: Dhaval Giani <[EMAIL PROTECTED]>
 * Derived from test_cn_proc.c by Matt Helsley
 * Original copyright notice follows
 *
 * Copyright (C) Matt Helsley, IBM Corp. 2005
 * Derived from fcctl.c by Guillaume Thouvenin
 * Original copyright notice follows:
 *
 * Copyright (C) 2005 BULL SA.
 * Written by Guillaume Thouvenin <[EMAIL PROTECTED]>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
 */
#include "common.h"

#include <linux/connector.h>
#include <linux/netlink.h>
#include "linux/cn_proc.h"
#include <poll.h>

#define SEND_MESSAGE_LEN (NLMSG_LENGTH(sizeof(struct cn_msg) + \
                                       sizeof(enum proc_cn_mcast_op)))
#define RECV_MESSAGE_LEN (NLMSG_LENGTH(sizeof(struct cn_msg) + \
                                       sizeof(struct proc_event)))

#define SEND_MESSAGE_SIZE    (NLMSG_SPACE(SEND_MESSAGE_LEN))
#define RECV_MESSAGE_SIZE    (NLMSG_SPACE(RECV_MESSAGE_LEN))

#define max(x,y) ((y)<(x)?(x):(y))

#define ZERO(s)       memset (&(s), 0, sizeof (s))
#define ZERO_ARRAY(s) memset ((s), 0, sizeof (s))
#define BUFF_SIZE (max(max(SEND_MESSAGE_SIZE, RECV_MESSAGE_SIZE), 1024))

#define PROC_CN_MCAST_LISTEN 1


typedef struct {
	pid_t pid;
	pid_t parent;
	pid_t threads[1];
} Process;

typedef struct {
	PidScanner     parent;
  
	pthread_t      listener;
	int	       socket;

	/* used only by the calling thread */
	Process      **procs;
	int	       procs_size;
	int	       n_procs;

	unsigned int   cur_proc;
	unsigned int   cur_thread;

	/* guard for following members */
	pthread_mutex_t lock;

	/* queue up netlink events */
	struct proc_event *buffer;
	int                buffer_size;
} NetLinkPidScanner;

static int
netlink_pid_scanner_free (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	if (nls->socket)
		close (nls->socket);
	pthread_mutex_destroy (&nls->lock);
	return 0;
}

static int
find_pid_an_idx (NetLinkPidScanner *nls, pid_t pid, int create)
{
	int i, j;

	/* append is a very common case at boot */
	if (nls->n_procs > 0 && pid > nls->procs[nls->n_procs - 1]->pid)
		i = nls->n_procs;
	else {
		/* should be a binary chop */
		for (i = 0; i < nls->n_procs; i++) {
			if (nls->procs[i]->pid > pid)
				break;
		}
	}

	/* were we already there ? */
	if (i > 0 && nls->procs[i - 1]->pid == pid)
		return i - 1;

	if (!create)
		return -1;

	/* increase size & realloc */
	if (nls->n_procs >= nls->procs_size) {
		if (!nls->procs_size)
			nls->procs_size = 256;
		nls->procs_size = nls->procs_size * 2;
		nls->procs = realloc (nls->procs, sizeof (Process *) * nls->procs_size);
	}

	/* shuffle everyone up */
	for (j = nls->n_procs; j > i; j--)
		nls->procs[j] = nls->procs[j - 1];

	nls->n_procs++;
	nls->procs[i] = (Process *)calloc (1, sizeof (Process));
	nls->procs[i]->pid = pid;

	return i;
}

static void
insert_pid (NetLinkPidScanner *nls, pid_t pid, pid_t parent)
{
	int idx = find_pid_an_idx (nls, pid, 1);
	nls->procs[idx]->parent = parent;
}

static void
insert_pid_thread (NetLinkPidScanner *nls, pid_t pid, pid_t thread)
{
	int n, idx;
	Process *p;

	idx = find_pid_an_idx (nls, pid, 1);
	p = nls->procs[idx];

	for (n = 0; p->threads[n]; n++)
		if (p->threads[n] == thread)
			return;

	p = realloc (p, sizeof (Process) + sizeof (pid_t) * (n + 1));
	nls->procs[idx] = p;

	p->threads[n] = thread;
	p->threads[n+1] = 0;
}

static void
remove_pid (NetLinkPidScanner *nls, pid_t pid)
{
	int i;
	if ((i = find_pid_an_idx (nls, pid, 0)) < 0)
		return;
	nls->n_procs--;
	for (; i < nls->n_procs; i++)
		nls->procs[i] = nls->procs[i+1];
}

static void
remove_pid_thread (NetLinkPidScanner *nls, pid_t pid, pid_t thread)
{
	int i, j;
	Process *p;

	if ((i = find_pid_an_idx (nls, pid, 0)) < 0)
		return;
	p = nls->procs[i];
	for (i = j = 0; p->threads[i] && p->threads[j]; i++) {
		if (p->threads[i] == thread)
			j++;
		p->threads[i] = p->threads[j];
	}
	p->threads[i] = 0;
}

static void
netlink_pid_scanner_restart (PidScanner *scanner)
{
	int ev_count, i;
	struct proc_event *evs;

	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	nls->cur_proc = 0;

	/* Import anything new that arrived recently */
	pthread_mutex_lock (&nls->lock);
	evs = nls->buffer;
	ev_count = nls->buffer_size;

	nls->buffer = NULL;
	nls->buffer_size = 0;
	pthread_mutex_unlock (&nls->lock);

	for (i = 0; i < ev_count; i++) {
		struct proc_event *ev = evs + i;
		switch (ev->what) {
		case PROC_EVENT_FORK:

/*			log ("Fork: parent = %d (ptgid %d)\tchild=%d (tpid %d)\n",
				 ev->event_data.fork.parent_pid,
				 ev->event_data.fork.parent_tgid,
				 ev->event_data.fork.child_pid,
				 ev->event_data.fork.child_tgid); */

			/* new process */
			if (ev->event_data.fork.child_pid == ev->event_data.fork.child_tgid)
				insert_pid (nls, ev->event_data.fork.child_tgid,
					    ev->event_data.fork.parent_tgid);
			else /* new thread */
				insert_pid_thread (nls, ev->event_data.fork.child_tgid,
						   ev->event_data.fork.child_pid);
			break;
		case PROC_EVENT_EXIT:
/*			log ("Exit: pid = %d\ttgid=%d\n",
				ev->event_data.exit.process_pid,
				ev->event_data.exit.process_tgid); */

			/* process exit */
			if (ev->event_data.exit.process_pid == ev->event_data.exit.process_tgid)
				remove_pid (nls, ev->event_data.exit.process_pid);
			else /* thread exit */
				remove_pid_thread (nls, ev->event_data.exit.process_tgid,
						   ev->event_data.exit.process_pid);
			break;
		default:
			log ("Serious event logging / threading error %d\n", ev->what);
			break;
		}
	}

	free (evs);
}

/* read in the /proc goodness */
static void
netlink_pid_scanner_bootstrap (NetLinkPidScanner *nls)
{
	int pid;
	PidScanner *bootstrap;

	/* few process are around at early boot time */
	bootstrap = pid_scanner_new_proc (PROC_PATH, NULL, NULL);
	pid_scanner_restart (bootstrap);
	while ((pid = pid_scanner_next (bootstrap))) {
		int tpid;

		insert_pid (nls, pid, 0);

		pid_scanner_get_tasks_start (bootstrap);
		while ((tpid = pid_scanner_get_tasks_next (bootstrap)))
			insert_pid_thread (nls, pid, tpid);
		pid_scanner_get_tasks_stop (bootstrap);
	}
	pid_scanner_free (bootstrap);
}

static pid_t
netlink_pid_scanner_next (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	if (nls->cur_proc >= nls->n_procs)
		return 0;
	return nls->procs[nls->cur_proc++]->pid;
}

static pid_t
netlink_pid_scanner_get_cur_pid (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	if (nls->cur_proc >= nls->n_procs)
		return 0;
	return nls->procs[nls->cur_proc]->pid;
}

static pid_t
netlink_pid_scanner_get_cur_ppid (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	if (nls->cur_proc >= nls->n_procs)
		return 0;
	return nls->procs[nls->cur_proc]->parent;
}

static void
netlink_pid_scanner_get_tasks_start (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	nls->cur_thread = 0;
}

static pid_t
netlink_pid_scanner_get_tasks_next (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	if (nls->cur_proc >= nls->n_procs ||
	    !nls->procs[nls->cur_proc]->threads[nls->cur_thread])
		return 0;
	return nls->procs[nls->cur_proc]->threads[nls->cur_thread++];
}

static void
netlink_pid_scanner_get_tasks_stop (PidScanner *scanner)
{
	NetLinkPidScanner *nls = (NetLinkPidScanner *) scanner;
	nls->cur_thread = 0;
}

static void 
handle_news (NetLinkPidScanner *nls, struct cn_msg *cn_hdr)
{
	struct proc_event *ev;

        ev = (struct proc_event*)cn_hdr->data;

        switch (ev->what) {
        case PROC_EVENT_FORK:
		/* hide threads */
		if (ev->event_data.fork.child_pid == ev->event_data.fork.child_tgid)
			pid_scanner_emit_paternity ((PidScanner *)nls,
						    ev->event_data.fork.child_tgid,
						    ev->event_data.fork.parent_tgid);
		/* drop through */
        case PROC_EVENT_EXIT:
		pthread_mutex_lock (&nls->lock);
		nls->buffer = realloc (nls->buffer, sizeof (struct proc_event) * (nls->buffer_size + 1));
		memcpy (&(nls->buffer[nls->buffer_size]), ev, sizeof (struct proc_event));
		nls->buffer_size++;
		pthread_mutex_unlock (&nls->lock);
		break;
	/* postpone triggering callback until we have a new exec name and args */
        case PROC_EVENT_EXEC:
		pid_scanner_emit_exec ((PidScanner *)nls, ev->event_data.exec.process_pid);
		break;
        case PROC_EVENT_UID:
        default:
                break;
        }
}

static size_t
netlink_recvfrom (NetLinkPidScanner *nls, char *buffer)
{
	socklen_t from_nla_len;
	struct sockaddr_nl from_nla;

	ZERO (from_nla);
        from_nla.nl_family = AF_NETLINK;
        from_nla.nl_groups = CN_IDX_PROC;
        from_nla.nl_pid = 1;

	from_nla_len = sizeof(from_nla);
	return recvfrom (nls->socket, buffer, BUFF_SIZE, 0,
			 (struct sockaddr*)&from_nla, &from_nla_len);
}

static void *
netlink_listen_thread (void *user_data)
{
	NetLinkPidScanner *nls = user_data;
  
	struct cn_msg *cn_hdr;

	char buff[BUFF_SIZE];
	size_t recv_len = 0;

	for (;;) {
                struct nlmsghdr *nlh = (struct nlmsghdr*)buff;

		/* block here mostly waiting for news ... */
		ZERO_ARRAY (buff);
                recv_len = netlink_recvfrom (nls, buff);
                if (recv_len < 1)
			continue;

		/* parse the news */
                while (NLMSG_OK (nlh, recv_len)) {
                        cn_hdr = NLMSG_DATA (nlh);
                        if (nlh->nlmsg_type == NLMSG_NOOP)
                                continue;
                        if ((nlh->nlmsg_type == NLMSG_ERROR) ||
                            (nlh->nlmsg_type == NLMSG_OVERRUN)) {
				log ("Netlink error or overrun !\n");
                                break;
			}
			handle_news (nls, cn_hdr);
                        if (nlh->nlmsg_type == NLMSG_DONE)
                                break;
                        nlh = NLMSG_NEXT(nlh, recv_len);
                }
        }

        return NULL;
}

PidScanner *
pid_scanner_new_netlink (PidScanEventFn event_fn, void *user_data)
{
	char buff[BUFF_SIZE];
	struct cn_msg *cn_hdr;
	struct nlmsghdr *nl_hdr;
	struct sockaddr_nl my_nla;
	enum proc_cn_mcast_op *mcop_msg;
	NetLinkPidScanner *nls;

	nls = (NetLinkPidScanner *)pid_scanner_alloc (sizeof (NetLinkPidScanner),
						      event_fn, user_data);

  /* vtable land-fill */
#define INIT(name) nls->parent.name = netlink_pid_scanner_##name
	INIT(free);
	INIT(restart);
	INIT(next);
	INIT(get_cur_pid);
	INIT(get_cur_ppid);
	INIT(get_tasks_start);
	INIT(get_tasks_next);
	INIT(get_tasks_stop);
#undef INIT

        /*
         * Create an endpoint for communication. Use the kernel user
         * interface device (PF_NETLINK) which is a datagram oriented
         * service (SOCK_DGRAM). The protocol used is the connector
         * protocol (NETLINK_CONNECTOR)
         */
        nls->socket = socket (PF_NETLINK, SOCK_DGRAM, NETLINK_CONNECTOR);
        if (nls->socket == -1) {
                log ("netlink socket error\n");
                free (nls);
                return NULL;
        }
        my_nla.nl_family = AF_NETLINK;
        my_nla.nl_groups = CN_IDX_PROC;
        my_nla.nl_pid = getpid();

        if (bind (nls->socket, (struct sockaddr *)&my_nla, sizeof(my_nla))) {
		log ("binding nls->socket error\n");
                goto close_and_exit;
        }
        nl_hdr = (struct nlmsghdr *)buff;
        cn_hdr = (struct cn_msg *)NLMSG_DATA(nl_hdr);
        mcop_msg = (enum proc_cn_mcast_op*)&cn_hdr->data[0];
	/* sending proc connector: PROC_CN_MCAST_LISTEN... */
        ZERO_ARRAY (buff);
        *mcop_msg = PROC_CN_MCAST_LISTEN;

        /* fill the netlink header */
        nl_hdr->nlmsg_len = SEND_MESSAGE_LEN;
        nl_hdr->nlmsg_type = NLMSG_DONE;
        nl_hdr->nlmsg_pid = getpid();
        /* fill the connector header */
        cn_hdr->id.idx = CN_IDX_PROC;
        cn_hdr->id.val = CN_VAL_PROC;
        cn_hdr->len = sizeof(enum proc_cn_mcast_op);
        if (send (nls->socket, nl_hdr, nl_hdr->nlmsg_len, 0) != nl_hdr->nlmsg_len) {
		log("failed to send proc connector mcast ctl op!\n");
                goto close_and_exit;
        } else {
		size_t recv_len;
                struct nlmsghdr *nlh = (struct nlmsghdr*)buff;
		struct pollfd pr = { 0, };

		pr.fd = nls->socket;
		pr.events = POLLIN;
		if ((poll (&pr, 1, 50 /* ms */) <= 0) || (!(pr.revents & POLLIN))) {
			log ("No PROC_EVENTs present\n");
			goto close_and_exit;
		}

		ZERO_ARRAY (buff);
                recv_len = netlink_recvfrom (nls, buff);
		if (recv_len < 1 || !NLMSG_OK (nlh, recv_len) ||
		    nlh->nlmsg_type != NLMSG_DONE) {
			log ("Failed to connect to PROC_EVENT via netlink\n");
			goto close_and_exit;
		} else {
			struct proc_event *ev;
			struct cn_msg *cn_hdr;

                        cn_hdr = NLMSG_DATA (nlh);
			ev = (struct proc_event*)cn_hdr->data;

			if (ev->what != PROC_EVENT_NONE || ev->event_data.ack.err) {
				log ("error: expecting an EVENT_NONE in response "
					 "to PROC_EVENT connect (err 0x%x)\n",
					 ev->event_data.ack.err);
				goto close_and_exit;
			}
			/* we made it ... */
		}
	}

	pthread_mutex_init (&nls->lock, NULL);

	if (pthread_create (&nls->listener, NULL, netlink_listen_thread, nls)) {
	    log ("Failed to create netlink thread\n");
	    goto close_and_exit;
	}

	netlink_pid_scanner_bootstrap (nls);

	return (PidScanner *)nls;

close_and_exit:
	log ("Failed to create netlink scanner\n");
	pid_scanner_free ((PidScanner *)nls);

	return NULL;
}
