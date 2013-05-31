/*
 * bootchart-output - finds, and dumps state from a main bootchart process
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
 */

#include "common.h"

#include <sys/ptrace.h>
#include <sys/mman.h>

/* simple, easy to unwind via ptrace buffer structures */

static Chunk *chunk_alloc (StackMap *sm, const char *dest)
{
	Chunk *c;
	static pthread_mutex_t guard = PTHREAD_MUTEX_INITIALIZER;

	pthread_mutex_lock (&guard);

	/* if we run out of buffer, just keep writing to the last buffer */
	if (sm->max_chunk == sizeof (sm->chunks)/sizeof(sm->chunks[0])) {
		static int overflowed = 0;
		if (unlikely(!overflowed)) {
			log ("bootchart-collector - internal buffer overflow! "
				 "did you set hz too high, or is your boot time too long ?\n");
			overflowed = 1;
		}
		c = sm->chunks[sm->max_chunk - 1];
		c->length = 0;
	} else {
		c = calloc (CHUNK_SIZE, 1);
		strncpy (c->dest_stream, dest, sizeof (c->dest_stream));
		c->length = 0;
		sm->chunks[sm->max_chunk++] = c;
	}

	pthread_mutex_unlock (&guard);
	return c;
}

/*
 * Safe to use from a single thread.
 */
BufferFile *
buffer_file_new (StackMap *sm, const char *output_fname)
{
	BufferFile *b = calloc (sizeof (BufferFile), 1);
	b->sm = sm;
	b->dest = output_fname;
	b->cur = chunk_alloc (b->sm, b->dest);
	return b;
}

void
buffer_file_append (BufferFile *file, const char *str, size_t len)
{
	do {
		unsigned long to_write = MIN (CHUNK_PAYLOAD - file->cur->length, len);
		memcpy (file->cur->data + file->cur->length, str, to_write);
		str += to_write;
		len -= to_write;
		file->cur->length += to_write;
		if (file->cur->length >= CHUNK_PAYLOAD)
			file->cur = chunk_alloc (file->sm, file->dest);
	} while (len > 0);
}

/* dump whole contents of input_fd to the output 'file' */

void
buffer_file_dump (BufferFile *file, int input_fd)
{
	for (;;) {
		ssize_t to_read = CHUNK_PAYLOAD - file->cur->length;

		to_read = read (input_fd, file->cur->data + file->cur->length, to_read);
		if (unlikely(to_read < 0)) {
			perror ("read error");
			break;
		} else if (to_read == 0) {
			break;
		}
		file->cur->length += to_read;
		if (file->cur->length >= CHUNK_PAYLOAD)
			file->cur = chunk_alloc (file->sm, file->dest);
	}
}

void
buffer_file_dump_frame_with_timestamp (BufferFile *file, int input_fd,
				       const char *uptime, size_t uptimelen)
{
	buffer_file_append (file, uptime, uptimelen);

	lseek (input_fd, SEEK_SET, 0);
	buffer_file_dump (file, input_fd);
  
	buffer_file_append (file, "\n", 1);
}

